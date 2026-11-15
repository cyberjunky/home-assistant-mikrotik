"""Reading a MikroTik every 30 seconds, and combining every MikroTik for where devices plug in."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CannotConnectError, InvalidAuthError, RouterOS
from .const import CONF_SSL, CONF_TRACK_DEVICES, DEFAULT_TRACK_DEVICES, DOMAIN, SCAN_INTERVAL
from .model import MikroTikData, Placement, parse, place

_LOGGER = logging.getLogger(__name__)

type MikroTikConfigEntry = ConfigEntry[MikroTikCoordinator]

# The Wi-Fi packages, newest first: (name, its menu)
_WIFI_PACKAGES = (("wifi", ("interface", "wifi")), ("wifiwave2", ("interface", "wifiwave2")))


def read_wifi(api: RouterOS, package: list[str]) -> dict[str, Any]:
    """The Wi-Fi interfaces, their profiles, the registrations and the CAPs managed over CAPsMAN.

    package caches which package this device has, found on the first read.
    """
    if not package:
        for name, menu in _WIFI_PACKAGES:
            if api.read(*menu) is not None:
                package.append(name)
                break
        else:
            package.append("wireless" if api.read("interface", "wireless") is not None else "")
    found = package[0]
    out: dict[str, Any] = {"package": found, "interfaces": [], "registrations": [], "remote_caps": []}
    if found in ("wifi", "wifiwave2"):
        menu = ("interface", found)
        out["interfaces"] = api.read(*menu) or []
        out["configurations"] = api.read(*menu, "configuration") or []
        out["registrations"] = api.read(*menu, "registration-table") or []
        out["remote_caps"] = api.read(*menu, "capsman", "remote-cap") or []
    elif found == "wireless":
        out["interfaces"] = api.read("interface", "wireless") or []
        out["registrations"] = api.read("interface", "wireless", "registration-table") or []
    if found in ("wireless", ""):
        # CAPsMAN of RouterOS 6: the CAPs' interfaces and clients are on the manager
        caps = api.read("caps-man", "registration-table")
        if caps:
            out["registrations"] += caps
            out["interfaces"] += api.read("caps-man", "interface") or []
            out["remote_caps"] = api.read("caps-man", "remote-cap") or []
    return out


class MikroTikCoordinator(DataUpdateCoordinator[MikroTikData]):
    """One MikroTik."""

    config_entry: MikroTikConfigEntry

    def __init__(self, hass: HomeAssistant, entry: MikroTikConfigEntry, api: RouterOS) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=entry.data[CONF_HOST], update_interval=SCAN_INTERVAL)
        self.api = api
        self.host: str = entry.data[CONF_HOST]
        self._wifi_package: list[str] = []

    @property
    def track_devices(self) -> bool:
        return bool(self.config_entry.options.get(CONF_TRACK_DEVICES, DEFAULT_TRACK_DEVICES))

    def _read(self) -> dict[str, Any]:
        api = self.api
        raw: dict[str, Any] = {
            "resource": api.read("system", "resource"),
            "identity": api.read("system", "identity"),
            "routerboard": api.read("system", "routerboard"),
            "health": api.read("system", "health"),
            "interface": api.read("interface") or [],
            "address": api.read("ip", "address"),
            "bridge_host": api.read("interface", "bridge", "host"),
            "neighbor": api.read("ip", "neighbor"),
            "dhcp_server": api.read("ip", "dhcp-server"),
            # The default route and ARP: which MAC is the gateway, so the port it is on leads up
            "route": api.read("ip", "route"),
            "arp": api.read("ip", "arp"),
            "wifi": read_wifi(api, self._wifi_package),
        }
        if not raw["bridge_host"]:
            # Older RouterOS and the CRS1xx/2xx: the switch chip keeps the MAC table
            raw["switch_host"] = api.read("interface", "ethernet", "switch", "host") or api.read(
                "interface", "ethernet", "switch", "unicast-fdb"
            )
        running = [
            i["name"] for i in raw["interface"] if i.get("type") == "ether" and i.get("running") in (True, "true")
        ]
        raw["links"] = api.links(running)
        if self.track_devices:
            raw["dhcp"] = api.read("ip", "dhcp-server", "lease")
        return raw

    async def _async_update_data(self) -> MikroTikData:
        try:
            raw = await self.hass.async_add_executor_job(self._read)
        except InvalidAuthError as err:
            raise ConfigEntryAuthFailed from err
        except CannotConnectError as err:
            raise UpdateFailed(f"{self.host}: {err}") from err
        return parse(raw, self.host, self.data)

    @callback
    def _async_refresh_finished(self) -> None:
        super()._async_refresh_finished()
        if self.last_update_success:
            fabric(self.hass).changed(self)


class Fabric:
    """Every MikroTik in Home Assistant together: where each device plugs in, and which entry tracks it."""

    def __init__(self) -> None:
        self.coordinators: dict[str, MikroTikCoordinator] = {}
        self.placement: dict[str, Placement] = {}
        # A device is tracked by one entry: the first that has it
        self.claims: dict[str, str] = {}

    def add(self, coordinator: MikroTikCoordinator) -> None:
        self.coordinators[coordinator.config_entry.entry_id] = coordinator

    def remove(self, entry_id: str) -> None:
        self.coordinators.pop(entry_id, None)
        self.claims = {mac: e for mac, e in self.claims.items() if e != entry_id}

    def claim(self, mac: str, entry_id: str) -> bool:
        return self.claims.setdefault(mac, entry_id) == entry_id

    def device(self, entry_id: str) -> MikroTikData | None:
        c = self.coordinators.get(entry_id)
        return c.data if c and c.data else None

    @callback
    def changed(self, source: MikroTikCoordinator) -> None:
        sources = {e: c.data for e, c in self.coordinators.items() if c.data}
        placement = place(sources)
        if placement == self.placement:
            return
        self.placement = placement
        # The others' trackers show where their devices plug in
        for c in self.coordinators.values():
            if c is not source and c.data:
                c.async_update_listeners()


def fabric(hass: HomeAssistant) -> Fabric:
    return hass.data.setdefault(DOMAIN, Fabric())


def api_from_entry(data: dict[str, Any]) -> RouterOS:
    return RouterOS(
        data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_PORT], data.get(CONF_SSL, False)
    )

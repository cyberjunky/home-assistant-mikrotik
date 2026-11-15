"""Device trackers: the network's devices this MikroTik knows (DHCP, ARP, Wi-Fi), with where they plug in.

Only when "Track network devices" is on. Each device is tracked by one MikroTik (the first that
has it), and says on which switch port or access point it is, over every MikroTik in Home Assistant.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_AP_MAC,
    ATTR_AP_NAME,
    ATTR_INTERFACE,
    ATTR_IP_ADDRESSES,
    ATTR_LAST_SEEN,
    ATTR_SIGNAL,
    ATTR_SSID,
    ATTR_SWITCH_MAC,
    ATTR_SWITCH_NAME,
    ATTR_SWITCH_PORT,
    ATTR_VLAN,
    CONF_CONSIDER_HOME,
    CONF_DEVICES_ENABLED,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_DEVICES_ENABLED,
)
from .coordinator import MikroTikConfigEntry, MikroTikCoordinator, fabric
from .model import Client

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: MikroTikConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if not coordinator.track_devices:
        return
    consider_home = timedelta(seconds=entry.options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME))
    enabled = bool(entry.options.get(CONF_DEVICES_ENABLED, DEFAULT_DEVICES_ENABLED))
    added: set[str] = set()

    @callback
    def add_new() -> None:
        new = []
        for mac in coordinator.data.clients:
            if mac in added or not fabric(hass).claim(mac, entry.entry_id):
                continue
            added.add(mac)
            new.append(MikroTikTracker(coordinator, mac, consider_home, enabled))
        if new:
            async_add_entities(new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class MikroTikTracker(CoordinatorEntity[MikroTikCoordinator], RestoreEntity, ScannerEntity):
    """A device on the network."""

    # ScannerEntity marks trackers as diagnostic, which hides them by default
    _attr_entity_category = None  # type: ignore[assignment]

    def __init__(self, coordinator: MikroTikCoordinator, mac: str, consider_home: timedelta, enabled: bool) -> None:
        super().__init__(coordinator)
        self._attr_mac_address = mac
        self._consider_home = consider_home
        self._enabled = enabled
        self._last_seen: datetime | None = None
        self._update()

    @property
    def entity_registry_enabled_default(self) -> bool:
        """ScannerEntity only enables a tracker whose MAC another integration knows: per the option instead."""
        return self._enabled

    @property
    def _client(self) -> Client | None:
        return self.coordinator.data.clients.get(self.mac_address or "") if self.coordinator.data else None

    @property
    def name(self) -> str:
        client = self._client
        return (client and (client.comment or client.hostname)) or self.hostname or self.mac_address or ""

    def _seen_now(self) -> bool:
        """Answering this MikroTik (ARP, its Wi-Fi), or registered to the Wi-Fi of any MikroTik."""
        client = self._client
        if self.coordinator.last_update_success and client and client.active:
            return True
        where = fabric(self.hass).placement.get(self.mac_address or "") if self.hass else None
        return bool(where and where.kind == "wifi")

    @property
    def is_connected(self) -> bool:
        if self._seen_now():
            return True
        return self._last_seen is not None and dt_util.utcnow() - self._last_seen <= self._consider_home

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        client = self._client
        if client and client.interface:
            attrs[ATTR_INTERFACE] = client.interface
        if client and len(client.ips) > 1:
            attrs[ATTR_IP_ADDRESSES] = client.ips
        if client and client.ssid:
            attrs[ATTR_SSID] = client.ssid
        if client and client.signal is not None:
            attrs[ATTR_SIGNAL] = client.signal
        f = fabric(self.hass)
        where = f.placement.get(self.mac_address or "")
        device = f.device(where.device) if where else None
        if where and device:
            if where.kind == "wifi":
                attrs[ATTR_AP_MAC] = device.main_mac
                attrs[ATTR_AP_NAME] = f"{device.identity} {where.port}"
                if where.signal is not None:
                    attrs[ATTR_SIGNAL] = where.signal
            else:
                attrs[ATTR_SWITCH_MAC] = device.main_mac
                attrs[ATTR_SWITCH_PORT] = where.port
                attrs[ATTR_SWITCH_NAME] = device.identity
                if where.vlan is not None:
                    attrs[ATTR_VLAN] = where.vlan
        if self._last_seen:
            attrs[ATTR_LAST_SEEN] = self._last_seen.isoformat()
        return attrs

    def _update(self) -> None:
        client = self._client
        if not self.coordinator.last_update_success or client is None:
            return
        if client.ip:
            self._attr_ip_address = client.ip
        if client.hostname:
            self._attr_hostname = client.hostname
        if self._seen_now():
            self._last_seen = dt_util.utcnow()

    async def async_added_to_hass(self) -> None:
        """When the device was last seen survives a restart."""
        if (last := await self.async_get_last_state()) is not None:
            seen = last.attributes.get(ATTR_LAST_SEEN)
            if self._last_seen is None and isinstance(seen, str):
                self._last_seen = dt_util.parse_datetime(seen)
        await super().async_added_to_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update()
        super()._handle_coordinator_update()

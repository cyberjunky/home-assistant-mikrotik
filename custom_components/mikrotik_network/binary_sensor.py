"""A link entity per port: on when a cable is in and the link is up, with its speed and what is on it."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTR_CONNECTED, ATTR_PORT, ATTR_PORT_SWITCH
from .coordinator import MikroTikConfigEntry, MikroTikCoordinator, fabric
from .entity import MikroTikEntity
from .model import Port

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: MikroTikConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def add_new() -> None:
        new = [PortLink(coordinator, name) for name in coordinator.data.ports if name not in added]
        added.update(p.port for p in new)
        if new:
            async_add_entities(new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class PortLink(MikroTikEntity, BinarySensorEntity):
    """A port's link."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "port"

    def __init__(self, coordinator: MikroTikCoordinator, port: str) -> None:
        super().__init__(coordinator, f"port_{port}")
        self.port = port
        self._attr_translation_placeholders = {"port": port}

    @property
    def _port(self) -> Port | None:
        return self.coordinator.data.ports.get(self.port)

    @property
    def available(self) -> bool:
        return super().available and self._port is not None

    @property
    def is_on(self) -> bool | None:
        p = self._port
        return p.running if p else None

    @property
    def icon(self) -> str:
        p = self._port
        if p and p.disabled:
            return "mdi:ethernet-off"
        return "mdi:ethernet" if p and p.running else "mdi:ethernet-cable-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        p = self._port
        if p is None:
            return {}
        attrs: dict[str, Any] = {
            # For other integrations and apps: which devices plug into this port, by MAC address
            ATTR_PORT_SWITCH: self.coordinator.data.main_mac,
            ATTR_PORT: p.name,
            ATTR_CONNECTED: fabric(self.hass).connected(self.coordinator.config_entry.entry_id, p.name),
            "devices": len(p.macs),
            "disabled": p.disabled,
        }
        if p.speed:
            attrs["speed_mbps"] = p.speed // 1_000_000
        if p.full_duplex is not None:
            attrs["full_duplex"] = p.full_duplex
        if p.comment:
            attrs["comment"] = p.comment
        if p.neighbor:
            attrs["neighbor"] = p.neighbor
        return attrs

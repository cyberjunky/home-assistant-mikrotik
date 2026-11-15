"""The MikroTik itself as a device, for its own entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MikroTikCoordinator


def device_info(coordinator: MikroTikCoordinator) -> DeviceInfo:
    data = coordinator.data
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.config_entry.unique_id or coordinator.config_entry.entry_id)},
        connections={(CONNECTION_NETWORK_MAC, data.main_mac)} if data.main_mac else set(),
        name=data.identity,
        manufacturer="MikroTik",
        model=data.model or None,
        serial_number=data.serial or None,
        sw_version=data.version or None,
        hw_version=data.firmware or None,
        configuration_url=f"http://{coordinator.host}",
    )


class MikroTikEntity(CoordinatorEntity[MikroTikCoordinator]):
    """An entity of the MikroTik device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MikroTikCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.unique_id or coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = device_info(coordinator)

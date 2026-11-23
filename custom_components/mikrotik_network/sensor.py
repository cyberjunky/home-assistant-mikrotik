"""Sensors: the device (CPU, memory, temperature, uptime, Wi-Fi clients), each port's traffic (off by
default), each Wi-Fi access point with its clients, and each CAP this device manages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfDataRate, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import ATTR_AP_MAC, ATTR_CONNECTED, ATTR_INTERFACE
from .coordinator import MikroTikConfigEntry, MikroTikCoordinator, fabric
from .entity import MikroTikEntity
from .model import MikroTikData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class DeviceSensorDescription(SensorEntityDescription):
    value: Callable[[MikroTikData], Any]
    exists: Callable[[MikroTikData], bool] = lambda d: True


def _boot_time(d: MikroTikData) -> datetime | None:
    if d.uptime is None:
        return None
    # Rounded to the minute, so it doesn't change with every read
    boot = dt_util.utc_from_timestamp(d.read_at) - timedelta(seconds=d.uptime)
    return boot.replace(second=0, microsecond=0)


DEVICE_SENSORS = (
    DeviceSensorDescription(
        key="cpu",
        translation_key="cpu",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d.cpu,
    ),
    DeviceSensorDescription(
        key="memory",
        translation_key="memory",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=lambda d: None if d.memory is None else round(d.memory * 100, 1),
    ),
    DeviceSensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d.temperature,
        exists=lambda d: d.temperature is not None,
    ),
    DeviceSensorDescription(
        key="boot",
        translation_key="boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_boot_time,
    ),
    DeviceSensorDescription(
        key="wifi_clients",
        translation_key="wifi_clients",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: len(d.wifi),
        exists=lambda d: bool(d.access_points),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: MikroTikConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def add_new() -> None:
        d = coordinator.data
        new: list[SensorEntity] = []
        for description in DEVICE_SENSORS:
            if description.key not in added and description.exists(d):
                new.append(DeviceSensor(coordinator, description))
                added.add(description.key)
        for port in d.ports:
            for direction in ("rx", "tx"):
                if (key := f"{direction}_{port}") not in added:
                    new.append(PortTraffic(coordinator, port, direction))
                    added.add(key)
        for name in d.access_points:
            if (key := f"ap_{name}") not in added:
                new.append(AccessPointSensor(coordinator, name))
                added.add(key)
        for name in d.remote_caps:
            if (key := f"cap_{name}") not in added:
                new.append(RemoteCapSensor(coordinator, name))
                added.add(key)
        if new:
            async_add_entities(new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class DeviceSensor(MikroTikEntity, SensorEntity):
    entity_description: DeviceSensorDescription

    def __init__(self, coordinator: MikroTikCoordinator, description: DeviceSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)


class PortTraffic(MikroTikEntity, SensorEntity):
    """What goes into (rx) or out of (tx) a port. On by default: it is what the ports are for,
    and a port with nothing on it stays 0, which the recorder doesn't write again."""

    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_native_unit_of_measurement = UnitOfDataRate.BYTES_PER_SECOND
    _attr_suggested_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_suggested_display_precision = 1
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: MikroTikCoordinator, port: str, direction: str) -> None:
        super().__init__(coordinator, f"{direction}_{port}")
        self.port = port
        self.direction = direction
        self._attr_translation_key = f"port_{direction}"
        self._attr_translation_placeholders = {"port": port}

    @property
    def native_value(self) -> float | None:
        p = self.coordinator.data.ports.get(self.port)
        if p is None:
            return None
        return p.rx_rate if self.direction == "rx" else p.tx_rate


class AccessPointSensor(MikroTikEntity, SensorEntity):
    """A Wi-Fi interface: its clients, with its network, band and frequency."""

    _attr_translation_key = "access_point"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: MikroTikCoordinator, name: str) -> None:
        super().__init__(coordinator, f"ap_{name}")
        self.ap = name
        self._attr_translation_placeholders = {"name": name}

    @property
    def available(self) -> bool:
        return super().available and self.ap in self.coordinator.data.access_points

    @property
    def native_value(self) -> int | None:
        ap = self.coordinator.data.access_points.get(self.ap)
        return ap.clients if ap else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ap = self.coordinator.data.access_points.get(self.ap)
        if ap is None:
            return {}
        attrs: dict[str, Any] = {
            # For other integrations and apps: which devices are on this access point, by MAC address
            ATTR_AP_MAC: self.coordinator.data.main_mac,
            ATTR_INTERFACE: ap.name,
            ATTR_CONNECTED: fabric(self.hass).connected(self.coordinator.config_entry.entry_id, ap.name),
            "ssid": ap.ssid,
            "running": ap.running,
            "disabled": ap.disabled,
            "mac": ap.mac,
        }
        for key in ("band", "frequency", "master"):
            if value := getattr(ap, key):
                attrs[key] = value
        return attrs


class RemoteCapSensor(MikroTikEntity, SensorEntity):
    """An access point managed over CAPsMAN: its state, address, model and version."""

    _attr_translation_key = "remote_cap"

    def __init__(self, coordinator: MikroTikCoordinator, name: str) -> None:
        super().__init__(coordinator, f"cap_{name}")
        self.cap = name
        self._attr_translation_placeholders = {"name": name}

    @property
    def available(self) -> bool:
        return super().available and self.cap in self.coordinator.data.remote_caps

    @property
    def native_value(self) -> str | None:
        cap = self.coordinator.data.remote_caps.get(self.cap)
        return (cap.state or "connected") if cap else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cap = self.coordinator.data.remote_caps.get(self.cap)
        if cap is None:
            return {}
        return {k: v for k, v in vars(cap).items() if v and k != "name"}

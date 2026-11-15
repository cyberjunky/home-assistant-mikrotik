"""MikroTik Network: your MikroTik routers, switches and access points in Home Assistant.

Device trackers for the network's devices (with the switch port or access point they are on), the
ports with their link and traffic, the Wi-Fi access points with their clients, and the device itself.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import CannotConnectError, InvalidAuthError
from .coordinator import MikroTikConfigEntry, MikroTikCoordinator, api_from_entry, fabric

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: MikroTikConfigEntry) -> bool:
    api = api_from_entry(dict(entry.data))
    try:
        await hass.async_add_executor_job(api.connect)
    except InvalidAuthError as err:
        raise ConfigEntryAuthFailed from err
    except CannotConnectError as err:
        raise ConfigEntryNotReady(f"{entry.data['host']}: {err}") from err
    coordinator = MikroTikCoordinator(hass, entry, api)
    fabric(hass).add(coordinator)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        fabric(hass).remove(entry.entry_id)
        await hass.async_add_executor_job(api.close)
        raise
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_options_changed))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _options_changed(hass: HomeAssistant, entry: MikroTikConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MikroTikConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        fabric(hass).remove(entry.entry_id)
        await hass.async_add_executor_job(entry.runtime_data.api.close)
    return unloaded

"""Diagnostics: what the integration reads, without the password, serial number or MAC addresses."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import MikroTikConfigEntry, fabric

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, "serial", "unique_id"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: MikroTikConfigEntry) -> dict[str, Any]:
    data = entry.runtime_data.data
    macs = sorted({*data.own_macs, *data.clients, *(m for m, _, _ in data.fdb), *(m for m, _, _ in data.wifi)})
    hidden = {mac: f"mac-{i}" for i, mac in enumerate(macs)}

    def hide(value: Any) -> Any:
        if isinstance(value, str):
            return hidden.get(value, value)
        if isinstance(value, dict):
            return {hide(k): hide(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [hide(v) for v in value]
        return value

    model = asdict(data)
    return {
        "entry": async_redact_data({**entry.as_dict(), "data": dict(entry.data)}, TO_REDACT),
        "data": hide(async_redact_data(model, TO_REDACT)),
        "placed_here": sum(1 for p in fabric(hass).placement.values() if p.device == entry.entry_id),
    }

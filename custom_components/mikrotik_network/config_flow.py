"""Adding a MikroTik: its address and an API user; the options for tracking devices."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import CannotConnectError, InvalidAuthError
from .const import (
    CONF_CONSIDER_HOME,
    CONF_DEVICES_ENABLED,
    CONF_SSL,
    CONF_TRACK_DEVICES,
    DEFAULT_API_PORT,
    DEFAULT_API_SSL_PORT,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_DEVICES_ENABLED,
    DEFAULT_TRACK_DEVICES,
    DOMAIN,
)
from .coordinator import MikroTikConfigEntry, api_from_entry

_LOGGER = logging.getLogger(__name__)


def _probe(data: dict[str, Any]) -> tuple[str, str]:
    """Log in and read its name and serial number. Blocking."""
    api = api_from_entry(data)
    api.connect()
    try:
        identity = (api.read("system", "identity") or [{}])[0].get("name") or data[CONF_HOST]
        board = (api.read("system", "routerboard") or [{}])[0]
        # A CHR (virtual RouterOS) has no serial number: its address then
        return str(identity), str(board.get("serial-number") or data[CONF_HOST])
    finally:
        api.close()


class MikroTikConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    # Why the last try failed (connection refused, timed out, ..), shown with the error
    _reason = ""

    async def _check(self, data: dict[str, Any], errors: dict[str, str]) -> tuple[str, str] | None:
        try:
            return await self.hass.async_add_executor_job(_probe, data)
        except InvalidAuthError:
            errors["base"] = "invalid_auth"
        except CannotConnectError as err:
            errors["base"] = "cannot_connect"
            self._reason = str(err) or type(err).__name__
            _LOGGER.warning("Cannot connect to %s:%s: %s", data[CONF_HOST], data[CONF_PORT], self._reason)
        except Exception as err:
            errors["base"] = "unknown"
            self._reason = f"{type(err).__name__}: {err}"
            _LOGGER.exception("Unexpected error connecting to %s:%s", data[CONF_HOST], data[CONF_PORT])
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**user_input}
            data[CONF_PORT] = int(
                data.get(CONF_PORT) or (DEFAULT_API_SSL_PORT if data.get(CONF_SSL) else DEFAULT_API_PORT)
            )
            if found := await self._check(data, errors):
                identity, serial = found
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: data[CONF_HOST]})
                return self.async_create_entry(title=identity, data=data)
        suggested = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=suggested.get(CONF_HOST, "")): str,
                    vol.Required(CONF_USERNAME, default=suggested.get(CONF_USERNAME, "")): str,
                    vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                    vol.Optional(CONF_SSL, default=suggested.get(CONF_SSL, False)): bool,
                    vol.Optional(CONF_PORT, description={"suggested_value": suggested.get(CONF_PORT)}): NumberSelector(
                        NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"reason": self._reason},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            if await self._check(data, errors):
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME]): str,
                    vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                }
            ),
            description_placeholders={"host": entry.data[CONF_HOST], "reason": self._reason},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: MikroTikConfigEntry) -> OptionsFlow:
        return MikroTikOptionsFlow()


class MikroTikOptionsFlow(OptionsFlow):
    """Tracking the network's devices: on for the router, usually off for switches and access points."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TRACK_DEVICES, default=options.get(CONF_TRACK_DEVICES, DEFAULT_TRACK_DEVICES)
                    ): bool,
                    vol.Required(
                        CONF_DEVICES_ENABLED, default=options.get(CONF_DEVICES_ENABLED, DEFAULT_DEVICES_ENABLED)
                    ): bool,
                    vol.Required(
                        CONF_CONSIDER_HOME, default=options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME)
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=30, max=3600, step=30, unit_of_measurement="s", mode=NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
        )

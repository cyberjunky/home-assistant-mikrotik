"""Adding a MikroTik, logging in again, and the options."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mikrotik_network.const import DOMAIN

from .conftest import GW, PASSWORD, USER

GOOD = {"host": GW, "username": USER, "password": PASSWORD, "ssl": False}


async def test_add(hass: HomeAssistant, fake_api) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], GOOD)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "gw"
    assert result["data"]["port"] == 8728
    assert result["result"].unique_id == "GW0001"


async def test_ssl_port(hass: HomeAssistant, fake_api) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**GOOD, "ssl": True})
    assert result["data"]["port"] == 8729


async def test_wrong_login_and_no_answer(hass: HomeAssistant, fake_api) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**GOOD, "password": "wrong"})
    assert result["errors"] == {"base": "invalid_auth"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**GOOD, "host": "10.9.9.9"})
    assert result["errors"] == {"base": "cannot_connect"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], GOOD)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_added_once(hass: HomeAssistant, fake_api) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="GW0001", data={**GOOD, "port": 8728}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], GOOD)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, fake_api) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="GW0001", data={**GOOD, "port": 8728, "password": "old"})
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"username": USER, "password": "nope"})
    assert result["errors"] == {"base": "invalid_auth"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"username": USER, "password": PASSWORD})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
    assert entry.data["password"] == PASSWORD
    await hass.async_block_till_done()
    # The entry reloaded with the new password: unload it, with its timer
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_options(hass: HomeAssistant, fake_api) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="GW0001", data={**GOOD, "port": 8728})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"track_devices": False, "devices_enabled": True, "consider_home": 300}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["track_devices"] is False
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

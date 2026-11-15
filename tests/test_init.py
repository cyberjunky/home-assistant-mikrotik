"""Three MikroTiks in Home Assistant: the router tracks the devices, every one tells where they plug in."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mikrotik_network.const import DOMAIN

from .conftest import CAP, CAP_MAC, GW, LAPTOP, NAS, PASSWORD, PHONE, PI, SW, SW_MAC, USER, FakeRouterOS


def entry_for(host: str, serial: str, track: bool) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=serial,
        title=host,
        data={"host": host, "username": USER, "password": PASSWORD, "port": 8728, "ssl": False},
        options={"track_devices": track, "devices_enabled": True, "consider_home": 180},
    )


@pytest.fixture
async def network(hass: HomeAssistant, fake_api):
    entries = [entry_for(GW, "GW0001", True), entry_for(SW, "SW0002", False), entry_for(CAP, "CAP0003", False)]
    for e in entries:
        e.add_to_hass(hass)
        await hass.config_entries.async_setup(e.entry_id)
        await hass.async_block_till_done()
    # Once more, now every MikroTik is known to the others
    for e in entries:
        await e.runtime_data.async_refresh()
    await hass.async_block_till_done()
    return entries


def tracker(hass: HomeAssistant, mac: str):
    entity_id = er.async_get(hass).async_get_entity_id("device_tracker", DOMAIN, mac)
    assert entity_id, mac
    return hass.states.get(entity_id)


async def test_trackers_with_their_port(hass: HomeAssistant, network) -> None:
    assert all(e.state is ConfigEntryState.LOADED for e in network)
    pi = tracker(hass, PI)
    assert (
        pi.attributes["sw_mac"] == SW_MAC
        and pi.attributes["sw_port"] == "ether2"
        and pi.attributes["sw_name"] == "sw-garage"
    )
    assert pi.attributes["ip"] == "192.168.88.20" and pi.attributes["host_name"] == "pi"
    nas = tracker(hass, NAS)
    assert nas.state == "home" and nas.attributes["sw_port"] == "ether3" and nas.attributes["vlan"] == 10
    phone = tracker(hass, PHONE)
    assert phone.state == "home"
    assert (
        phone.attributes["ap_mac"] == CAP_MAC
        and phone.attributes["ap_name"] == "cap wifi1"
        and phone.attributes["signal"] == -52
    )
    assert "sw_mac" not in phone.attributes
    # The switches themselves hang where they are, not the other way round
    assert tracker(hass, CAP_MAC).attributes["sw_mac"] == SW_MAC
    # Only the router tracks: no trackers from the switch or the access point
    assert len(hass.states.async_entity_ids("device_tracker")) == 6


async def test_home_and_away(hass: HomeAssistant, network) -> None:
    # The router's ARP entry failed, but the cAP has it on its Wi-Fi: home
    assert tracker(hass, LAPTOP).state == "home"
    # Stale in ARP and on no Wi-Fi: not seen, so away
    assert tracker(hass, PI).state == "not_home"


async def test_ports_and_access_points(hass: HomeAssistant, network) -> None:
    reg = er.async_get(hass)
    ether2 = hass.states.get(reg.async_get_entity_id("binary_sensor", DOMAIN, "SW0002_port_ether2"))
    assert ether2.state == "on" and ether2.attributes["speed_mbps"] == 1000 and ether2.attributes["devices"] == 1
    ether4 = hass.states.get(reg.async_get_entity_id("binary_sensor", DOMAIN, "SW0002_port_ether4"))
    assert ether4.state == "off"
    wifi1 = hass.states.get(reg.async_get_entity_id("sensor", DOMAIN, "CAP0003_ap_wifi1"))
    assert wifi1.state == "2" and wifi1.attributes["ssid"] == "Home"
    cpu = hass.states.get(reg.async_get_entity_id("sensor", DOMAIN, "GW0001_cpu"))
    assert cpu.state == "7"
    # The traffic per port is there, off by default
    rx = reg.async_get(reg.async_get_entity_id("sensor", DOMAIN, "GW0001_rx_ether1"))
    assert rx.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_no_answer_and_unload(hass: HomeAssistant, network) -> None:
    gw = network[0]
    FakeRouterOS.fail = "read"
    await gw.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert not gw.runtime_data.last_update_success
    FakeRouterOS.fail = ""
    for e in network:
        assert await hass.config_entries.async_unload(e.entry_id)
    await hass.async_block_till_done()
    assert all(e.state is ConfigEntryState.NOT_LOADED for e in network)


async def test_not_reachable_at_start(hass: HomeAssistant, fake_api) -> None:
    FakeRouterOS.fail = "connect"
    e = entry_for(GW, "GW0001", True)
    e.add_to_hass(hass)
    await hass.config_entries.async_setup(e.entry_id)
    assert e.state is ConfigEntryState.SETUP_RETRY


async def test_diagnostics_hide_logins_and_macs(hass: HomeAssistant, network) -> None:
    from custom_components.mikrotik_network.diagnostics import async_get_config_entry_diagnostics

    text = str(await async_get_config_entry_diagnostics(hass, network[0]))
    assert PASSWORD not in text and "GW0001" not in text
    assert PHONE not in text and NAS not in text and "mac-0" in text

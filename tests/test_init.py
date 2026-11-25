"""Three MikroTiks in Home Assistant: the router tracks the devices, every one tells where they plug in."""

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache_with_extra_data

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


async def test_trackers_with_their_port(hass: HomeAssistant, network, caplog: pytest.LogCaptureFixture) -> None:
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
    # Each tracker has the tracked device, by its MAC address, with the tracker's name
    device = dr.async_get(hass).async_get(er.async_get(hass).async_get(pi.entity_id).device_id)
    assert device.name == "pi" and (dr.CONNECTION_NETWORK_MAC, PI) in device.connections
    assert "does not provide device info" not in caplog.text
    # Only the router tracks: no trackers from the switch or the access point
    assert len(hass.states.async_entity_ids("device_tracker")) == 6


async def test_home_and_away(hass: HomeAssistant, network) -> None:
    # The router's ARP entry failed, but the cAP has it on its Wi-Fi: home
    assert tracker(hass, LAPTOP).state == "home"
    # Stale in ARP and on no Wi-Fi: not seen, so away
    assert tracker(hass, PI).state == "not_home"


async def test_a_device_at_home_writes_no_new_state_per_poll(hass: HomeAssistant, network) -> None:
    """Being seen again changes nothing in the state: no row per poll in a recorder."""
    before = tracker(hass, NAS)
    assert before.state == "home"
    # Only a device that is away says when it was last seen
    assert "last_seen" not in before.attributes
    for _ in range(2):
        await network[0].runtime_data.async_refresh()
        await hass.async_block_till_done()
    after = tracker(hass, NAS)
    assert after.attributes == before.attributes
    assert after.last_updated == before.last_updated


async def test_last_seen_survives_a_restart(hass: HomeAssistant, fake_api) -> None:
    """Kept beside the state: a device seen a minute ago is still home, one seen days ago is away."""
    recent = dt_util.utcnow() - timedelta(seconds=60)
    mock_restore_cache_with_extra_data(hass, [(State("device_tracker.pi", "home"), {"last_seen": recent.isoformat()})])
    entry = entry_for(GW, "GW0001", True)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    pi = tracker(hass, PI)
    assert pi.entity_id == "device_tracker.pi"
    # Stale in ARP, but within consider_home
    assert pi.state == "home" and "last_seen" not in pi.attributes


async def test_last_seen_long_ago_shows_on_an_away_device(hass: HomeAssistant, fake_api) -> None:
    long_ago = dt_util.utcnow() - timedelta(days=2)
    mock_restore_cache_with_extra_data(
        hass, [(State("device_tracker.pi", "home"), {"last_seen": long_ago.isoformat()})]
    )
    entry = entry_for(GW, "GW0001", True)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    pi = tracker(hass, PI)
    assert pi.state == "not_home" and pi.attributes["last_seen"] == long_ago.isoformat()
    # It stands still while the device is away
    updated = pi.last_updated
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert tracker(hass, PI).last_updated == updated


async def test_ports_and_access_points(hass: HomeAssistant, network) -> None:
    reg = er.async_get(hass)
    ether2 = hass.states.get(reg.async_get_entity_id("binary_sensor", DOMAIN, "SW0002_port_ether2"))
    assert ether2.state == "on" and ether2.attributes["speed_mbps"] == 1000 and ether2.attributes["devices"] == 1
    # Which devices plug into it, for other integrations and apps: also devices no MikroTik tracks
    assert ether2.attributes["switch_mac"] == SW_MAC and ether2.attributes["port"] == "ether2"
    assert ether2.attributes["connected"] == [PI]
    ether3 = hass.states.get(reg.async_get_entity_id("binary_sensor", DOMAIN, "SW0002_port_ether3"))
    assert ether3.attributes["connected"] == [CAP_MAC]
    ether4 = hass.states.get(reg.async_get_entity_id("binary_sensor", DOMAIN, "SW0002_port_ether4"))
    assert ether4.state == "off"
    wifi1 = hass.states.get(reg.async_get_entity_id("sensor", DOMAIN, "CAP0003_ap_wifi1"))
    assert wifi1.state == "2" and wifi1.attributes["ssid"] == "Home"
    assert wifi1.attributes["ap_mac"] == CAP_MAC and wifi1.attributes["connected"] == sorted([PHONE, LAPTOP])
    cpu = hass.states.get(reg.async_get_entity_id("sensor", DOMAIN, "GW0001_cpu"))
    assert cpu.state == "7"
    # The traffic per port is there, on by default
    rx = reg.async_get(reg.async_get_entity_id("sensor", DOMAIN, "GW0001_rx_ether1"))
    assert rx.disabled_by is None
    # And all that went through it, as a counter for Home Assistant's statistics
    data_in = hass.states.get(reg.async_get_entity_id("sensor", DOMAIN, "GW0001_rx_bytes_ether1"))
    assert data_in.attributes["state_class"] == "total_increasing" and data_in.attributes["device_class"] == "data_size"
    assert float(data_in.state) > 0
    # Errors and drops: 0 on a healthy port, with the four counts
    errors = hass.states.get(reg.async_get_entity_id("sensor", DOMAIN, "GW0001_errors_ether1"))
    assert errors.state == "0" and errors.attributes["rx_drops"] == 0


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

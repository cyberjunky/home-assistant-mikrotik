"""The RouterOS rows as data, and where every device plugs in."""

from custom_components.mikrotik_network.model import parse, parse_rate, parse_uptime, place

from .conftest import CAP, CAP_MAC, DEVICES, GW, GW_MAC, LAPTOP, NAS, PHONE, PI, SW, SW_MAC, host


def raw(host: str) -> dict:
    menus = DEVICES[host]
    wifi = {
        "interfaces": menus.get(("interface", "wifi"), []),
        "configurations": menus.get(("interface", "wifi", "configuration"), []),
        "registrations": menus.get(("interface", "wifi", "registration-table"), []),
    }
    return {
        "resource": menus[("system", "resource")],
        "identity": menus[("system", "identity")],
        "routerboard": menus.get(("system", "routerboard")),
        "health": menus.get(("system", "health")),
        "interface": menus[("interface",)],
        "address": menus[("ip", "address")],
        "bridge_host": menus.get(("interface", "bridge", "host")),
        "neighbor": menus.get(("ip", "neighbor")),
        "dhcp_server": menus.get(("ip", "dhcp-server")),
        "dhcp": menus.get(("ip", "dhcp-server", "lease")),
        "arp": menus.get(("ip", "arp")),
        "route": menus.get(("ip", "route")),
        "links": {"ether1": {"rate": "1Gbps", "full-duplex": True}, "ether2": {"rate": "100Mbps"}},
        "wifi": wifi,
    }


def network() -> dict:
    return {host: parse(raw(host), host, now=1000.0) for host in (GW, SW, CAP)}


def test_units():
    assert parse_uptime("1w2d3h4m5s") == 7 * 86400 + 2 * 86400 + 3 * 3600 + 4 * 60 + 5
    assert parse_uptime("") is None
    assert parse_rate("2.5Gbps") == 2_500_000_000 and parse_rate("100Mbps") == 100_000_000
    assert parse_rate("unknown") is None


def test_the_router():
    gw = network()[GW]
    assert (gw.identity, gw.version, gw.serial, gw.router) == ("gw", "7.16.2", "GW0001", True)
    assert gw.cpu == 7 and gw.memory == 0.4 and gw.temperature == 48.0 and gw.uptime == 3 * 86400 + 4 * 3600 + 300
    assert gw.main_mac == GW_MAC
    assert set(gw.ports) == {"ether1", "ether2", "ether3", "ether4"}
    assert gw.ports["ether1"].speed == 1_000_000_000 and gw.ports["ether1"].comment == "internet"
    assert gw.ports["ether2"].neighbor == "sw-garage" and len(gw.ports["ether2"].macs) == 5
    assert not gw.ports["ether4"].running
    # DHCP with ARP: answered lately or not
    assert gw.clients[NAS].ip == "192.168.88.10" and gw.clients[NAS].hostname == "nas" and gw.clients[NAS].active
    assert not gw.clients[PI].active and not gw.clients[LAPTOP].active


def test_traffic_rates():
    first = parse(raw(GW), GW, now=1000.0)
    later = raw(GW)
    later["interface"] = [
        dict(i, **{"rx-byte": i["rx-byte"] + 30_000, "tx-byte": i["tx-byte"] + 3_000}) for i in later["interface"]
    ]
    second = parse(later, GW, first, now=1030.0)
    assert second.ports["ether1"].rx_rate == 1000.0 and second.ports["ether1"].tx_rate == 100.0
    assert first.ports["ether1"].rx_rate is None


def test_the_access_point():
    cap = network()[CAP]
    assert cap.access_points["wifi1"].ssid == "Home" and cap.access_points["wifi1"].clients == 2
    # The SSID from a configuration profile
    assert cap.access_points["wifi2"].ssid == "Guests" and cap.access_points["wifi2"].clients == 0
    assert cap.clients[PHONE].wifi and cap.clients[PHONE].signal == -52 and cap.clients[PHONE].ssid == "Home"
    assert not cap.router


def test_where_everything_plugs_in():
    n = network()
    placed = place(n)
    where = {mac: (p.device, p.port, p.kind) for mac, p in placed.items()}
    # A device on the port with the fewest MACs; the ports toward the router are uplinks
    assert where[PI] == (SW, "ether2", "ethernet")
    assert where[NAS] == (GW, "ether3", "ethernet") and placed[NAS].vlan == 10
    # The switches where they hang, never the other way round
    assert where[SW_MAC] == (GW, "ether2", "ethernet")
    assert where[CAP_MAC] == (SW, "ether3", "ethernet")
    assert GW_MAC not in where
    # Wi-Fi clients on their access point
    assert where[PHONE] == (CAP, "wifi1", "wifi") and placed[PHONE].signal == -52
    assert where[LAPTOP] == (CAP, "wifi1", "wifi")


def test_without_a_mikrotik_router():
    # Behind another router: the switches still find each other's order from their MAC tables
    n = network()
    n[GW].router = False
    del n[GW]
    where = {mac: (p.device, p.port) for mac, p in place(n).items()}
    assert where[CAP_MAC] == (SW, "ether3") and where[PI] == (SW, "ether2")
    assert where[PHONE] == (CAP, "wifi1")


def test_mac_table_of_an_older_switch():
    # RouterOS before 6.41, and the CRS1xx/2xx: the switch chip's table, with port or ports
    r = raw(SW)
    r["bridge_host"] = []
    r["switch_host"] = [
        {"mac-address": PI.upper(), "ports": "ether2"},
        {"mac-address": CAP_MAC.upper(), "port": "ether3"},
        {"mac-address": GW_MAC.upper(), "port": "switch1-cpu"},
    ]
    sw = parse(r, SW, now=1000.0)
    assert sw.ports["ether2"].macs == [PI] and sw.ports["ether3"].macs == [CAP_MAC]
    assert "switch1-cpu" not in {p for _, p, _ in sw.fdb}


def test_routeros_6_without_arp_status():
    r = raw(GW)
    r["arp"] = [
        {"mac-address": NAS.upper(), "address": "192.168.88.10", "interface": "bridge", "complete": True},
        {"mac-address": PI.upper(), "address": "192.168.88.20", "interface": "bridge", "complete": False},
    ]
    r["health"] = [{"temperature": 41, "voltage": 24}]
    gw = parse(r, GW, now=1000.0)
    assert gw.clients[NAS].active and not gw.clients[PI].active
    assert gw.temperature == 41.0


def test_behind_another_router():
    # A FRITZ!Box is the router: the CRS and the cAP find the port toward it from their default
    # gateway. Only the FRITZ!Box is placed there; what is seen only through that port is above.
    fritz, fritz_ip = "00:7a:a4:00:00:fe", "192.168.88.254"
    up = {
        "route": [{"dst-address": "0.0.0.0/0", "gateway": fritz_ip, "active": True}],
        "arp": [{"mac-address": fritz.upper(), "address": fritz_ip}],
    }
    sw_raw = {**raw(SW), **up}
    sw_raw["bridge_host"] = [*sw_raw["bridge_host"], host(fritz, "ether1")]
    cap_raw = {**raw(CAP), **up}
    cap_raw["bridge_host"] = [*cap_raw["bridge_host"], host(fritz, "ether1")]
    sw, cap = parse(sw_raw, SW, now=1000.0), parse(cap_raw, CAP, now=1000.0)
    assert sw.gateway_mac == fritz
    where = {mac: (p.device, p.port, p.kind) for mac, p in place({SW: sw, CAP: cap}).items()}
    assert where[fritz] == (SW, "ether1", "ethernet")
    assert where[PI] == (SW, "ether2", "ethernet") and where[CAP_MAC] == (SW, "ether3", "ethernet")
    assert where[PHONE] == (CAP, "wifi1", "wifi")
    # On the FRITZ!Box's side, not on the CRS's uplink
    assert NAS not in where and GW_MAC not in where and SW_MAC not in where


def test_gateway_as_routeros_6_writes_it():
    from custom_components.mikrotik_network.model import _gateway_mac

    r = {
        "route": [
            {"dst-address": "10.0.0.0/8", "gateway": "10.1.1.1"},
            {"dst-address": "0.0.0.0/0", "gateway": "192.168.2.254", "immediate-gw": "192.168.2.254%bridge"},
        ],
        "arp": [{"mac-address": "00:7A:A4:4B:F4:4A", "address": "192.168.2.254"}],
    }
    assert _gateway_mac(r) == "00:7a:a4:4b:f4:4a"
    assert _gateway_mac({"route": [], "arp": []}) == ""


def test_a_device_on_several_addresses():
    # A FRITZ!Box answers on its own address and on others: the gateway's address wins
    fritz = "00:7a:a4:4b:f4:4a"
    r = raw(SW)
    r["route"] = [{"dst-address": "0.0.0.0/0", "gateway": "192.168.2.254", "active": True}]
    r["arp"] = [
        {"mac-address": fritz.upper(), "address": f"192.168.2.{n}", "interface": "bridge", "status": "reachable"}
        for n in (187, 181, 254)
    ] + [
        {"mac-address": PI.upper(), "address": "192.168.2.20", "interface": "bridge", "status": "stale"},
        {"mac-address": PI.upper(), "address": "192.168.2.21", "interface": "bridge", "status": "reachable"},
    ]
    sw = parse(r, SW, now=1000.0)
    assert sw.clients[fritz].ip == "192.168.2.254" and len(sw.clients[fritz].ips) == 3
    # Not the gateway: one it answered on lately
    assert sw.clients[PI].ip == "192.168.2.21"
    # A DHCP lease always wins
    r["dhcp"] = [{"mac-address": PI.upper(), "address": "192.168.2.20", "status": "bound"}]
    assert parse(r, SW, now=1000.0).clients[PI].ip == "192.168.2.20"

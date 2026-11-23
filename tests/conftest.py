"""A network of three MikroTiks, read through a fake RouterOS API.

gw (hAP ax³, 192.168.88.1): the router; DHCP and ARP; ether2 to sw-garage, ether3 the NAS
sw-garage (CRS112, 192.168.88.2): ether2 a Raspberry Pi, ether3 the cAP
cap (cAP ax, 192.168.88.3): wifi1 with a phone and a laptop
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from custom_components.mikrotik_network.api import CannotConnectError, InvalidAuthError

GW, SW, CAP = "192.168.88.1", "192.168.88.2", "192.168.88.3"
GW_MAC, SW_MAC, CAP_MAC = "48:a9:8a:00:00:01", "48:a9:8a:00:00:02", "48:a9:8a:00:00:03"
NAS, PI, PHONE, LAPTOP = "00:11:32:00:00:10", "dc:a6:32:00:00:20", "6a:00:00:00:00:30", "a4:83:e7:00:00:40"


def iface(name: str, mac: str, running: bool = True, kind: str = "ether", **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "type": kind,
        "mac-address": mac.upper(),
        "running": running,
        "disabled": False,
        "rx-byte": 1000,
        "tx-byte": 2000,
        "rx-error": 0,
        "tx-error": 0,
        "rx-drop": 0,
        "tx-drop": 0,
        **extra,
    }


def host(mac: str, port: str, vid: int = 1) -> dict[str, Any]:
    return {"mac-address": mac.upper(), "on-interface": port, "local": False, "vid": vid}


DEVICES: dict[str, dict[tuple[str, ...], Any]] = {
    GW: {
        ("system", "identity"): [{"name": "gw"}],
        ("system", "resource"): [
            {
                "uptime": "3d4h5m",
                "version": "7.16.2 (stable)",
                "board-name": "hAP ax^3",
                "cpu-load": 7,
                "free-memory": 600,
                "total-memory": 1000,
            }
        ],
        ("system", "routerboard"): [
            {"model": "C53UiG+5HPaxD2HPaxD", "serial-number": "GW0001", "current-firmware": "7.16.2"}
        ],
        ("system", "health"): [{"name": "cpu-temperature", "value": "48", "type": "C"}],
        ("interface",): [
            iface("ether1", GW_MAC, comment="internet"),
            iface("ether2", GW_MAC),
            iface("ether3", GW_MAC),
            iface("ether4", GW_MAC, running=False),
            iface("bridge", GW_MAC, kind="bridge"),
        ],
        ("ip", "address"): [{"address": f"{GW}/24", "interface": "bridge"}],
        ("interface", "bridge", "host"): [
            host(SW_MAC, "ether2"),
            host(PI, "ether2"),
            host(CAP_MAC, "ether2"),
            host(PHONE, "ether2"),
            host(LAPTOP, "ether2"),
            host(NAS, "ether3", vid=10),
            host(GW_MAC, "bridge") | {"local": True},
        ],
        ("ip", "neighbor"): [{"interface": "ether2,bridge", "mac-address": SW_MAC.upper(), "identity": "sw-garage"}],
        ("ip", "dhcp-server"): [{"name": "defconf", "interface": "bridge", "disabled": False}],
        ("ip", "dhcp-server", "lease"): [
            {"mac-address": m.upper(), "address": ip, "host-name": name, "status": "bound"}
            for m, ip, name in (
                (SW_MAC, SW, "sw-garage"),
                (CAP_MAC, CAP, "cap"),
                (NAS, "192.168.88.10", "nas"),
                (PI, "192.168.88.20", "pi"),
                (PHONE, "192.168.88.30", "phone"),
                (LAPTOP, "192.168.88.40", "laptop"),
            )
        ],
        ("ip", "arp"): [
            {"mac-address": m.upper(), "address": ip, "interface": "bridge", "status": status}
            for m, ip, status in (
                (SW_MAC, SW, "reachable"),
                (CAP_MAC, CAP, "reachable"),
                (NAS, "192.168.88.10", "reachable"),
                (PI, "192.168.88.20", "stale"),
                (PHONE, "192.168.88.30", "reachable"),
                (LAPTOP, "192.168.88.40", "failed"),
            )
        ],
    },
    SW: {
        ("system", "identity"): [{"name": "sw-garage"}],
        ("system", "resource"): [
            {
                "uptime": "1w",
                "version": "7.16.2 (stable)",
                "board-name": "CRS112-8P-4S",
                "cpu-load": 2,
                "free-memory": 50,
                "total-memory": 100,
            }
        ],
        ("system", "routerboard"): [{"model": "CRS112-8P-4S", "serial-number": "SW0002"}],
        ("interface",): [
            iface("ether1", SW_MAC, comment="to gw"),
            iface("ether2", SW_MAC),
            iface("ether3", SW_MAC),
            iface("ether4", SW_MAC, running=False),
            iface("sfp9", SW_MAC, running=False),
            iface("bridge", SW_MAC, kind="bridge"),
        ],
        ("ip", "address"): [{"address": f"{SW}/24", "interface": "bridge"}],
        ("interface", "bridge", "host"): [
            host(GW_MAC, "ether1"),
            host(NAS, "ether1"),
            host(PI, "ether2"),
            host(CAP_MAC, "ether3"),
            host(PHONE, "ether3"),
            host(LAPTOP, "ether3"),
        ],
        ("ip", "neighbor"): [
            {"interface": "ether1", "mac-address": GW_MAC.upper(), "identity": "gw"},
            {"interface": "ether3", "mac-address": CAP_MAC.upper(), "identity": "cap"},
        ],
    },
    CAP: {
        ("system", "identity"): [{"name": "cap"}],
        ("system", "resource"): [
            {
                "uptime": "2d",
                "version": "7.16.2 (stable)",
                "board-name": "cAP ax",
                "cpu-load": 1,
                "free-memory": 50,
                "total-memory": 100,
            }
        ],
        ("system", "routerboard"): [{"model": "cAPGi-5HaxD2HaxD", "serial-number": "CAP0003"}],
        ("interface",): [
            iface("ether1", CAP_MAC),
            iface("wifi1", CAP_MAC, kind="wifi"),
            iface("wifi2", CAP_MAC, kind="wifi"),
        ],
        ("ip", "address"): [{"address": f"{CAP}/24", "interface": "ether1"}],
        ("interface", "bridge", "host"): [
            host(GW_MAC, "ether1"),
            host(SW_MAC, "ether1"),
            host(NAS, "ether1"),
            host(PI, "ether1"),
            host(PHONE, "wifi1"),
            host(LAPTOP, "wifi1"),
        ],
        ("ip", "neighbor"): [{"interface": "ether1", "mac-address": SW_MAC.upper(), "identity": "sw-garage"}],
        ("interface", "wifi"): [
            {
                "name": "wifi1",
                "mac-address": CAP_MAC.upper(),
                "configuration.ssid": "Home",
                "channel.band": "5ghz-ax",
                "running": True,
            },
            {
                "name": "wifi2",
                "mac-address": CAP_MAC.upper(),
                "configuration": "guest",
                "channel.band": "2ghz-ax",
                "running": True,
            },
        ],
        ("interface", "wifi", "configuration"): [{"name": "guest", "ssid": "Guests"}],
        ("interface", "wifi", "registration-table"): [
            {"mac-address": PHONE.upper(), "interface": "wifi1", "signal": -52},
            {"mac-address": LAPTOP.upper(), "interface": "wifi1", "signal": -67},
        ],
    },
}
# Menus every device has (empty here); anything else is a package it doesn't have
EMPTY = {("interface", "wifi", "capsman", "remote-cap")}

USER, PASSWORD = "monitor", "secret"


class FakeRouterOS:
    """The RouterOS API of one of the devices above."""

    fail: str = ""

    def __init__(self, host: str, username: str, password: str, port: int, use_ssl: bool) -> None:
        self.host, self.username, self.password = host, username, password
        self.connected = False

    def connect(self) -> None:
        if FakeRouterOS.fail == "connect" or self.host not in DEVICES:
            raise CannotConnectError("no route to host")
        if (self.username, self.password) != (USER, PASSWORD):
            raise InvalidAuthError
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def read(self, *path: str) -> list[dict[str, Any]] | None:
        if FakeRouterOS.fail == "read":
            raise CannotConnectError("connection lost")
        menus = DEVICES[self.host]
        if path in menus:
            return [dict(r) for r in menus[path]]
        return [] if path in EMPTY else None

    def links(self, names: list[str]) -> dict[str, dict[str, Any]]:
        return {n: {"name": n, "rate": "1Gbps", "full-duplex": True} for n in names}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def fake_api():
    FakeRouterOS.fail = ""
    with patch("custom_components.mikrotik_network.coordinator.RouterOS", FakeRouterOS):
        yield FakeRouterOS

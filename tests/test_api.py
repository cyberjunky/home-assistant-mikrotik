"""The RouterOS API wrapper: logging in, a menu a device doesn't have, a dropped connection."""

from unittest.mock import MagicMock, patch

import pytest
from librouteros.exceptions import ConnectionClosed, MultiTrapError, TrapError

from custom_components.mikrotik_network.api import CannotConnectError, InvalidAuthError, RouterOS


def device(menus):
    api = MagicMock()

    def path(*p):
        if p not in menus:
            raise TrapError("no such command prefix")
        if isinstance(menus[p], Exception):
            raise menus[p]
        return iter(menus[p])

    api.path.side_effect = path
    return api


def test_login_errors():
    ros = RouterOS("10.0.0.1", "u", "p", 8728, False)
    with patch("librouteros.connect", side_effect=TrapError("invalid user name or password (6)")):
        with pytest.raises(InvalidAuthError):
            ros.connect()
    with patch("librouteros.connect", side_effect=OSError("timed out")):
        with pytest.raises(CannotConnectError):
            ros.connect()


def test_ssl_wraps_the_socket():
    ros = RouterOS("10.0.0.1", "u", "p", 8729, True)
    with patch("librouteros.connect") as connect:
        ros.connect()
    assert "ssl_wrapper" in connect.call_args.kwargs and connect.call_args.kwargs["port"] == 8729


def test_reading():
    ros = RouterOS("10.0.0.1", "u", "p", 8728, False)
    api = device(
        {
            ("system", "identity"): [{"name": "gw"}],
            ("ip", "arp"): ConnectionClosed("gone"),
            # RouterOS 7 without the wifi package answers with two errors at once
            ("interface", "wifi"): MultiTrapError(
                TrapError("no such command or directory (wifi)"), TrapError("no such command prefix")
            ),
            ("system", "health"): TrapError("not enough permissions (9)"),
        }
    )
    with patch("librouteros.connect", return_value=api):
        # Connects on the first read
        assert ros.read("system", "identity") == [{"name": "gw"}]
        # A package it doesn't have, or a menu the user may not read: not there, the connection is fine
        assert ros.read("interface", "wifi") is None
        assert ros.read("interface", "wireless") is None
        assert ros.read("system", "health") is None
        # A dropped connection: an error now, a new connection next time
        with pytest.raises(CannotConnectError):
            ros.read("ip", "arp")
        assert ros.read("system", "identity") == [{"name": "gw"}]


def test_links():
    ros = RouterOS("10.0.0.1", "u", "p", 8728, False)
    api = MagicMock()
    monitor = MagicMock(return_value=iter([{"name": "ether1", "rate": "1Gbps"}]))
    api.path.return_value = monitor
    with patch("librouteros.connect", return_value=api):
        ros.connect()
        assert ros.links(["ether1"]) == {"ether1": {"name": "ether1", "rate": "1Gbps"}}
    monitor.assert_called_once_with("monitor", numbers="ether1", once=True)
    assert ros.links([]) == {}


def test_login_on_any_routeros():
    from custom_components.mikrotik_network.api import login

    # 6.43 and later: the password does it
    new = MagicMock(return_value=iter([{}]))
    login(new, "u", "p")
    new.assert_called_once_with("/login", name="u", password="p")
    # Older: a challenge comes back, answered with the hashed password
    old = MagicMock(side_effect=[iter([{"ret": "ebddd18303a54111e2dea05a92ab46b4"}]), iter([{}])])
    login(old, "u", "p")
    assert old.call_count == 2
    second = old.call_args_list[1]
    assert second.kwargs["name"] == "u" and second.kwargs["response"].startswith("00")

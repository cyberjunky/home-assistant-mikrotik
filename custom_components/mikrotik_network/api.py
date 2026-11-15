"""The RouterOS API (librouteros, as Home Assistant's own MikroTik integration uses), read only."""

from __future__ import annotations

import logging
import ssl
from typing import Any

import librouteros
from librouteros.exceptions import LibRouterosError, MultiTrapError, TrapError
from librouteros.login import encode_password

_LOGGER = logging.getLogger(__name__)

# The device answered with an error (one, or several at once): a menu it doesn't have (another
# Wi-Fi package) or the user may not read. Not a broken connection.
TRAPS = (TrapError, MultiTrapError)

TIMEOUT = 10


def login(api: Any, username: str, password: str) -> None:
    """Log in on any RouterOS: 6.43 and later take the password; older ones answer with a challenge
    (ret) instead, and want the password hashed with it."""
    reply = tuple(api("/login", name=username, password=password))
    challenge = next((r["ret"] for r in reply if r.get("ret")), None)
    if challenge:
        tuple(api("/login", name=username, response=encode_password(str(challenge), password)))


class CannotConnectError(Exception):
    """The device doesn't answer, or not as RouterOS."""


class InvalidAuthError(Exception):
    """The user or password is wrong, or the user may not use the API."""


class RouterOS:
    """One connection to a RouterOS device. Blocking: run it in the executor."""

    def __init__(self, host: str, username: str, password: str, port: int, use_ssl: bool) -> None:
        self.host = host
        self._username = username
        self._password = password
        self._port = port
        self._ssl = use_ssl
        self._api: librouteros.api.Api | None = None

    def connect(self) -> None:
        kwargs: dict[str, Any] = {
            "login_method": login,
            "port": self._port,
            "encoding": "utf8",
            "timeout": TIMEOUT,
        }
        if self._ssl:
            # RouterOS ships a self-signed certificate
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            kwargs["ssl_wrapper"] = context.wrap_socket
        try:
            self._api = librouteros.connect(self.host, self._username, self._password, **kwargs)
        except (LibRouterosError, OSError, TimeoutError) as err:
            if "invalid user name or password" in str(err) or "cannot log in" in str(err):
                raise InvalidAuthError from err
            raise CannotConnectError(str(err)) from err

    def close(self) -> None:
        if self._api is not None:
            try:
                self._api.close()
            except LibRouterosError, OSError:
                pass
            self._api = None

    def read(self, *path: str) -> list[dict[str, Any]] | None:
        """Every row of a menu, or None when this device doesn't have it or the user may not read it."""
        if self._api is None:
            self.connect()
        assert self._api is not None
        try:
            return list(self._api.path(*path))
        except TRAPS as err:
            _LOGGER.debug("%s: no /%s: %s", self.host, "/".join(path), err)
            return None
        except (LibRouterosError, OSError, TimeoutError) as err:
            # A dropped connection: connect again next time
            self.close()
            raise CannotConnectError(str(err)) from err

    def links(self, names: list[str]) -> dict[str, dict[str, Any]]:
        """The link of each Ethernet port that is running (rate, duplex), in one call."""
        if not names or self._api is None:
            return {}
        try:
            rows = self._api.path("interface", "ethernet")("monitor", numbers=",".join(names), once=True)
            return {row.get("name", ""): row for row in rows}
        except TRAPS as err:
            _LOGGER.debug("%s: no link details: %s", self.host, err)
            return {}
        except (LibRouterosError, OSError, TimeoutError) as err:
            self.close()
            raise CannotConnectError(str(err)) from err

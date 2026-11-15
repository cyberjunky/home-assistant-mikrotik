"""The RouterOS API (librouteros, as Home Assistant's own MikroTik integration uses), read only."""

from __future__ import annotations

import logging
import ssl
from typing import Any

import librouteros
from librouteros.exceptions import LibRouterosError, TrapError
from librouteros.login import plain, token

_LOGGER = logging.getLogger(__name__)

TIMEOUT = 10


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
            "login_methods": (plain, token),
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
        """Every row of a menu, or None when this device doesn't have it (another Wi-Fi package)."""
        if self._api is None:
            self.connect()
        assert self._api is not None
        try:
            return list(self._api.path(*path))
        except TrapError as err:
            if "no such command" in str(err):
                return None
            raise
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
        except TrapError as err:
            _LOGGER.debug("%s: no link details: %s", self.host, err)
            return {}
        except (LibRouterosError, OSError, TimeoutError) as err:
            self.close()
            raise CannotConnectError(str(err)) from err

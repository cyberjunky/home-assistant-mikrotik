"""Constants for MikroTik Network."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "mikrotik_network"
NAME: Final = "MikroTik Network"

DEFAULT_API_PORT: Final = 8728
DEFAULT_API_SSL_PORT: Final = 8729
SCAN_INTERVAL: Final = timedelta(seconds=30)

CONF_SSL: Final = "ssl"
CONF_TRACK_DEVICES: Final = "track_devices"
CONF_DEVICES_ENABLED: Final = "devices_enabled"
CONF_CONSIDER_HOME: Final = "consider_home"

DEFAULT_TRACK_DEVICES: Final = True
DEFAULT_DEVICES_ENABLED: Final = True
DEFAULT_CONSIDER_HOME: Final = 180

# On a device tracker: where it plugs in, in the names UniFi uses, so other apps and
# integrations (such as the Network app) can draw it on its switch port or access point
ATTR_SWITCH_MAC: Final = "sw_mac"
ATTR_SWITCH_PORT: Final = "sw_port"
ATTR_SWITCH_NAME: Final = "sw_name"
ATTR_AP_MAC: Final = "ap_mac"
ATTR_AP_NAME: Final = "ap_name"
ATTR_VLAN: Final = "vlan"
ATTR_SSID: Final = "ssid"
ATTR_SIGNAL: Final = "signal"
ATTR_INTERFACE: Final = "interface"
ATTR_LAST_SEEN: Final = "last_seen"
# On a port or access point: the MAC addresses placed there, and the port's name
ATTR_CONNECTED: Final = "connected"
ATTR_PORT_SWITCH: Final = "switch_mac"
ATTR_PORT: Final = "port"

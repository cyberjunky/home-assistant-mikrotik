[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
![Project Maintenance][maintenance-shield]

[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg?style=for-the-badge&logo=paypal)](https://www.paypal.me/cyberjunkynl/)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor-GitHub-red.svg?style=for-the-badge&logo=github)](https://github.com/sponsors/cyberjunky)

# MikroTik Network

Your MikroTik routers, switches and access points in Home Assistant: the devices on your network,
**on which switch port or access point each one is**, every port with its link and traffic, your
Wi-Fi access points with their clients, and the MikroTiks themselves.

It reads RouterOS over its API, the same way Home Assistant's own MikroTik integration does, so it
works with RouterOS 6 and 7 and needs only a read-only user. It adds what that integration doesn't
have: the ports, the access points, and where every device plugs in, worked out over all your
MikroTiks together.

## What you get

**Device trackers** (when *Track network devices* is on): a tracker for every device the MikroTik
knows from its DHCP leases, its ARP table or its Wi-Fi. A device is home while it answers (ARP) or is
registered to the Wi-Fi of any of your MikroTiks, and for *Consider home* after that. A device is
tracked by one MikroTik only. Each tracker says where the device is:

| Attribute | |
|---|---|
| `ip`, `host_name`, `mac` | From DHCP and ARP |
| `sw_mac`, `sw_port`, `sw_name` | The switch it is plugged into (its MAC address and name) and the port, for a wired device |
| `vlan` | The VLAN it was seen in on that port |
| `ap_mac`, `ap_name`, `ssid`, `signal` | The access point, Wi-Fi network and signal (dBm), for a Wi-Fi client |
| `interface` | The interface the MikroTik sees it on |
| `last_seen` | When it was last seen |

`sw_mac`, `sw_port` and `ap_mac` are the names UniFi uses, so other integrations and apps that draw
networks understand them; the [Network app](https://github.com/cyberjunky/home-assistant-apps/tree/main/app-network)
draws every device on its switch port with them.

**Where a device plugs in.** A device's MAC address is seen on every switch between it and the router.
The integration takes the port that leads furthest down: not a port toward the router (a MikroTik
with a DHCP server), and of the others the one with the fewest MAC addresses, since an uplink carries
everything behind it. A Wi-Fi client is on the access point it is registered to. Add all your
MikroTiks, also the ones that don't track devices, so it knows the whole network.

**Per port** (Ethernet and SFP): a link entity, on when the link is up, with its speed, duplex,
comment, the MikroTik or LLDP neighbour on it and how many devices are behind it. The traffic in and
out of each port is there as two sensors, off by default (two per port is many): turn on the ones you
want.

**Per Wi-Fi access point** (a radio of the MikroTik, or one it manages over CAPsMAN): its clients, with
its SSID, band and frequency. A CAPsMAN manager also gets a sensor per CAP it manages, with its
address, model and version.

**The MikroTik itself**: CPU load, memory used, temperature (when it has a sensor), when it last
started, and the number of Wi-Fi clients.

## Installation

Through HACS: add `https://github.com/cyberjunky/home-assistant-mikrotik` as a custom repository of
the type *Integration*, install **MikroTik Network**, and restart Home Assistant.

## Setup

On each MikroTik, a read-only user for the API:

```
/user group add name=homeassistant policy=read,api
/user add name=homeassistant group=homeassistant password=<a long password>
```

The `api` service (port 8728) is on by default. For an encrypted connection turn on `api-ssl`
(port 8729) and tick *Use SSL*.

Then in Home Assistant: **Settings → Devices & services → Add integration → MikroTik Network**, with
the address, the user and the password. Add every MikroTik: the router, the switches and the access
points.

### Options

| Option | Default | |
|---|---|---|
| Track network devices | on | A tracker for every device this MikroTik knows. On for your router; turn it off for switches and access points (they still tell where devices plug in) |
| Enable new device trackers | on | Home Assistant leaves trackers of devices it doesn't know disabled; this enables them |
| Consider home | 180 s | How long a device that isn't seen any more still counts as home |

## Compared with Home Assistant's MikroTik integration

Kept: the login (RouterOS 6 and 7, the API with or without SSL, logging in again when the password
changes), device trackers from DHCP, ARP and Wi-Fi (the wifi, wifiwave2, wireless and CAPsMAN
packages) with *Consider home*.

Left out: *ARP ping* and *Force DHCP*. RouterOS's own ARP state (reachable or not) tells whether a
device answers, without pinging every device every time.

New: *Track network devices* as an option, where each device plugs in, the ports, the access points,
and the MikroTik's own sensors.

Both can run side by side; they have different names (`mikrotik` and `mikrotik_network`).

[releases-shield]: https://img.shields.io/github/release/cyberjunky/home-assistant-mikrotik.svg?style=for-the-badge
[releases]: https://github.com/cyberjunky/home-assistant-mikrotik/releases
[license-shield]: https://img.shields.io/github/license/cyberjunky/home-assistant-mikrotik.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-cyberjunky-blue.svg?style=for-the-badge

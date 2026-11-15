[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
![Project Maintenance][maintenance-shield]

[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg?style=for-the-badge&logo=paypal)](https://www.paypal.me/cyberjunkynl/)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor-GitHub-red.svg?style=for-the-badge&logo=github)](https://github.com/sponsors/cyberjunky)

# MikroTik Network

<img src="custom_components/mikrotik_network/brand/icon.png" alt="MikroTik Network" width="128" align="right">

Your MikroTik routers, switches and access points in Home Assistant: the devices on your network,
**on which switch port or access point each one is**, every port with its link and traffic, your
Wi-Fi access points with their clients, and the MikroTiks themselves.

It reads RouterOS over its API, the same way Home Assistant's own MikroTik integration does, so it
works with RouterOS 6.43 and later and RouterOS 7, and needs only a read-only user. It adds what that integration doesn't
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

On each MikroTik, in its terminal (Winbox, WebFig or SSH):

1. **A read-only user** for the API:

   ```
   /user group add name=homeassistant policy=read,api
   /user add name=homeassistant group=homeassistant password=<a long password>
   ```

2. **The API service on**, best only for Home Assistant's address. It is off on many MikroTiks:

   ```
   /ip service enable api
   /ip service set api address=<Home Assistant IP>/32
   ```

   `/ip service print where name~"api"` shows whether it is on (no `X`), its port (8728) and which
   addresses may use it. For an encrypted connection use `api-ssl` (port 8729, it needs a
   certificate) instead, and tick *Use SSL* in Home Assistant.

3. **The firewall lets Home Assistant in.** The default configuration of a MikroTik router accepts
   only what comes from its LAN. If Home Assistant is in another VLAN or subnet, allow it:

   ```
   /ip firewall filter add chain=input protocol=tcp dst-port=8728 src-address=<Home Assistant IP> action=accept place-before=0 comment="Home Assistant API"
   ```

Then in Home Assistant: **Settings → Devices & services → Add integration → MikroTik Network**, with
the address, the user and the password. Add every MikroTik: the router, the switches and the access
points.

### When it can't connect

The form says why:

| It says | Look at |
|---|---|
| Connection refused | The `api` service is off, or on another port (step 2) |
| Timed out | The firewall drops it, or the service's *Available From* doesn't include Home Assistant's address (steps 2 and 3) |
| An SSL error | *Use SSL* is ticked, but `api-ssl` is off or has no certificate |
| The user or password is wrong | The user, the password, or the group lacks the `api` policy (step 1) |

Switches running **SwOS** (the CSS series, and CRS models started in SwOS) have no API at all: switch
them to RouterOS to add them.

### Options

| Option | Default | |
|---|---|---|
| Track network devices | on | A tracker for every device this MikroTik knows. On for your router; turn it off for switches and access points (they still tell where devices plug in) |
| Enable new device trackers | on | Home Assistant leaves trackers of devices it doesn't know disabled; this enables them |
| Consider home | 180 s | How long a device that isn't seen any more still counts as home |

## Compared with Home Assistant's MikroTik integration

Kept: the login (RouterOS 6.43 and later, and 7, the API with or without SSL, logging in again when the password
changes), device trackers from DHCP, ARP and Wi-Fi (the wifi, wifiwave2, wireless and CAPsMAN
packages) with *Consider home*.

Left out: *ARP ping* and *Force DHCP*. RouterOS's own ARP state (reachable or not) tells whether a
device answers, without pinging every device every time.

New: *Track network devices* as an option, where each device plugs in, the ports, the access points,
and the MikroTik's own sensors.

Both can run side by side; they have different names (`mikrotik` and `mikrotik_network`).

## Diagnostics

**Settings → Devices & services → MikroTik Network → ⋮ → Download diagnostics** gives what the
integration read from that MikroTik: its ports, access points, clients and where each device was
placed. The password, user, serial number and MAC addresses are left out (MAC addresses become
`mac-0`, `mac-1`, …), so it can be shared in an issue.

## Development

```bash
uv venv --python 3.14
uv pip install -r requirements_test.txt
uv run pytest
uvx ruff check custom_components tests
```

The tests run against a fake network of three MikroTiks (a router, a switch and an access point), so no
MikroTik is needed.

## 💖 Support This Project

If you find this integration useful, please consider supporting its continued development:

[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg?style=for-the-badge&logo=paypal)](https://www.paypal.me/cyberjunkynl/)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor-GitHub-red.svg?style=for-the-badge&logo=github)](https://github.com/sponsors/cyberjunky)

## License

MIT, see [LICENSE](LICENSE). It talks to RouterOS with [librouteros](https://github.com/luqasz/librouteros), as Home Assistant's own MikroTik integration does.

---

[releases-shield]: https://img.shields.io/github/release/cyberjunky/home-assistant-mikrotik.svg?style=for-the-badge
[releases]: https://github.com/cyberjunky/home-assistant-mikrotik/releases
[commits-shield]: https://img.shields.io/github/commit-activity/y/cyberjunky/home-assistant-mikrotik.svg?style=for-the-badge
[commits]: https://github.com/cyberjunky/home-assistant-mikrotik/commits/main
[license-shield]: https://img.shields.io/github/license/cyberjunky/home-assistant-mikrotik.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-cyberjunky-blue.svg?style=for-the-badge

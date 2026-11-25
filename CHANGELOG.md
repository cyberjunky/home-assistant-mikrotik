# Changelog

## 0.1.6

**After updating:** nothing to do, unless a template of yours reads `last_seen` of a device that is home: it gets nothing now.

- **Far fewer state writes:** `last_seen` is no longer refreshed in the attributes of a device that is home. It was updated with every poll, which made every poll a new state for each device to record. The attribute now only shows on a device that is away, where it gives the time the device was last seen and stays fixed. Home and away, and "consider home", work as before, also across a restart.

## 0.1.5

**After updating:** traffic sensors you already had stay as they were. If you never turned on the *Port … in* and *Port … out* sensors, turn them on once: Settings → Entities, search for "port", select them, Enable selected.

- **Port traffic on by default:** *Port … in* and *Port … out* are now on for new ports. They are what the Network app's Traffic page needs, and a port with nothing on it stays at 0, which Home Assistant doesn't record again.
- **Data per port:** *Port … data in* and *Port … data out* count all that went through a port since the MikroTik started, so Home Assistant can show the data per hour, day or month.
- **Errors per port:** *Port … errors* counts broken and dropped frames, with each count as an attribute. It stays 0 on a healthy port; one that keeps rising points to a bad cable or plug.

## 0.1.4

- **Each tracked device is a device in Home Assistant:** a device tracker now says which device it tracks, by its MAC address, as Home Assistant asks of integrations from 2027.11 on. That ends the warning in the log that the integration "does not provide device info for its ScannerEntity device tracker". The device is named as the tracker is (the comment in RouterOS, else the hostname), and keeps that name while it is away.

## 0.1.3

- **A hAP with its factory DHCP server is not the router:** a MikroTik counted as the top of the network as soon as it ran a DHCP server. A hAP that still has its default DHCP server, behind a FRITZ!Box, then made everything it saw through its own uplink look plugged into that uplink. Now a MikroTik only counts as the router when its own default gateway isn't on the network; otherwise its uplink is an uplink like any other.

## 0.1.2

- **A device on several addresses:** a device that answers on more than one address (a FRITZ!Box does) gets its DHCP lease, else the default gateway's address, else one it answered on lately, instead of whichever came first in ARP. All its addresses are on the tracker as `ip_addresses`.

## 0.1.1

- **Which device on which port, for every device:** each port and Wi-Fi access point lists the MAC addresses plugged into it (`connected`), with the switch's or access point's MAC (`switch_mac`, `ap_mac`) and the port's name. Behind another router a MikroTik tracks only a few devices itself; now a device tracked by any integration (arp-scan, the FRITZ!Box) can be placed on its port, as the Network app does.

## 0.1.0

- First version: MikroTik routers, switches and access points over the RouterOS API (RouterOS 6, also before 6.43, and 7, with or without SSL). Device trackers from DHCP, ARP and Wi-Fi (wifi, wifiwave2, wireless, CAPsMAN), with *Track network devices*, *Enable new device trackers* and *Consider home* as options. Every tracker says on which switch port (`sw_mac`, `sw_port`, `vlan`) or access point (`ap_mac`, `ssid`, `signal`) it is, worked out over all MikroTiks together. A link entity per port, traffic per port (off by default), a sensor per Wi-Fi access point and per CAP managed over CAPsMAN, and CPU, memory, temperature and last boot of the MikroTik itself.

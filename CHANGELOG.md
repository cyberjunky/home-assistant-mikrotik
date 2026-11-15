# Changelog

## 0.1.1

- **Which device on which port, for every device:** each port and Wi-Fi access point lists the MAC addresses plugged into it (`connected`), with the switch's or access point's MAC (`switch_mac`, `ap_mac`) and the port's name. Behind another router a MikroTik tracks only a few devices itself; now a device tracked by any integration (arp-scan, the FRITZ!Box) can be placed on its port, as the Network app does.

## 0.1.0

- First version: MikroTik routers, switches and access points over the RouterOS API (RouterOS 6, also before 6.43, and 7, with or without SSL). Device trackers from DHCP, ARP and Wi-Fi (wifi, wifiwave2, wireless, CAPsMAN), with *Track network devices*, *Enable new device trackers* and *Consider home* as options. Every tracker says on which switch port (`sw_mac`, `sw_port`, `vlan`) or access point (`ap_mac`, `ssid`, `signal`) it is, worked out over all MikroTiks together. A link entity per port, traffic per port (off by default), a sensor per Wi-Fi access point and per CAP managed over CAPsMAN, and CPU, memory, temperature and last boot of the MikroTik itself.

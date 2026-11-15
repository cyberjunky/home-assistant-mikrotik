# Changelog

## 0.1.0

- First version: MikroTik routers, switches and access points over the RouterOS API (RouterOS 6, also before 6.43, and 7, with or without SSL). Device trackers from DHCP, ARP and Wi-Fi (wifi, wifiwave2, wireless, CAPsMAN), with *Track network devices*, *Enable new device trackers* and *Consider home* as options. Every tracker says on which switch port (`sw_mac`, `sw_port`, `vlan`) or access point (`ap_mac`, `ssid`, `signal`) it is, worked out over all MikroTiks together. A link entity per port, traffic per port (off by default), a sensor per Wi-Fi access point and per CAP managed over CAPsMAN, and CPU, memory, temperature and last boot of the MikroTik itself.

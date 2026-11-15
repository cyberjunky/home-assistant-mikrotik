"""What a MikroTik says, as data: the device, its ports, its Wi-Fi access points and its clients.

Pure functions from the rows the RouterOS API returns, so the tests can feed them. The rows differ
between RouterOS 6 and 7 and between the Wi-Fi packages (wifi, wifiwave2, wireless, CAPsMAN v6);
only this module knows that.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

# A Wi-Fi registration says where a client is, whatever the MAC tables say: it counts as half a MAC
WIFI_WEIGHT = 0.5

_UPTIME = re.compile(r"(\d+)([wdhms])")
_UNITS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
_RATE = re.compile(r"^([\d.]+)\s*([kMG]?)bps$")
# ARP states that mean the device answered lately (stale and failed don't)
_ARP_ALIVE = {"reachable", "delay", "probe", "permanent"}


def normalize_mac(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", ":")
    return text if re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", text) else ""


def parse_uptime(text: Any) -> int | None:
    """RouterOS writes 1w2d3h4m5s."""
    parts = _UPTIME.findall(str(text or ""))
    return sum(int(n) * _UNITS[u] for n, u in parts) if parts else None


def parse_rate(text: Any) -> int | None:
    """A link rate as RouterOS writes it (1Gbps, 100Mbps, 2.5Gbps), in bits per second."""
    m = _RATE.match(str(text or "").strip())
    if not m:
        return None
    return int(float(m.group(1)) * {"": 1, "k": 1e3, "M": 1e6, "G": 1e9}[m.group(2)])


def as_int(value: Any) -> int | None:
    try:
        return int(str(value).split("@")[0])
    except TypeError, ValueError:
        return None


def as_bool(value: Any) -> bool:
    return value is True or str(value).lower() in ("true", "yes")


@dataclass
class Port:
    name: str
    kind: str  # ethernet, sfp
    running: bool
    disabled: bool
    mac: str = ""
    comment: str = ""
    speed: int | None = None  # bits per second
    full_duplex: bool | None = None
    rx_bytes: int | None = None
    tx_bytes: int | None = None
    rx_rate: float | None = None  # bytes per second into the port
    tx_rate: float | None = None
    neighbor: str = ""  # the identity of the MikroTik/LLDP neighbour on it
    macs: list[str] = field(default_factory=list)


@dataclass
class AccessPoint:
    """A Wi-Fi interface: a radio of this device, or of a CAP it manages."""

    name: str
    mac: str = ""
    ssid: str = ""
    band: str = ""
    frequency: str = ""
    running: bool = False
    disabled: bool = False
    master: str = ""  # a virtual AP: the interface it runs on
    clients: int = 0


@dataclass
class RemoteCap:
    """An access point managed by this device over CAPsMAN."""

    name: str
    identity: str = ""
    address: str = ""
    mac: str = ""
    board: str = ""
    version: str = ""
    state: str = ""


@dataclass
class Client:
    mac: str
    ip: str = ""
    hostname: str = ""
    comment: str = ""
    interface: str = ""
    active: bool = False
    wifi: bool = False
    ssid: str = ""
    signal: int | None = None


@dataclass
class MikroTikData:
    identity: str = ""
    model: str = ""
    serial: str = ""
    firmware: str = ""
    version: str = ""
    uptime: int | None = None
    cpu: int | None = None
    memory: float | None = None  # used, 0..1
    temperature: float | None = None
    main_mac: str = ""
    own_macs: set[str] = field(default_factory=set)
    # Runs a DHCP server: the router, the top of the network
    router: bool = False
    ports: dict[str, Port] = field(default_factory=dict)
    access_points: dict[str, AccessPoint] = field(default_factory=dict)
    remote_caps: dict[str, RemoteCap] = field(default_factory=dict)
    clients: dict[str, Client] = field(default_factory=dict)
    # (mac, port, vlan) from the bridge's MAC table, and (mac, interface, signal) of the Wi-Fi clients
    fdb: list[tuple[str, str, int | None]] = field(default_factory=list)
    wifi: list[tuple[str, str, int | None]] = field(default_factory=list)
    read_at: float = 0.0


def _one(rows: list[dict] | None) -> dict:
    return rows[0] if rows else {}


def _temperature(rows: list[dict] | None) -> float | None:
    """RouterOS 7 lists sensors (name, value), RouterOS 6 has one row with temperature."""
    if not rows:
        return None
    for row in rows:
        if row.get("name") in ("cpu-temperature", "temperature", "board-temperature1"):
            try:
                return float(row.get("value"))
            except TypeError, ValueError:
                continue
    try:
        return float(rows[0]["temperature"])
    except KeyError, TypeError, ValueError:
        return None


def parse(
    raw: dict[str, Any], host: str, previous: MikroTikData | None = None, now: float | None = None
) -> MikroTikData:
    """The data from one read of every menu. previous gives the traffic rates."""
    now = time.time() if now is None else now
    resource = _one(raw.get("resource"))
    board = _one(raw.get("routerboard"))
    total, free = as_int(resource.get("total-memory")), as_int(resource.get("free-memory"))
    data = MikroTikData(
        identity=str(_one(raw.get("identity")).get("name") or host),
        model=str(board.get("model") or resource.get("board-name") or ""),
        serial=str(board.get("serial-number") or ""),
        firmware=str(board.get("current-firmware") or ""),
        version=str(resource.get("version") or "").split(" ")[0],
        uptime=parse_uptime(resource.get("uptime")),
        cpu=as_int(resource.get("cpu-load")),
        memory=1 - (free or 0) / total if total else None,
        temperature=_temperature(raw.get("health")),
        router=any(not as_bool(r.get("disabled")) for r in raw.get("dhcp_server") or []),
        read_at=now,
    )
    interfaces = raw.get("interface") or []
    by_name = {str(i.get("name")): i for i in interfaces}
    data.own_macs = {normalize_mac(i.get("mac-address")) for i in interfaces} - {""}
    # Its main MAC: the one of the interface its address is on (else the first port's)
    for row in raw.get("address") or []:
        if str(row.get("address", "")).split("/")[0] == host and row.get("interface") in by_name:
            data.main_mac = normalize_mac(by_name[row["interface"]].get("mac-address"))
    if not data.main_mac:
        data.main_mac = next((normalize_mac(i.get("mac-address")) for i in interfaces if i.get("type") == "ether"), "")

    # The MAC table: which MAC on which port. The bridge's on RouterOS 6.41 and later; the switch
    # chip's before that, and on the CRS1xx/2xx (port, or ports)
    per_port: dict[str, set[str]] = {}
    for row in [*(raw.get("bridge_host") or []), *(raw.get("switch_host") or [])]:
        mac = normalize_mac(row.get("mac-address"))
        port = str(row.get("on-interface") or row.get("port") or str(row.get("ports") or "").split(",")[0])
        if port.endswith("-cpu"):
            continue
        if not mac or not port or as_bool(row.get("local")) or mac in data.own_macs:
            continue
        per_port.setdefault(port, set()).add(mac)
        data.fdb.append((mac, port, as_int(row.get("vid"))))
    neighbors: dict[str, str] = {}
    for row in raw.get("neighbor") or []:
        port = str(row.get("interface") or "").split(",")[0]
        if port and port not in neighbors:
            neighbors[port] = str(row.get("identity") or row.get("mac-address") or "")

    links = raw.get("links") or {}
    for i in interfaces:
        name, kind = str(i.get("name") or ""), str(i.get("type") or "")
        if kind != "ether" or not name:
            continue
        rx, tx = as_int(i.get("rx-byte")), as_int(i.get("tx-byte"))
        port = Port(
            name=name,
            kind="sfp" if name.startswith("sfp") else "ethernet",
            running=as_bool(i.get("running")),
            disabled=as_bool(i.get("disabled")),
            mac=normalize_mac(i.get("mac-address")),
            comment=str(i.get("comment") or ""),
            speed=parse_rate(links.get(name, {}).get("rate")),
            full_duplex=as_bool(links[name]["full-duplex"]) if "full-duplex" in links.get(name, {}) else None,
            rx_bytes=rx,
            tx_bytes=tx,
            neighbor=neighbors.get(name, ""),
            macs=sorted(per_port.get(name, set())),
        )
        last = previous.ports.get(name) if previous else None
        dt = now - previous.read_at if previous else 0
        if (
            last
            and dt > 0
            and rx is not None
            and tx is not None
            and last.rx_bytes is not None
            and last.tx_bytes is not None
        ):
            if rx >= last.rx_bytes and tx >= last.tx_bytes:
                port.rx_rate = (rx - last.rx_bytes) / dt
                port.tx_rate = (tx - last.tx_bytes) / dt
        data.ports[name] = port

    _parse_wifi(raw.get("wifi") or {}, data)
    _parse_clients(raw, data)
    return data


def _parse_wifi(wifi: dict[str, Any], data: MikroTikData) -> None:
    """The access points (Wi-Fi interfaces) and who is registered to them, whatever the package."""
    profiles = {str(c.get("name")): c for c in wifi.get("configurations") or []}
    for row in wifi.get("interfaces") or []:
        name = str(row.get("name") or "")
        if not name:
            continue
        profile = profiles.get(str(row.get("configuration") or ""), {})
        data.access_points[name] = AccessPoint(
            name=name,
            mac=normalize_mac(row.get("mac-address") or row.get("radio-mac")),
            ssid=str(row.get("configuration.ssid") or row.get("ssid") or profile.get("ssid") or ""),
            band=str(row.get("channel.band") or row.get("band") or ""),
            frequency=str(row.get("channel.frequency") or row.get("frequency") or ""),
            running=as_bool(row.get("running")),
            disabled=as_bool(row.get("disabled")),
            master=str(row.get("master-interface") or ""),
        )
    for row in wifi.get("registrations") or []:
        mac = normalize_mac(row.get("mac-address"))
        interface = str(row.get("interface") or "")
        if not mac:
            continue
        signal = as_int(
            row.get("signal") if row.get("signal") is not None else row.get("signal-strength") or row.get("rx-signal")
        )
        data.wifi.append((mac, interface, signal))
        ap = data.access_points.get(interface)
        if ap:
            ap.clients += 1
        data.clients[mac] = Client(
            mac=mac,
            interface=interface,
            active=True,
            wifi=True,
            ssid=str(row.get("ssid") or (ap.ssid if ap else "")),
            signal=signal,
        )
    for row in wifi.get("remote_caps") or []:
        name = str(row.get("name") or row.get("identity") or row.get("address") or "")
        if not name:
            continue
        data.remote_caps[name] = RemoteCap(
            name=name,
            identity=str(row.get("identity") or ""),
            address=str(row.get("address") or ""),
            mac=normalize_mac(row.get("base-mac")),
            board=str(row.get("board") or ""),
            version=str(row.get("version") or ""),
            state=str(row.get("state") or ""),
        )


def _parse_clients(raw: dict[str, Any], data: MikroTikData) -> None:
    """The network's devices this one knows: Wi-Fi registrations (above), DHCP leases and the ARP table."""
    for row in raw.get("dhcp") or []:
        mac = normalize_mac(row.get("mac-address"))
        if not mac or as_bool(row.get("disabled")):
            continue
        client = data.clients.setdefault(mac, Client(mac=mac))
        client.ip = str(row.get("active-address") or row.get("address") or client.ip)
        client.hostname = str(row.get("host-name") or client.hostname)
        client.comment = str(row.get("comment") or client.comment)
    for row in raw.get("arp") or []:
        mac = normalize_mac(row.get("mac-address"))
        if not mac or mac in data.own_macs:
            continue
        status = str(row.get("status") or "")
        # RouterOS 6 has no status: a complete dynamic entry is a device that answered
        alive = status in _ARP_ALIVE if status else as_bool(row.get("complete")) and not as_bool(row.get("invalid"))
        client = data.clients.setdefault(mac, Client(mac=mac))
        client.ip = client.ip or str(row.get("address") or "")
        if not client.wifi:
            client.interface = str(row.get("interface") or client.interface)
        client.active = client.active or alive


# ---------------------------------------------------------------------
# Where a device plugs in, over every MikroTik
# ---------------------------------------------------------------------
@dataclass
class Placement:
    device: str  # the config entry
    port: str
    kind: str  # ethernet, wifi
    vlan: int | None = None
    signal: int | None = None


def place(sources: dict[str, MikroTikData]) -> dict[str, Placement]:
    """Where each MAC plugs in, over every MikroTik.

    A MAC is seen on every switch between the device and the router, so:
    - A port that leads to the router (a MikroTik with a DHCP server) is an uplink: nothing is placed
      on it while another place is known, and a MikroTik never is.
    - Of the other ports, the one with the fewest MACs wins (an uplink carries everything behind it);
      a Wi-Fi registration counts as half a MAC.
    Without a MikroTik router (behind another router), two MikroTiks that see each other: the one
    seen through the quieter port is the lower one, and the upper one is never placed on it.
    """
    port_macs: dict[tuple[str, str], set[str]] = {}
    load: dict[tuple[str, str], float] = {}
    for sid, d in sources.items():
        for mac, port, _ in d.fdb:
            port_macs.setdefault((sid, port), set()).add(mac)
            load[(sid, port)] = load.get((sid, port), 0) + 1
        for _mac, interface, _ in d.wifi:
            load[(sid, interface)] = load.get((sid, interface), 0) + WIFI_WEIGHT
    owner = {mac: sid for sid, d in sources.items() for mac in d.own_macs}
    routers = [sid for sid, d in sources.items() if d.router]
    router_macs = {mac for sid in routers for mac in sources[sid].own_macs}

    def toward_router(sid: str, port: str) -> bool:
        return sid not in routers and bool(port_macs.get((sid, port), set()) & router_macs)

    seen_on: dict[tuple[str, str], float] = {}
    for sid, d in sources.items():
        for mac, port, _ in d.fdb:
            x = owner.get(mac)
            if x and x != sid:
                weight = load[(sid, port)]
                seen_on[(x, sid)] = min(weight, seen_on.get((x, sid), weight))

    # Per MAC: (uplink?, weight, placement); a place that isn't an uplink always wins
    best: dict[str, tuple[bool, float, Placement]] = {}

    def offer(mac: str, sid: str, port: str, weight: float, placement: Placement) -> None:
        x = owner.get(mac)
        if x == sid:
            return
        uplink = toward_router(sid, port)
        if x and uplink:
            return
        # No router known: x seen on sid, and sid on x through a quieter port: sid is below x
        if x and not routers and (sid, x) in seen_on and seen_on[(sid, x)] < seen_on[(x, sid)]:
            return
        rank = (uplink, weight)
        if mac not in best or rank < best[mac][:2]:
            best[mac] = (uplink, weight, placement)

    for sid, d in sources.items():
        for mac, port, vlan in d.fdb:
            offer(mac, sid, port, load[(sid, port)], Placement(sid, port, "ethernet", vlan=vlan))
        for mac, interface, signal in d.wifi:
            offer(mac, sid, interface, WIFI_WEIGHT, Placement(sid, interface, "wifi", signal=signal))
    return {mac: p for mac, (_, _, p) in best.items()}

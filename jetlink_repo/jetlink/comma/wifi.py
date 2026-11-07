"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT License.
See the LICENSE file in the root directory for more details.

The link over Wi-Fi: the comma joins the device's hotspot (a phone's, a
Jetson's) and finds the server on it.

Three ways to find it, tried in this order, because they differ in what they
assume:

  - **A remembered peer.** The last address that answered, for a few minutes,
    so a drive's joins do not sweep every time.
  - **mDNS.** The server announces itself as `_jetlink._tcp` and avahi-browse
    hears it. This is the only one that needs no guess: the announcement *is*
    the server. Absent on a device without avahi, and then skipped silently.
  - **The gateway, then the subnet.** The hotspot case is the gateway (the
    phone), and a shared AP where the phone is an ordinary client is a sweep.
    Both are addresses that might be a server, so both come after the one that
    is.

On a hotspot the password the person typed into the comma is what the link
trusts, and that does not change here: the gateway and the sweep stay inside
the interface's own subnet, and mDNS answers on this interface alone. No gadget
is built over any of it and the USB-C port is left alone, so ADB keeps working.
"""
from __future__ import annotations

import ipaddress
import re
import shutil
import socket
import struct
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROUTES = Path('/proc/net/route')
INTERFACE = 'wlan0'
# a hotspot answers a connect in milliseconds, and one with nothing listening
# refuses at once; this only bounds a gateway that drops the SYN
DIAL_TIMEOUT = 1.0
# between dials while nothing answers: the app may not be open yet
DIAL_DELAY = 2.0

_RTF_UP = 0x1
_RTF_GATEWAY = 0x2

# Where a discovered peer is remembered, so subsequent joins dial it directly
# without another sweep. One line: "host:port:monotonic". Kept out of the
# params key-value dir, which must not hold extra files.
PEER_FILE = Path('/data/.jetlink_wifi_peer')
# how long a remembered peer may be reused before it must answer again
PEER_TTL_S = 300.0
# bound the sweep: a phone on the same Wi-Fi answers a TCP connect at once; this
# caps how long a host that drops the SYN may stall a probe
DISCOVER_TIMEOUT = 0.25
# never probe more hosts than this in one sweep
DISCOVER_MAX_HOSTS = 254

# The service a jetlink server announces itself as, and the daemon that hears
# it. AGNOS ships both avahi tools (the reference fork's server_locator browses
# with this same pair). A device without them gets the gateway and the sweep.
MDNS_SERVICE = '_jetlink._tcp'
BROWSE_BIN = 'avahi-browse'
# how long one browse may run: avahi-browse --terminate still needs a moment to
# hear the first answers, and a browse that outlives its usefulness holds a join
BROWSE_TIMEOUT = 2.0
# the most results a single browse is parsed for, so a busy network cannot make
# the parse unbounded
BROWSE_MAX = 32


def local_addr(interface: str = INTERFACE) -> tuple[str, int] | None:
  """The interface's IPv4 address and prefix length, e.g. ('10.0.0.44', 24).

  Lets discovery work on a normal AP where the phone is a peer client rather
  than the gateway. None when the interface has no address."""
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    import fcntl
    ip = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s', interface[:15].encode()))[20:24])  # SIOCGIFADDR
    mask = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x891b, struct.pack('256s', interface[:15].encode()))[20:24])  # SIOCGIFNETMASK
  except (OSError, ImportError):
    return None
  finally:
    s.close()
  prefix = sum(bin(int(o)).count('1') for o in mask.split('.'))
  return ip, prefix


def _probe(host: str, port: int, timeout: float) -> bool:
  """True when a jetlink server may be on host:port: the TCP connect succeeds.
  The real protocol check is the join's own HELLO, so a bare connect (no bytes
  sent) never disturbs a phone or loads its model."""
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.settimeout(timeout)
  try:
    s.connect((host, port))
    return True
  except OSError:
    return False
  finally:
    s.close()


def _save_peer(host: str, port: int) -> None:
  try:
    PEER_FILE.parent.mkdir(parents=True, exist_ok=True)
    PEER_FILE.write_text(f"{host}:{port}:{time.monotonic()}")
  except OSError:
    pass


def _saved_peer(port: int) -> str | None:
  """A still-fresh, answering remembered peer, else None."""
  try:
    host, p, ts = PEER_FILE.read_text().strip().split(':')
    if int(p) != port or time.monotonic() - float(ts) > PEER_TTL_S:
      return None
  except (OSError, ValueError):
    return None
  return host if _probe(host, port, DIAL_TIMEOUT) else None


def parse_browse(text: str, service: str = MDNS_SERVICE) -> list[tuple[str, str]]:
  """avahi-browse's output for `service` as (instance, address) pairs.

  ``avahi-browse -rtp`` prints one record a line, fields semicolon-separated:

      =;wlan0;IPv4;<instance>;_jetlink._tcp;local;<hostname>;<address>;<port>;"txt"

  Only a resolved IPv4 record for our own service counts: an unresolved one has
  no address yet, and an IPv6 one the caller cannot dial. The address comes back
  as the daemon printed it, a dotted quad for IPv4. A record whose address field
  is empty is one avahi has not finished resolving.
  """
  out: list[tuple[str, str]] = []
  for line in text.splitlines():
    if not line.startswith('='):
      continue
    fields = line.split(';')
    # '=' through at least the address field (index 7)
    if len(fields) < 8 or fields[2] != 'IPv4' or fields[4] != service:
      continue
    name, address = fields[3].strip(), fields[7].strip()
    if address:
      out.append((name, address))
    if len(out) >= BROWSE_MAX:
      break
  return out


def browse(service: str = MDNS_SERVICE, timeout: float = BROWSE_TIMEOUT) -> list[tuple[str, str]]:
  """The instances announcing `service` on the local link, as (instance, address).

  Best effort: no avahi-browse (a dev machine, or a device without it) and no
  answer are both an empty list, because the caller has the gateway and the
  sweep to fall back on. `--terminate` makes the daemon exit on its own instead
  of browsing until killed.
  """
  try:
    proc = subprocess.run([BROWSE_BIN, '-rtp', '--terminate', service],
                          capture_output=True, text=True, timeout=timeout)
  except (FileNotFoundError, OSError, subprocess.SubprocessError):
    return []
  return parse_browse(proc.stdout or '', service)


def discover(port: int = 5599, interface: str = INTERFACE,
             timeout: float = DISCOVER_TIMEOUT, skip: frozenset[str] | set[str] = frozenset(),
             mdnss: list[tuple[str, str]] | None = None) -> str | None:
  """Find a jetlink server on the local Wi-Fi without a fixed address.

  Tries a remembered peer, then mDNS (a server announcing itself), then the
  gateway (the hotspot case), then sweeps the subnet concurrently (a shared AP
  where the phone is an ordinary client). Hosts in `skip` (already tried and
  failed by the caller) are not tried again. `mdnss` is the browse result, for
  tests and for a caller that has asked already.

  Returns the first host whose TCP connect succeeds, remembered for next time.
  Pure connect probes; no HELLO, so a probe neither starts a session nor loads
  a server's model. None when nothing answers.
  """
  saved = _saved_peer(port)
  if saved and saved not in skip:
    return saved

  # mDNS first: an announced server is the server, where the rest are addresses
  # that might be one. Probes are still connects only, in case the record is stale
  for _name, address in (browse() if mdnss is None else mdnss):
    if address and address not in skip and _probe(address, port, DIAL_TIMEOUT):
      _save_peer(address, port)
      return address

  gw = gateway(interface)
  # gateway next (hotspot), then the other hosts on the link (shared AP)
  candidates: list[str] = []
  if gw and gw not in skip:
    candidates.append(gw)
  addr = local_addr(interface)
  if addr is not None:
    ip, prefix = addr
    net = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
    for h in net.hosts():
      hs = str(h)
      if hs != ip and hs != gw and hs not in skip:
        candidates.append(hs)
      if len(candidates) > DISCOVER_MAX_HOSTS:
        break

  seen: set[str] = set()
  ordered: list[str] = []
  for host in candidates:
    if host not in seen:
      seen.add(host)
      ordered.append(host)

  if not ordered:
    return None
  # probe concurrently: a host that drops the SYN waits the full timeout, and a
  # sequential /24 sweep would take seconds. The gateway is tried first, alone.
  head, rest = ordered[:1], ordered[1:]
  for host in head:
    if _probe(host, port, DIAL_TIMEOUT):
      _save_peer(host, port)
      return host
  with ThreadPoolExecutor(max_workers=32) as pool:
    for host in pool.map(lambda h: h if _probe(h, port, timeout) else None, rest):
      if host:
        _save_peer(host, port)
        return host
  return None


def gateway(interface: str = INTERFACE, routes: Path = ROUTES) -> str | None:
  """The default gateway on `interface`, or None when the comma is on no
  Wi-Fi. The modem's default route is never it."""
  try:
    lines = routes.read_text().splitlines()[1:]
  except OSError:
    return None
  for line in lines:
    f = line.split()
    # Iface Destination Gateway Flags ..., addresses in host (little-endian) order
    if len(f) < 4 or f[0] != interface or f[1] != '00000000':
      continue
    flags = int(f[3], 16)
    if flags & _RTF_UP and flags & _RTF_GATEWAY:
      return socket.inet_ntoa(struct.pack('<I', int(f[2], 16)))
  return None


def band(interface: str = INTERFACE) -> str | None:
  """The band the comma is on, '2.4', '5' or '6' (GHz), from the frequency
  iwconfig reports; None when it cannot say. Read once a dial: 2.4 GHz is
  too slow for a big model's frames, and the apps say so."""
  tool = shutil.which('iwconfig') or '/usr/sbin/iwconfig'
  try:
    out = subprocess.run([tool, interface], capture_output=True, text=True, timeout=1.0).stdout
  except (OSError, subprocess.SubprocessError):
    return None
  m = re.search(r'Frequency[:=]\s*([\d.]+)\s*GHz', out)
  if m is None:
    return None
  ghz = float(m.group(1))
  return '2.4' if ghz < 3.0 else '5' if ghz < 5.925 else '6'


def link_info(interface: str = INTERFACE) -> dict:
  """What the comma's hello says of a Wi-Fi link (Transport.link_info)."""
  b = band(interface)
  return {'kind': 'wifi', **({'band': b} if b else {})}

"""Self-signed TLS material for WebUI (enables WebCodecs over LAN HTTPS)."""

from __future__ import annotations

import logging
import socket
import ssl
import subprocess
from pathlib import Path

log = logging.getLogger("webuid")


def default_tls_dir() -> Path:
  for candidate in (
    Path("/data/openpilot/webui/tls"),
    Path("/persist/webui/tls"),
    Path.home() / ".local/share/webui/tls",
  ):
    parent = candidate.parent
    try:
      if parent.exists() or str(candidate).startswith(str(Path.home())):
        return candidate
    except OSError:
      continue
  return Path.home() / ".local/share/webui/tls"


def _local_ipv4s() -> list[str]:
  ips = {"127.0.0.1"}
  try:
    hostname = socket.gethostname()
    for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
      ips.add(info[4][0])
  except OSError:
    pass
  try:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
      s.connect(("8.8.8.8", 80))
      ips.add(s.getsockname()[0])
  except OSError:
    pass
  return sorted(ips)


def ensure_tls_files(tls_dir: Path | None = None) -> tuple[Path, Path]:
  """Create or reuse a self-signed cert + key (idempotent)."""
  directory = tls_dir or default_tls_dir()
  directory.mkdir(parents=True, exist_ok=True)
  cert = directory / "webui.crt"
  key = directory / "webui.key"
  if cert.is_file() and key.is_file():
    return cert, key

  san_parts = ["DNS:localhost", "DNS:openpilot.local"]
  for ip in _local_ipv4s():
    san_parts.append(f"IP:{ip}")
  san = ",".join(san_parts)

  cmd = [
    "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
    "-keyout", str(key),
    "-out", str(cert),
    "-days", "3650",
    "-subj", "/CN=openpilot-webui",
    "-addext", f"subjectAltName={san}",
  ]
  log.info("Generating WebUI TLS cert in %s (SAN: %s)", directory, san)
  subprocess.run(cmd, check=True, capture_output=True, text=True)
  return cert, key


def build_ssl_context(cert_path: Path, key_path: Path) -> ssl.SSLContext:
  ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
  ctx.load_cert_chain(str(cert_path), str(key_path))
  return ctx

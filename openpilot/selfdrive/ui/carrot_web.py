from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from ipaddress import ip_address
from math import ceil, floor

from openpilot.selfdrive.ui.widgets.qr_code import QRCodeTexture


CARROT_WEB_PORT = 7000  # the settings panel served by carrot_server
CARROT_WEB_ADDRESS_REFRESH_SECONDS = 0.1
CARROT_WEB_AUTO_CLOSE_SECONDS = 30.0
CARROT_WEB_MIN_CLOSE_SECONDS = 0.35

# Every LAN service worth a QR code, in the order the dialog draws them.
# 7000 is this fork's settings panel, 5080 the webui submodule, 5090 the OP
# assistant (ai.aid).
CARROT_WEB_SERVICES: tuple[tuple[str, int], ...] = (
  ("Carrot Web", 7000),
  ("WebUI", 5080),
  ("OP 助手", 5090),
)


def fit_single_line_font_size(preferred_size: int, measured_width: float, max_width: float) -> int:
  if preferred_size <= 1 or measured_width <= max_width:
    return max(1, preferred_size)
  if measured_width <= 0 or max_width <= 0:
    return 1
  return max(1, floor(preferred_size * max_width / measured_width))


def build_carrot_web_url(address: str | None, port: int = CARROT_WEB_PORT) -> str | None:
  text = str(address or "").strip()
  if not text:
    return None

  try:
    parsed = ip_address(text)
  except ValueError:
    return None

  if parsed.is_unspecified or parsed.is_loopback or parsed.is_multicast:
    return None

  host = f"[{parsed.compressed}]" if parsed.version == 6 else parsed.compressed
  return f"http://{host}:{port}"


@dataclass(frozen=True)
class CarrotWebAddress:
  address: str = ""
  url: str | None = None


class CarrotWebAddressWatcher:
  def __init__(self, params_memory, refresh_interval: float = CARROT_WEB_ADDRESS_REFRESH_SECONDS):
    self._params_memory = params_memory
    self._refresh_interval = refresh_interval
    self._next_refresh_time = 0.0
    self._value = CarrotWebAddress()

  @property
  def value(self) -> CarrotWebAddress:
    return self._value

  def refresh(self, now: float, force: bool = False) -> bool:
    if not force and now < self._next_refresh_time:
      return False

    self._next_refresh_time = now + self._refresh_interval
    try:
      address = str(self._params_memory.get("NetworkAddress") or "").strip()
    except Exception:
      address = ""

    url = build_carrot_web_url(address)
    next_value = CarrotWebAddress(address=address if url else "", url=url)
    changed = next_value != self._value
    self._value = next_value
    return changed


@dataclass(frozen=True)
class CarrotWebServiceQr:
  """One service column of the dialog: its QR texture and resolved URL."""
  label: str
  port: int
  url: str | None
  qr: QRCodeTexture


class CarrotWebQrSession:
  """One QR per service in `CARROT_WEB_SERVICES`, all keyed off NetworkAddress."""

  def __init__(self, params_memory, timestamp_factory: Callable[[], str] | None = None,
               services: tuple[tuple[str, int], ...] | None = None):
    self._address = CarrotWebAddressWatcher(params_memory)
    self._services = services or CARROT_WEB_SERVICES
    self._textures = [QRCodeTexture() for _ in self._services]
    self._urls: list[str | None] = [None] * len(self._services)
    self._timestamp_factory = timestamp_factory or (lambda: datetime.now().strftime("%H:%M:%S"))
    self._opened_at = 0.0
    self._updated_time: str | None = None

  @property
  def services(self) -> list[CarrotWebServiceQr]:
    return [
      CarrotWebServiceQr(label=label, port=port, url=self._urls[i], qr=self._textures[i])
      for i, (label, port) in enumerate(self._services)
    ]

  @property
  def updated_time(self) -> str | None:
    return self._updated_time

  def _refresh_qr(self) -> None:
    address = self._address.value.address
    self._urls = [build_carrot_web_url(address, port) for _label, port in self._services]
    for texture, url in zip(self._textures, self._urls, strict=True):
      texture.set_data(url)
    self._updated_time = self._timestamp_factory() if self._urls[0] else None

  def open(self, now: float) -> None:
    self._opened_at = now
    self._address.refresh(now, force=True)
    self._refresh_qr()

  def update(self, now: float) -> bool:
    if self._address.refresh(now):
      self._refresh_qr()
    return now - self._opened_at >= CARROT_WEB_AUTO_CLOSE_SECONDS

  def can_close(self, now: float) -> bool:
    return now - self._opened_at >= CARROT_WEB_MIN_CLOSE_SECONDS

  def seconds_until_close(self, now: float) -> int:
    return max(0, ceil(CARROT_WEB_AUTO_CLOSE_SECONDS - (now - self._opened_at)))

  def destroy(self) -> None:
    for texture in self._textures:
      texture.destroy()

import io
import json
import pickle
import shutil
import struct
import tempfile
import time
from pathlib import Path

from openpilot.common.file_chunker import get_manifest_path
from openpilot.common.hardware.usb import CHESTNUT_USB_PRODUCT, USB_DEVICES_PATH, is_chestnut_usb_id

MODELS_DIR = Path(__file__).resolve().parent / 'models'
TG_INPUT_DEVICES_PATH = MODELS_DIR / 'tg_input_devices.json'
CHESTNUT_POWERED_VOLTAGE = 5000
CHESTNUT_PCIE_READY = 0x78


def get_tg_input_devices(process_name: str, chestnut: bool):
  with open(TG_INPUT_DEVICES_PATH) as f:
    return json.load(f)[process_name]['default' if not chestnut else 'chestnut']

def modeld_pkl_path(chestnut: bool):
  prefix = 'big_' if chestnut else ''
  return MODELS_DIR / f'{prefix}driving_tinygrad.pkl'

def big_model_source_available() -> bool:
  model_path = MODELS_DIR / 'big_driving_supercombo.onnx'
  return model_path.is_file() and model_path.stat().st_size >= 1024

def dump_oob(obj, f):
  with tempfile.TemporaryFile(dir=".") as tmp:
    def buffer_callback(pb: pickle.PickleBuffer):
      m = pb.raw()
      tmp.write(struct.pack('<q', m.nbytes))
      tmp.write(m)
      pb.release() # keep peak ram at ~1 buffer
    stream = io.BytesIO()
    pickle.Pickler(stream, protocol=5, buffer_callback=buffer_callback).dump(obj)
    opcodes = stream.getvalue()
    f.write(struct.pack('<q', len(opcodes)))
    f.write(opcodes)
    tmp.seek(0)
    shutil.copyfileobj(tmp, f)

def load_oob(f):
  opcodes = f.read(struct.unpack('<q', f.read(8))[0])
  def buffers():
    while (h := f.read(8)):
      pb = pickle.PickleBuffer(bytearray(struct.unpack('<q', h)[0]))
      f.readinto(pb)
      yield pb
  return pickle.load(io.BytesIO(opcodes), buffers=buffers())

def chestnut_present() -> bool:
  for d in USB_DEVICES_PATH.glob("*"):
    try:
      usb_id = (int((d / "idVendor").read_text(), 16), int((d / "idProduct").read_text(), 16))
      product = (d / "product").read_text().strip()
      if is_chestnut_usb_id(*usb_id) and product == CHESTNUT_USB_PRODUCT:
        return True
    except Exception:
      pass
  return False

def chestnut_compiled() -> bool:
  return Path(get_manifest_path(modeld_pkl_path(chestnut=True))).is_file()


def chestnut_ready(state) -> bool:
  return state.supplyVoltage >= CHESTNUT_POWERED_VOLTAGE and not state.supplyFault and state.pcieLtssm == CHESTNUT_PCIE_READY


# ---------------------------------------------------------------------------
# USB eGPU detection (ported from CarrotPilot cluster support).
#
# sp is a Chestnut-AI-accelerator build and has no production USB eGPU model
# pipeline, so usbgpu_compiled() is conservative (False): the cluster autorun
# treats an absent eGPU as "no external display", which is the safe default.
# usbgpu_present() is real hardware probing so a user who plugs a supported
# bridge is detected even though sp never compiles for it.
# ---------------------------------------------------------------------------

USBGPU_USB_IDS = ((0xADD1, 0x0001), (0x3801, 0x0001))
USBGPU_MIN_SPEED_MBPS = 5000
USBGPU_TRANSIENT_INIT_TEXT = (
  "pcie link not up",
  "pcie power off failed",
  "pcie power on failed",
  "usb bridge reset failed",
  "read(0xb450",
  "f0 out failed: -1",
  "libusb_open: no such device",
  "amd:0 does not exist",
)


def usb_device_present(usb_ids, min_speed_mbps: int = 0) -> bool:
  for d in USB_DEVICES_PATH.glob("*"):
    try:
      usb_id = (int((d / "idVendor").read_text(), 16), int((d / "idProduct").read_text(), 16))
      speed_mbps = float((d / "speed").read_text()) if min_speed_mbps > 0 else 0
      if usb_id in usb_ids and speed_mbps >= min_speed_mbps:
        return True
    except Exception:
      pass
  return False


def usbgpu_present() -> bool:
  return usb_device_present(USBGPU_USB_IDS, USBGPU_MIN_SPEED_MBPS)


def wait_for_usbgpu_present(timeout: float, poll_interval: float = 0.1) -> bool:
  if usbgpu_present():
    return True
  deadline = time.monotonic() + max(0.0, timeout)
  poll_interval = max(0.01, poll_interval)
  while (remaining := deadline - time.monotonic()) > 0.0:
    time.sleep(min(poll_interval, remaining))
    if usbgpu_present():
      return True
  return False


def refresh_usbgpu_device_cache() -> None:
  try:
    from tinygrad.runtime.support.usb import USB3
    USB3.list_devices.__func__.cache_clear()
  except (AttributeError, ImportError):
    pass


def usbgpu_pcie_not_ready(error) -> bool:
  if isinstance(error, str):
    message = error.lower()
    return any(marker in message for marker in USBGPU_TRANSIENT_INIT_TEXT)
  return False


def usbgpu_compiled() -> bool:
  # sp never compiles the model for an external eGPU; return False so the
  # cluster autorun takes the no-external-display path when none is present.
  return False

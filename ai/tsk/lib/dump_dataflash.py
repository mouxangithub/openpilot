#!/usr/bin/env python3
"""DataFlash dump: upload the exploit payload and dump EPS memory 0xFF200000-0xFF208000.

Vehicle requirement: Not Ready to Drive mode (not READY Mode). May need two runs with a power cycle
between them (prime + dump). The first run often primes the EPS and returns 1-2
frames; a full dump follows on the second run after a power cycle.

This shares the UDS session-setup preamble with tsk/lib/extractor.py but is a
distinct operation: a different payload (payload_dataflash_ff200000_ff208000.bin),
a different dump range, and a raw frame collector instead of the key-struct parser.
The ~6 shared preamble lines are deliberately duplicated so the two operations
stay independently testable rather than coupled through a shared helper.
"""
import hashlib
import struct
import time
from pathlib import Path

from ai.tsk.lib.env import is_agnos, DATAFLASH_DIR, DATAFLASH_PAYLOAD_PATH
from ai.tsk.lib.extractor import NotAGNOSError, RetryError, TSKExtractor
from ai.tsk.lib.panda_connect import stop_manager_and_pandad

# EPS UDS parameters (shared with the extractor)
ADDR = TSKExtractor.ADDR  # 0x7a1
BUS = TSKExtractor.BUS    # 0

# Dump range
DUMP_START = 0xFF200000
DUMP_END = 0xFF208000
DUMP_TOTAL = DUMP_END - DUMP_START  # 0x8000 == 32768

# Known SecOC key location (offset from DUMP_START). The 2021+ Sienna and Yaris EPS
# keys both sit at 0x6e14; a partial dump is only usable if it captured this 16-byte
# window, since the matcher can't find a key that landed in a dropped (zeroed) gap.
KEY_SIZE = 16
KNOWN_KEY_OFFSET = 0x6E14

# Payload upload/trigger vector. Same as extractor.hack(); only the payload bytes
# and the dump range differ. The erase routine at TRIGGER_ADDR/TRIGGER_SIZE is the
# trigger that runs the already-uploaded payload, not the dump target.
PAYLOAD_LOAD_ADDR = 0xFEBF0000
PAYLOAD_LOAD_SIZE = 0x1000
TRIGGER_ADDR = 0x000E0000
TRIGGER_SIZE = 0x8000
PAYLOAD_SHA256 = "d48988366b5e6d2ddd7438caca5e6f6f02daba9b650263c323a2ffd770a06e34"

# Frame collection timing
IDLE_TIMEOUT = 10.0
MAX_SECONDS = 240.0
RESPONSE_PENDING = b"\x03\x7f\x31\x78\x00\x00\x00\x00"

DUMP_FILENAME = f"dump_{DUMP_START:08x}_{DUMP_END:08x}.bin"


def dump_path() -> Path:
  return Path(DATAFLASH_DIR) / DUMP_FILENAME


def _noop(**kwargs) -> None:
  pass


def _finalize(dump_buf, received, frames_count, bytes_received) -> dict:
  """Classify a finished collection into complete | partial | key_missed and persist it.

  Pure post-collection logic (no car I/O), so it is unit-testable off-device. A
  partial is only "allowed" — written as the .partial sidecar and offered to Find —
  when the known key window (KNOWN_KEY_OFFSET) is fully covered; otherwise it's
  key_missed: a partial dump that didn't capture the key, whether it got one frame or
  nearly all of it. key_missed persists no file, since Find can't use it.
  """
  # Complete: full coverage.
  if bytes_received >= DUMP_TOTAL:
    path = dump_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(dump_buf))
    return {
      "status": "complete",
      "frames": frames_count,
      "bytes": bytes_received,
      "total": DUMP_TOTAL,
      "dump_path": str(path),
      "message": "导出完成。",
    }

  # A dump that didn't capture the key window is unusable no matter how much it got —
  # one frame or nearly all of it, it's a partial dump without enough data. Same
  # remedy either way: restart the car and dump again (a 30s-later restart is just a
  # cold start, nothing special). Persist no file — Find can't use it.
  key_covered = all(received[KNOWN_KEY_OFFSET:KNOWN_KEY_OFFSET + KEY_SIZE])
  if not key_covered:
    return {
      "status": "key_missed",
      "frames": frames_count,
      "bytes": bytes_received,
      "total": DUMP_TOTAL,
      "dump_path": "",
      "message": (f"部分导出（{bytes_received}/{DUMP_TOTAL} 字节）。\n"
                  "密钥区域未覆盖，本次导出不可用。\n"
                  "请熄火并切回 Not Ready to Drive 后重新导出；\n"
                  "若为 RAV4 Prime/Sienna 等 UDS 可提取车型，可尝试「TSK 一键提取」跳过 CAN/DataFlash。"),
    }

  # Usable partial: the key window is covered even though the full range isn't. Save
  # to a sidecar so it can't masquerade as the canonical complete dump the matcher
  # prefers; its existence is what enables Find on a partial.
  partial_path = Path(str(dump_path()) + ".partial")
  partial_path.parent.mkdir(parents=True, exist_ok=True)
  partial_path.write_bytes(bytes(dump_buf))
  return {
    "status": "partial",
    "frames": frames_count,
    "bytes": bytes_received,
    "total": DUMP_TOTAL,
    "dump_path": str(partial_path),
    "message": (f"部分导出（{bytes_received}/{DUMP_TOTAL} 字节）。\n"
                "可尝试「查找丰田 SecOC 密钥」。\n"
                "若失败，请熄火并切回 Not Ready to Drive 模式后重新导出。"),
  }


def dump(progress_cb=None, should_cancel=None) -> dict:
  """Upload the payload and dump 0xFF200000-0xFF208000 from the EPS.

  progress_cb, if given, is called as
    progress_cb(status=, frames=, bytes_done=, total=, message=)
  with whichever keys changed. Returns a dict:
    {status, frames, bytes, total, dump_path, message}
  where status is one of: complete | partial | key_missed | failed.
  Raises NotAGNOSError off-device.
  """
  if not is_agnos():
    raise NotAGNOSError

  cb = progress_cb or _noop

  from Crypto.Cipher import AES

  from opendbc.car.isotp import isotp_send
  from opendbc.car.structs import CarParams
  from opendbc.car.uds import UdsClient, ACCESS_TYPE, SESSION_TYPE, SERVICE_TYPE, \
    ROUTINE_CONTROL_TYPE, InvalidServiceIdError, MessageTimeoutError, NegativeResponseError

  # Verify the payload before touching the car.
  payload = Path(DATAFLASH_PAYLOAD_PATH).read_bytes()
  if hashlib.sha256(payload).hexdigest() != PAYLOAD_SHA256:
    raise RetryError("DataFlash payload SHA256 mismatch")
  if len(payload) != PAYLOAD_LOAD_SIZE:
    raise RetryError("DataFlash payload wrong size")

  cb(status="running", frames=0, bytes_done=0, total=DUMP_TOTAL, message="")

  stop_manager_and_pandad()

  panda = TSKExtractor._connect_panda()
  panda.set_safety_mode(CarParams.SafetyModel.elm327)

  uds = UdsClient(panda, ADDR, ADDR + 8, BUS, timeout=0.1, response_pending_timeout=0.1)

  # Mandatory programming-session flow. Inter-transition sleeps match the Bk2ol
  # reference's known-good dataflash timing; the PROGRAMMING -> PROGRAMMING repeat
  # in particular is not exercised back-to-back by the extractor.
  try:
    uds.diagnostic_session_control(SESSION_TYPE.DEFAULT)
    time.sleep(0.5)
    uds.diagnostic_session_control(SESSION_TYPE.EXTENDED_DIAGNOSTIC)
    time.sleep(0.7)
    uds.diagnostic_session_control(SESSION_TYPE.PROGRAMMING)
    time.sleep(1.0)
    uds.diagnostic_session_control(SESSION_TYPE.PROGRAMMING)
  except (InvalidServiceIdError, MessageTimeoutError, NegativeResponseError):
    raise RetryError("Can't enter programming session.")

  # Security access.
  try:
    seed_payload = b"\x00" * 16
    seed = uds.security_access(ACCESS_TYPE.REQUEST_SEED, data_record=seed_payload)
    key = AES.new(TSKExtractor.SEED_KEY_SECRET, AES.MODE_ECB).decrypt(seed_payload)
    key = AES.new(key, AES.MODE_ECB).encrypt(seed)
    uds.security_access(ACCESS_TYPE.SEND_KEY, key)
  except (InvalidServiceIdError, MessageTimeoutError, NegativeResponseError):
    raise RetryError("Security Access failed")

  # Upload and verify the payload.
  try:
    uds.write_data_by_identifier(0x203, b"\x00" * 5)
    uds.write_data_by_identifier(0x201, TSKExtractor.DID_201_KEY)
    uds.write_data_by_identifier(0x202, TSKExtractor.DID_202_IV)

    request = b"\x01\x46\x01\x00" + struct.pack("!I", PAYLOAD_LOAD_ADDR) + struct.pack("!I", PAYLOAD_LOAD_SIZE)
    uds._uds_request(SERVICE_TYPE.REQUEST_DOWNLOAD, data=request)

    chunk_size = 0x400
    for i in range(len(payload) // chunk_size):
      uds.transfer_data(i + 1, payload[i * chunk_size:(i + 1) * chunk_size])
    uds.request_transfer_exit()

    verify = b"\x45\x00" + struct.pack("!I", PAYLOAD_LOAD_ADDR) + struct.pack("!I", PAYLOAD_LOAD_SIZE)
    uds.routine_control(ROUTINE_CONTROL_TYPE.START, 0x10f0, verify)
  except (InvalidServiceIdError, MessageTimeoutError, NegativeResponseError):
    raise RetryError("Payload upload failed")

  # Trigger the payload via the erase routine. Send manually so we don't block
  # waiting for a response that never comes. Same vector as extractor.hack().
  erase = b"\x31\x01\xff\x00" + b"\x45\x00" + struct.pack("!I", TRIGGER_ADDR) + struct.pack("!I", TRIGGER_SIZE)
  isotp_send(panda, erase, ADDR, bus=BUS)

  # Collect dump frames. Each frame carries a 24-bit pointer (low 3 bytes of the
  # address) plus 4 data bytes; the top address byte comes from DUMP_START.
  dump_buf = bytearray(DUMP_TOTAL)
  received = bytearray(DUMP_TOTAL)
  frames_count = 0
  bytes_covered = 0
  begin = time.time()
  last_progress = begin

  while True:
    if should_cancel and should_cancel():
      return {
        "status": "cancelled",
        "frames": frames_count,
        "bytes": bytes_covered,
        "total": DUMP_TOTAL,
        "dump_path": "",
        "message": "DataFlash 导出已取消。",
      }
    if time.time() - begin > MAX_SECONDS:
      break

    made_progress = False
    for addr, *_, data, bus in panda.can_recv():
      if bus != BUS or addr != ADDR + 8 or len(data) < 8:
        continue
      if data == RESPONSE_PENDING:
        continue

      ptr_low24 = (struct.unpack("<I", data[:4])[0] >> 8) & 0xFFFFFF
      offset = ((DUMP_START & 0xFF000000) | ptr_low24) - DUMP_START
      if offset < 0 or offset + 4 > DUMP_TOTAL:
        continue

      dump_buf[offset:offset + 4] = data[4:8]
      # Count only newly-covered bytes so a retransmitted or overlapping chunk isn't
      # double-counted. Replaces a per-iteration sum() over the whole 32KB buffer.
      for k in range(offset, offset + 4):
        if received[k] == 0:
          received[k] = 1
          bytes_covered += 1
      frames_count += 1
      made_progress = True

      if frames_count % 256 == 0:
        cb(status="running", frames=frames_count, bytes_done=bytes_covered, total=DUMP_TOTAL)

    if made_progress:
      last_progress = time.time()
    elif time.time() - last_progress > IDLE_TIMEOUT:
      break
    else:
      time.sleep(0.001)

    if bytes_covered >= DUMP_TOTAL:
      break

  bytes_received = bytes_covered
  cb(status="running", frames=frames_count, bytes_done=bytes_received, total=DUMP_TOTAL)
  return _finalize(dump_buf, received, frames_count, bytes_received)

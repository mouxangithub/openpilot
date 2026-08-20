#!/usr/bin/env python3
"""Find and verify the Toyota SecOC key inside a DataFlash dump.

This is pure computation — it takes the 32KB dump (from dump_dataflash.py) plus a
CAN oracle (sync + protected frames captured from the bus) and returns the key or
nothing. It never touches the car, so it is not is_agnos-gated and runs anywhere
the two input files exist.

Design (per the 2026-07-05 decisions, refined for capture-noise tolerance):
  - Car-agnostic. No model gate. The verification below is the safety net.
  - No candidate system. No entropy filter, no scoring, no candidate cap. An
    exhaustive stride-1 byte-aligned scan over every 16-byte window (32,753 of
    them) filters candidates with an AES-CMAC first pass, then fully verifies
    survivors against the whole oracle.
  - First pass unions several sync samples (FIRST_PASS_SAMPLES), spread across the
    capture, so one bad sync frame can't hide the key. The CMAC subkeys depend only
    on the window, so they are computed once per window and reused across probes.
  - Acceptance is an absolute match count, not a percentage: accept when a window
    authenticates at least MATCH_FLOOR oracle samples (sync + protected), of which
    at least MIN_SYNC_MATCHES are sync. A wrong window clears a 28-bit sync MAC with
    p=2^-28 and a protected MAC with p~2^-22, so reaching MATCH_FLOOR is ~2^-660 or
    less — impossible — while a real key clears essentially all samples, so a few
    corrupt frames are tolerated instead of rejecting the key.

The AES-CMAC core (subkeys, MAC, first28/tail28, sync_input, freshness, the oracle
loader) is reused verbatim from the proven reference verifier and matches openpilot's
own opendbc/car/secoc.py bit-for-bit.

This module does not install the key. It returns the key hex to the caller, which
installs via KeyFileManager (same split as /api/extract).
"""
import json
import struct
import time
from pathlib import Path

from Crypto.Cipher import AES

from ai.tsk.lib.dump_dataflash import DUMP_START, DUMP_TOTAL, dump_path
from ai.tsk.lib.env import CAN_ORACLE_PATH

# Acceptance: a window must authenticate at least MATCH_FLOOR oracle samples
# (sync + protected), of which at least MIN_SYNC_MATCHES are sync. MATCH_FLOOR is
# far above the noise floor for a wrong key (~2^-660) and easily reached by a real
# capture (tens of sync + hundreds of protected), so a few corrupt frames don't
# reject the key. Raising MATCH_FLOOR buys no safety and only demands a richer
# capture, so it is kept modest.
MATCH_FLOOR = 30
MIN_SYNC_MATCHES = 2
FIRST_PASS_SAMPLES = 5

# Oracle framing (matches the reference loader and the collector's target format).
SYNC_ADDR = 0x0F
PROTECTED_ADDRS = {0x131, 0x2E4, 0x344}
ORACLE_BUSES = {0, 2}
MAX_SYNC_SAMPLES = 1024
MAX_PROTECTED_PER_ADDR = 250

def oracle_path() -> Path:
  return Path(CAN_ORACLE_PATH)


# --- AES-CMAC (RFC 4493) primitives, matching opendbc/car/secoc.py ---

def _left_shift_one(buf: bytes) -> bytes:
  out = bytearray(len(buf))
  carry = 0
  for i in range(len(buf) - 1, -1, -1):
    out[i] = ((buf[i] << 1) & 0xFF) | carry
    carry = 1 if (buf[i] & 0x80) else 0
  return bytes(out)


def _xor(a: bytes, b: bytes) -> bytes:
  return bytes(x ^ y for x, y in zip(a, b))


def _cmac_subkeys(key: bytes):
  L = AES.new(key, AES.MODE_ECB).encrypt(b"\x00" * 16)
  K1 = bytearray(_left_shift_one(L))
  if L[0] & 0x80:
    K1[15] ^= 0x87
  K2 = bytearray(_left_shift_one(bytes(K1)))
  if K1[0] & 0x80:
    K2[15] ^= 0x87
  return bytes(K1), bytes(K2)


def _aes_cmac(key: bytes, msg: bytes, subkeys=None) -> bytes:
  K1, K2 = subkeys or _cmac_subkeys(key)
  n = max(1, (len(msg) + 15) // 16)
  complete = len(msg) > 0 and len(msg) % 16 == 0
  if complete:
    last = _xor(msg[(n - 1) * 16:n * 16], K1)
  else:
    chunk = (msg[(n - 1) * 16:] + b"\x80").ljust(16, b"\x00")
    last = _xor(chunk, K2)
  X = b"\x00" * 16
  cipher = AES.new(key, AES.MODE_ECB)
  for i in range(n - 1):
    X = cipher.encrypt(_xor(X, msg[i * 16:(i + 1) * 16]))
  return cipher.encrypt(_xor(X, last))


def _first28(mac: bytes) -> int:
  return ((mac[0] << 20) | (mac[1] << 12) | (mac[2] << 4) | (mac[3] >> 4)) & 0xFFFFFFF


def _tail28(data: bytes) -> int:
  return (((data[4] & 0x0F) << 24) | (data[5] << 16) | (data[6] << 8) | data[7]) & 0xFFFFFFF


def _sync_input(trip: int, reset: int) -> bytes:
  return struct.pack(">HH", 0x0F, trip) + bytes(
    [((reset << 4) >> 16) & 0xFF, ((reset << 4) >> 8) & 0xFF, (reset << 4) & 0xFF])


def _freshness(trip: int, reset: int, msg_cnt: int) -> bytes:
  return struct.pack(">HI", trip & 0xFFFF,
                     ((reset & 0xFFFFF) << 12) | ((msg_cnt & 0xFF) << 4) | ((reset & 3) << 2))


def load_oracle_samples(path: Path):
  """Parse a can_oracle.ndjson file into (sync_samples, protected_samples, malformed).

  Each line is a raw CAN frame {addr, bus, data(hex)}. Sync frames (0x0F) carry a
  (trip, reset, auth); protected frames on the three SecOC addresses inherit the
  trip/reset of the most recent sync seen on their bus. Malformed lines (torn JSON,
  bad hex, missing fields) are skipped and counted rather than crashing the load, so
  a corrupt or truncated capture degrades legibly instead of failing hard.
  """
  sync_samples = []
  protected_samples = []
  sync_by_bus = {}
  sync_seen = set()
  prot_counts = {}
  malformed = 0

  with path.open("r", encoding="utf-8") as f:
    for line in f:
      if not line.strip():
        continue
      try:
        r = json.loads(line)
        addr = int(r["addr"])
        bus = int(r["bus"])
        data = bytes.fromhex(r["data"][:16])
      except (ValueError, KeyError, TypeError):
        malformed += 1
        continue
      if bus not in ORACLE_BUSES or len(data) < 8:
        continue

      if addr == SYNC_ADDR:
        trip = int.from_bytes(data[0:2], "big")
        reset = (data[2] << 12) | (data[3] << 4) | (data[4] >> 4)
        auth = _tail28(data)
        sync_by_bus[bus] = (trip, reset, auth)
        k = (bus, trip, reset, auth)
        if k not in sync_seen and len(sync_samples) < MAX_SYNC_SAMPLES:
          sync_seen.add(k)
          sync_samples.append({"bus": bus, "trip": trip, "reset": reset, "auth": auth})

      elif addr in PROTECTED_ADDRS:
        if prot_counts.get(addr, 0) >= MAX_PROTECTED_PER_ADDR:
          continue
        if bus not in sync_by_bus:
          continue
        trip, reset, _ = sync_by_bus[bus]
        prot_counts[addr] = prot_counts.get(addr, 0) + 1
        protected_samples.append({
          "addr": addr, "bus": bus, "payload4": data[:4], "flag": data[4] >> 4,
          "auth": _tail28(data), "trip": trip, "reset": reset,
        })

  return sync_samples, protected_samples, malformed


def _verify_sync(key: bytes, samples, subkeys) -> int:
  matches = 0
  for s in samples:
    if _first28(_aes_cmac(key, _sync_input(s["trip"], s["reset"]), subkeys)) == s["auth"]:
      matches += 1
  return matches


def _verify_protected(key: bytes, samples, subkeys) -> int:
  matches = 0
  for s in samples:
    for msg_cnt in range(256):
      flag = ((msg_cnt & 3) << 2) | (s["reset"] & 3)
      if flag != s["flag"]:
        continue
      msg = struct.pack(">H", s["addr"]) + s["payload4"] + _freshness(s["trip"], s["reset"], msg_cnt)
      if _first28(_aes_cmac(key, msg, subkeys)) == s["auth"]:
        matches += 1
        break
  return matches


def _base_result() -> dict:
  return {
    "status": "",       # found | not_found | insufficient_oracle | no_dump
    "key": "",
    "offset": -1,
    "address": "",
    "sync": "",
    "protected": "",
    "matches": 0,
    "windows_scanned": 0,
    "survivors": 0,
    "elapsed": 0.0,
    "malformed": 0,
    "dump_partial": False,
    "message": "",
  }


def find_key(dump: bytes, sync_samples, protected_samples, progress_cb=None) -> dict:
  """Exhaustively scan dump for a window that authenticates the CAN oracle.

  Pure function: no file or car I/O. The first pass runs one AES-CMAC per 16-byte
  window against a spread of sync samples (survivor if it clears any); survivors are
  then counted against every sync and protected sample, and the best is accepted if
  it clears at least MATCH_FLOOR samples with at least MIN_SYNC_MATCHES sync.
  """
  result = _base_result()
  t0 = time.time()
  n_windows = max(0, len(dump) - 15)
  n_sync = len(sync_samples)
  n_prot = len(protected_samples)
  result["windows_scanned"] = n_windows

  if n_sync == 0:
    result.update(status="not_found", elapsed=time.time() - t0,
                  message="CAN 校验文件中没有 sync 样本。")
    return result

  # First pass: union over sync samples spread across the capture, so a bad sample
  # (including a garbage burst at the start) can't hide the key. subkeys depend only
  # on the window, so compute once and reuse across probes.
  probe_idx = sorted({i * n_sync // FIRST_PASS_SAMPLES for i in range(FIRST_PASS_SAMPLES)})
  probes = [(_sync_input(sync_samples[j]["trip"], sync_samples[j]["reset"]), sync_samples[j]["auth"])
            for j in probe_idx]
  survivors = []
  for off in range(n_windows):
    window = dump[off:off + 16]
    subkeys = _cmac_subkeys(window)
    for tin, target in probes:
      if _first28(_aes_cmac(window, tin, subkeys)) == target:
        survivors.append(off)
        break
    if progress_cb is not None and (off & 0xFFF) == 0:
      progress_cb(scanned=off, total=n_windows, survivors=len(survivors))
  result["survivors"] = len(survivors)

  # Full verification: count every sync + protected match. Keep the strongest.
  best = None
  for off in survivors:
    window = dump[off:off + 16]
    subkeys = _cmac_subkeys(window)
    sync_matches = _verify_sync(window, sync_samples, subkeys)
    prot_matches = _verify_protected(window, protected_samples, subkeys)
    total = sync_matches + prot_matches
    if best is None or total > best["total"]:
      best = {"offset": off, "key": window, "sync": sync_matches,
              "protected": prot_matches, "total": total}

  result["elapsed"] = time.time() - t0

  if best is None:
    result.update(status="not_found", sync=f"0/{n_sync}", protected=f"0/{n_prot}",
                  message="没有窗口能通过 CAN 校验。密钥不在本次导出中，或采集数据异常——请重新采集 CAN 后再试。")
    return result

  result["sync"] = f"{best['sync']}/{n_sync}"
  result["protected"] = f"{best['protected']}/{n_prot}"
  result["matches"] = best["total"]
  result["offset"] = best["offset"]
  addr = DUMP_START + best["offset"]
  result["address"] = f"0x{addr:08x}"

  accepted = best["total"] >= MATCH_FLOOR and best["sync"] >= MIN_SYNC_MATCHES
  if accepted:
    result.update(status="found", key=best["key"].hex(), address=f"0x{addr:08x}",
                  message=f"在 0x{addr:08x} 找到并验证 SecOC 密钥 "
                          f"（{best['total']} 次匹配：sync {result['sync']}，protected {result['protected']}）。")
  else:
    if best["sync"] < MIN_SYNC_MATCHES:
      reason = f"仅 {best['sync']} 次 sync 匹配，至少需要 {MIN_SYNC_MATCHES} 次"
    else:
      reason = f"{best['total']} 次匹配，至少需要 {MATCH_FLOOR} 次"
    result.update(status="not_found",
                  message=f"0x{addr:08x} 的最佳窗口未通过信任校验（{reason}）。请重新采集 CAN 后再试。")
  return result


def run(progress_cb=None) -> dict:
  """Load the dump and CAN oracle from disk and run find_key. Returns the result
  dict; does not install the key.

  Prefers the complete dump; if only a partial (.partial sidecar) exists, runs on
  that. A partial can only surface the key if the key's 16-byte window fell in the
  captured bytes — the zero-filled gaps can't forge a match — so a partial run is
  safe: it finds the real key or reports not-found and asks for a full re-dump.
  """
  result = _base_result()

  complete_path = dump_path()
  partial_path = Path(str(complete_path) + ".partial")
  dump_is_partial = False
  try:
    dump = complete_path.read_bytes()
  except OSError:
    try:
      dump = partial_path.read_bytes()
      dump_is_partial = True
    except OSError:
      result.update(status="no_dump", message="未找到 DataFlash 导出文件。请先导出 DataFlash。")
      return result
  if len(dump) != DUMP_TOTAL:
    result.update(status="no_dump",
                  message=f"导出文件为 {len(dump)} 字节，应为 {DUMP_TOTAL} 字节。请重新导出 DataFlash。")
    return result

  try:
    sync_samples, protected_samples, malformed = load_oracle_samples(oracle_path())
  except OSError:
    result.update(status="insufficient_oracle", message="未找到 CAN 校验文件。请先采集 CAN 报文。")
    return result

  result["malformed"] = malformed
  total = len(sync_samples) + len(protected_samples)
  if len(sync_samples) < MIN_SYNC_MATCHES or total < MATCH_FLOOR:
    msg = (f"CAN 数据不足（sync {len(sync_samples)}，protected {len(protected_samples)}；"
           f"至少需要 {MATCH_FLOOR} 条总计且 {MIN_SYNC_MATCHES} 条 sync）。请采集更多 CAN。")
    if malformed:
      msg += f"（已跳过 {malformed} 行格式错误。）"
    result.update(status="insufficient_oracle", message=msg)
    return result

  res = find_key(dump, sync_samples, protected_samples, progress_cb=progress_cb)
  res["malformed"] = malformed
  res["dump_partial"] = dump_is_partial
  # A partial that fails to find the key most likely never captured the key's region.
  # The collapsed message is deliberate: the modal shows no debug block for a partial.
  if dump_is_partial and res["status"] == "not_found":
    res["message"] = (
      "在部分 DataFlash 导出中未找到密钥。\n"
      "请熄火并切回 Not Ready to Drive 后重新完整导出；\n"
      "或清除缓存后重新执行 CAN→DataFlash→查找；\n"
      "RAV4 Prime/Sienna 等可尝试 TSK 一键提取。"
    )
  return res

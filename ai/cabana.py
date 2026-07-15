"""
Cabana Web backend, served from the AI agent service on port 5090.

This keeps Cabana independent from openpilot/dashy while sharing the same
HTTP server as the AI web UI.
"""

import asyncio
import gzip
import hashlib
import json
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aiohttp import web

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

try:
  from cereal import messaging
except ImportError:
  messaging = None  # type: ignore

try:
  from opendbc.can.dbc import DBC
  from opendbc.car.values import PLATFORMS
except ImportError:
  DBC = None  # type: ignore
  PLATFORMS = {}  # type: ignore

try:
  from opendbc import DBC_PATH, get_generated_dbcs
except ImportError:
  DBC_PATH = ""  # type: ignore
  def get_generated_dbcs() -> dict[str, str]:  # type: ignore
    return {}

try:
  from openpilot.tools.lib.logreader import LogReader
except ImportError:
  LogReader = None  # type: ignore


def _can_frame_to_dict(cf, mono_time: float | None = None) -> dict[str, Any]:
  return {
    "address": int(cf.address),
    "bus": int(cf.src),
    "data": cf.dat.hex(),
    "time": mono_time if mono_time is not None else 0.0,
  }


_CAR_PARAM_KEYS = (
  "CarParams",
  "CarParamsCache",
  "CarParamsPersistent",
  "CarParamsPrevRoute",
)


def _car_params_from_bytes(raw: bytes) -> dict[str, Any] | None:
  try:
    from cereal import car
    with car.CarParams.from_bytes(raw) as cp:
      return {
        "brand": cp.brand,
        "carFingerprint": cp.carFingerprint,
        "openpilotLongitudinalControl": bool(cp.openpilotLongitudinalControl),
      }
  except Exception:
    return None


def _load_car_params_from_params() -> dict[str, Any] | None:
  params = Params()
  for key in _CAR_PARAM_KEYS:
    raw = params.get(key)
    if raw:
      cp = _car_params_from_bytes(raw)
      if cp:
        return cp
  return None


def _load_car_params_from_cereal() -> dict[str, Any] | None:
  if messaging is None:
    return None
  try:
    sm = messaging.SubMaster(["carParams"])
    sm.update(2000)
    cp = sm["carParams"]
    if cp and cp.carFingerprint:
      return {
        "brand": cp.brand,
        "carFingerprint": cp.carFingerprint,
        "openpilotLongitudinalControl": bool(cp.openpilotLongitudinalControl),
      }
  except Exception as e:
    cloudlog.warning(f"cabana: failed to read live carParams: {e}")
  return None


def _load_car_params() -> dict[str, Any] | None:
  return _load_car_params_from_params() or _load_car_params_from_cereal()


def _list_dbc_names() -> list[str]:
  dbcs: list[str] = []
  if DBC_PATH:
    dbc_path = Path(DBC_PATH)
    if dbc_path.exists():
      dbcs.extend([p.stem for p in dbc_path.glob("*.dbc")])
  try:
    dbcs.extend(get_generated_dbcs().keys())
  except Exception:
    pass
  return sorted(set(dbcs))


_EN_TO_ZH_ALIASES: dict[str, list[str]] = {
  "toyota": ["丰田"],
  "lexus": ["雷克萨斯", "凌志"],
  "honda": ["本田"],
  "acura": ["讴歌"],
  "volkswagen": ["大众"],
  "audi": ["奥迪"],
  "tesla": ["特斯拉"],
  "subaru": ["斯巴鲁"],
  "nissan": ["日产"],
  "hyundai": ["现代"],
  "kia": ["起亚"],
  "ford": ["福特"],
  "mazda": ["马自达"],
  "bmw": ["宝马"],
  "mercedes": ["奔驰"],
  "chevrolet": ["雪佛兰"],
  "gmc": ["GMC"],
  "rivian": ["Rivian"],
  "corolla": ["卡罗拉"],
  "camry": ["凯美瑞"],
  "rav4": ["荣放"],
  "prius": ["普锐斯"],
  "highlander": ["汉兰达"],
  "civic": ["思域"],
  "accord": ["雅阁"],
  "crv": ["CRV"],
  "model3": ["model3"],
  "modely": ["modely"],
}

_dbc_catalog_cache: list[dict[str, Any]] | None = None


def _search_tokens(text: str) -> list[str]:
  return [t for t in re.split(r"[^a-z0-9\u4e00-\u9fff]+", (text or "").lower()) if len(t) >= 2]


def _append_zh_aliases(parts: set[str]) -> None:
  for token in list(parts):
    tl = token.lower()
    for en, zh_list in _EN_TO_ZH_ALIASES.items():
      if en in tl or tl == en:
        parts.add(en)
        parts.update(zh_list)


def _build_dbc_catalog() -> list[dict[str, Any]]:
  global _dbc_catalog_cache
  if _dbc_catalog_cache is not None:
    return _dbc_catalog_cache

  buckets: dict[str, dict[str, set[str]]] = defaultdict(
    lambda: {
      "brands": set(),
      "makes": set(),
      "models": set(),
      "fingerprints": set(),
      "labels": set(),
      "tokens": set(),
    }
  )

  if PLATFORMS:
    for fingerprint, platform in PLATFORMS.items():
      cfg = getattr(platform, "config", None)
      if cfg is None:
        continue

      dbc_names: set[str] = set()
      dbc_dict = getattr(cfg, "dbc_dict", None) or {}
      if isinstance(dbc_dict, dict):
        for val in dbc_dict.values():
          if val:
            dbc_names.add(str(val))

      doc_rows: list[tuple[str, str, str]] = []
      for doc in getattr(cfg, "car_docs", None) or []:
        name = getattr(doc, "name", "") or ""
        make = getattr(doc, "make", "") or ""
        model = getattr(doc, "model", "") or ""
        if name or make or model:
          doc_rows.append((name, make, model))

      brand_hint = ""
      if doc_rows and doc_rows[0][1]:
        brand_hint = doc_rows[0][1].lower()
      elif fingerprint:
        brand_hint = fingerprint.split()[0].lower()

      for dbc_name in dbc_names:
        bucket = buckets[dbc_name]
        if fingerprint:
          bucket["fingerprints"].add(fingerprint)
          bucket["tokens"].update(_search_tokens(fingerprint))
        if brand_hint:
          bucket["brands"].add(brand_hint)
          bucket["tokens"].add(brand_hint)
        for label, make, model in doc_rows:
          if label:
            bucket["labels"].add(label)
            bucket["tokens"].update(_search_tokens(label))
          if make:
            bucket["makes"].add(make.lower())
            bucket["tokens"].update(_search_tokens(make))
          if model:
            bucket["models"].add(model.lower())
            bucket["tokens"].update(_search_tokens(model))

  catalog: list[dict[str, Any]] = []
  for dbc_name in _list_dbc_names():
    bucket = buckets.get(dbc_name) or {
      "brands": set(),
      "makes": set(),
      "models": set(),
      "fingerprints": set(),
      "labels": set(),
      "tokens": set(),
    }
    tokens = set(bucket["tokens"])
    tokens.update(_search_tokens(dbc_name))
    _append_zh_aliases(tokens)

    labels = sorted(bucket["labels"])[:8]
    models = sorted(bucket["models"])[:12]
    makes = sorted(bucket["makes"])[:8]
    brands = sorted(bucket["brands"])[:8]
    fingerprints = sorted(bucket["fingerprints"])[:10]

    search_text = " ".join(sorted(tokens))
    catalog.append({
      "name": dbc_name,
      "brands": brands,
      "makes": makes,
      "models": models,
      "fingerprints": fingerprints,
      "labels": labels,
      "searchText": search_text,
    })

  _dbc_catalog_cache = catalog
  return catalog


def _get_dbc_dict(car_fingerprint: str) -> dict[str, str]:
  if not PLATFORMS or not car_fingerprint:
    return {}

  platform = PLATFORMS.get(car_fingerprint)
  if platform is None:
    fp_upper = car_fingerprint.upper()
    for key, candidate in PLATFORMS.items():
      if key.upper() == fp_upper:
        platform = candidate
        break
    if platform is None:
      for key, candidate in PLATFORMS.items():
        if fp_upper in key.upper() or key.upper() in fp_upper:
          platform = candidate
          break

  if platform is None:
    return {}

  cfg = getattr(platform, "config", None)
  if cfg is None:
    return {}
  return dict(getattr(cfg, "dbc_dict", {}))


def _pick_preferred_dbc(dbc_names: list[str]) -> str | None:
  if not dbc_names:
    return None
  for name in dbc_names:
    if "_pt" in name or name.endswith("_pt"):
      return name
  return dbc_names[0]


def _suggest_dbc_for_car(car: dict[str, Any]) -> str | None:
  dbc_dict = _get_dbc_dict(car.get("carFingerprint", ""))
  if dbc_dict:
    return _pick_preferred_dbc(list(dbc_dict.values()))

  fingerprint = (car.get("carFingerprint") or "").lower()
  brand = (car.get("brand") or "").lower()
  tokens = [t for t in re.split(r"[^a-z0-9]+", fingerprint) if len(t) >= 3]
  if brand:
    tokens.insert(0, brand)

  best_name = None
  best_score = 0
  for dbc_name in _list_dbc_names():
    dbc_lower = dbc_name.lower()
    score = 0
    for token in tokens:
      if token in dbc_lower:
        score += len(token)
    if "_pt" in dbc_lower:
      score += 3
    if score > best_score:
      best_score = score
      best_name = dbc_name
  return best_name if best_score > 0 else None


def _load_dbc_content(dbc_name: str) -> str | None:
  """Return raw DBC text for a given DBC name (generated or file)."""
  if DBC is None:
    return None
  try:
    generated = get_generated_dbcs()
    if dbc_name in generated:
      return generated[dbc_name]
  except Exception:
    pass
  dbc_path = Path(DBC_PATH) / f"{dbc_name}.dbc"
  if dbc_path.exists():
    return dbc_path.read_text()
  return None


_SG_UNIT_RE = re.compile(r'^SG_\s+\w+.*?\)\s+\[[^\]]+\]\s+"([^"]*)"')


def _extract_units(content: str) -> dict[tuple[int, str], str]:
  """Map (address, signal_name) -> unit string from raw DBC lines."""
  units: dict[tuple[int, str], str] = {}
  address = 0
  for line in content.splitlines():
    line = line.strip()
    if line.startswith("BO_ "):
      parts = line.split()
      if len(parts) >= 2:
        try:
          address = int(parts[1], 0)
        except ValueError:
          pass
    elif line.startswith("SG_ "):
      m = _SG_UNIT_RE.match(line)
      if m:
        sig_name = line.split()[1]
        units[(address, sig_name)] = m.group(1)
  return units


def _parse_dbc_signals(dbc_name: str) -> list[dict[str, Any]]:
  if DBC is None:
    return []
  try:
    dbc = DBC(dbc_name)
  except Exception:
    return []
  content = _load_dbc_content(dbc_name)
  units = _extract_units(content) if content else {}
  signals = []
  for addr, msg in dbc.msgs.items():
    for sig_name, sig in msg.sigs.items():
      signals.append({
        "address": addr,
        "message": msg.name,
        "signal": sig_name,
        "start_bit": sig.start_bit,
        "size": sig.size,
        "little_endian": sig.is_little_endian,
        "signed": sig.is_signed,
        "factor": sig.factor,
        "offset": sig.offset,
        "unit": units.get((addr, sig_name), ""),
      })
  return signals


# -----------------------------------------------------------------------------
# Live CAN broadcasting
# -----------------------------------------------------------------------------

class LiveCanBroadcaster:
  def __init__(self):
    self._clients: set[web.WebSocketResponse] = set()
    self._task: asyncio.Task | None = None
    self._sm: Any = None
    self._latest: dict[tuple[int, int], dict[str, Any]] = {}
    self._last_send = 0.0
    self._send_interval = 0.05  # 20 Hz — enough for live view, avoids WS flood

  def start(self):
    if self._task is not None:
      return
    try:
      self._sm = messaging.SubMaster(["can"])
    except Exception as e:
      cloudlog.error(f"cabana: failed to create SubMaster: {e}")
      return
    self._task = asyncio.create_task(self._loop())

  async def _loop(self):
    while True:
      if self._sm is None or not self._clients:
        await asyncio.sleep(0.1)
        continue
      try:
        self._sm.update(100)
        if self._sm.updated["can"]:
          mono = time.monotonic()
          for cf in self._sm["can"]:
            key = (int(cf.src), int(cf.address))
            self._latest[key] = _can_frame_to_dict(cf, mono)

        now = time.monotonic()
        if self._latest and now - self._last_send >= self._send_interval:
          frames = list(self._latest.values())
          payload = json.dumps({"type": "can", "frames": frames})
          dead = set()
          for ws in self._clients:
            try:
              await ws.send_str(payload)
            except Exception:
              dead.add(ws)
          self._clients -= dead
          self._last_send = now
        else:
          await asyncio.sleep(0.01)
      except Exception as e:
        cloudlog.error(f"cabana: broadcaster error: {e}")
        await asyncio.sleep(0.5)

  def add(self, ws: web.WebSocketResponse):
    self._clients.add(ws)
    self.start()

  def remove(self, ws: web.WebSocketResponse):
    self._clients.discard(ws)


LIVE_CAN = LiveCanBroadcaster()


# -----------------------------------------------------------------------------
# Route / qlog helpers
# -----------------------------------------------------------------------------

def _get_routes_dir() -> Path | None:
  candidates = [
    Path("/data/media/0/realdata"),
    Path("/data/realdata"),
  ]
  try:
    from openpilot.common.basedir import BASEDIR
    candidates.append(Path(BASEDIR) / "data" / "media" / "0" / "realdata")
    candidates.append(Path(BASEDIR) / "data" / "realdata")
  except Exception:
    pass
  for p in candidates:
    if p.exists():
      return p
  return None


def _find_qlogs(route_dir: Path) -> list[Path]:
  """Find qlog files in a route directory (flat or per-segment layout)."""
  found: set[Path] = set()
  for path in route_dir.rglob("qlog*"):
    if _is_can_log_file(path, "qlog"):
      found.add(path)
  return sorted(found)


def _find_rlogs(route_dir: Path) -> list[Path]:
  """Find rlog files when qlog has no / too few CAN frames."""
  found: set[Path] = set()
  for path in route_dir.rglob("rlog*"):
    if _is_can_log_file(path, "rlog"):
      found.add(path)
  return sorted(found)


def _is_can_log_file(path: Path, prefix: str) -> bool:
  if not path.is_file():
    return False
  name = path.name
  if name.endswith(".lock"):
    return False
  if not name.startswith(prefix):
    return False
  try:
    if path.stat().st_size == 0:
      return False
  except OSError:
    return False
  return True


MAX_REPLAY_FRAMES = 25_000
REPLAY_SNAPSHOT_INTERVAL = 0.25  # ~4 Hz UI updates (delta per address)
REPLAY_MAX_SNAPSHOT_FRAMES = 96
REPLAY_BURST_BATCHES = 2
REPLAY_START_BUFFER = 32
REPLAY_STREAM_BATCH = 32
REPLAY_FRAME_QUEUE_SIZE = 64
CACHE_VERSION = 2
# qlog is heavily decimated; caches above this are almost certainly mis-tagged rlog data.
QLOG_CACHE_MAX_FRAMES = 8_000


def _cabana_cache_dir() -> Path:
  from ai.system.paths import openpilot_root

  candidates = [
    openpilot_root() / "ai" / "cabana_cache",
  ]
  try:
    from openpilot.common.basedir import BASEDIR
    candidates.append(Path(BASEDIR) / "data" / "cabana_cache")
  except Exception:
    pass
  candidates.append(Path(__file__).resolve().parent.parent / "data" / "cabana_cache")
  for p in candidates:
    try:
      p.mkdir(parents=True, exist_ok=True)
      return p
    except Exception:
      continue
  return candidates[-1]


def _route_cache_file(route_path: Path) -> Path:
  try:
    mtime = int(route_path.stat().st_mtime)
  except OSError:
    mtime = 0
  digest = hashlib.sha1(route_path.name.encode("utf-8")).hexdigest()[:12]
  return _cabana_cache_dir() / f"{digest}_{mtime}_v{CACHE_VERSION}.json.gz"


def _threadsafe_queue_put(queue: asyncio.Queue[Any], item: Any, loop: asyncio.AbstractEventLoop) -> None:
  """Block the worker thread until the batch is queued (never drop frames)."""
  fut = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
  fut.result(timeout=900)


def _compact_can_batch(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Keep latest frame per bus+address — enough for the replay table, fewer WS payloads."""
  latest: dict[tuple[int, int], dict[str, Any]] = {}
  for frame in frames:
    latest[(int(frame["bus"]), int(frame["address"]))] = frame
  return list(latest.values())


def _build_replay_snapshots(
  frames: list[dict[str, Any]],
  *,
  interval: float = REPLAY_SNAPSHOT_INTERVAL,
) -> list[tuple[float, list[dict[str, Any]]]]:
  """Timeline of CAN deltas: only addresses that changed since last snapshot."""
  if not frames:
    return []
  latest: dict[tuple[int, int], dict[str, Any]] = {}
  prev_sig: dict[tuple[int, int], tuple[float, str]] = {}
  first_t = float(frames[0]["time"])
  last_t = float(frames[-1]["time"])
  snapshots: list[tuple[float, list[dict[str, Any]]]] = []
  next_emit = first_t
  i = 0
  n = len(frames)

  def emit_delta(progress: float) -> None:
    delta: list[dict[str, Any]] = []
    for key, frame in latest.items():
      sig = (float(frame["time"]), str(frame.get("data", "")))
      if prev_sig.get(key) != sig:
        prev_sig[key] = sig
        delta.append(frame)
    if not delta and not snapshots:
      delta = list(latest.values())[:REPLAY_MAX_SNAPSHOT_FRAMES]
      for key, frame in latest.items():
        prev_sig[key] = (float(frame["time"]), str(frame.get("data", "")))
    if delta:
      if len(delta) > REPLAY_MAX_SNAPSHOT_FRAMES:
        delta = delta[:REPLAY_MAX_SNAPSHOT_FRAMES]
      snapshots.append((progress, delta))
    elif snapshots:
      # Keep timeline ticks so the scrubber advances even when CAN is sparse.
      snapshots.append((progress, []))

  while i < n or next_emit <= last_t + 1e-6:
    while i < n and float(frames[i]["time"]) <= next_emit + 1e-6:
      f = frames[i]
      latest[(int(f["bus"]), int(f["address"]))] = f
      i += 1
    if latest:
      emit_delta(next_emit - first_t)
    next_emit += interval
    if i >= n and next_emit > last_t + interval:
      break

  if frames and snapshots:
    final_p = last_t - first_t
    if snapshots[-1][0] < final_p - interval * 0.25:
      emit_delta(final_p)
  return snapshots


def _replay_log_paths(qlogs: list[Path], rlogs: list[Path], *, full: bool) -> tuple[list[Path], str]:
  """Default fast path: qlog only (no video, no full rlog). full=1 reads qlog+rlog or rlog."""
  if full:
    if qlogs and rlogs:
      return qlogs + rlogs, "rlog"
    if rlogs:
      return rlogs, "rlog"
    return qlogs, "qlog"
  if qlogs:
    return qlogs, "qlog"
  return rlogs, "rlog"


def _load_route_cache(route_path: Path, *, want_full: bool) -> list[dict[str, Any]] | None:
  path = _route_cache_file(route_path)
  if not path.is_file():
    return None
  try:
    raw = gzip.decompress(path.read_bytes())
    data = json.loads(raw.decode("utf-8"))
    if bool(data.get("full")) != want_full:
      return None
    frames = data.get("frames")
    if not isinstance(frames, list) or not frames:
      return None
    if not want_full and len(frames) > QLOG_CACHE_MAX_FRAMES:
      return None
    return frames
  except Exception:
    return None


def _save_route_cache(
  route_path: Path,
  frames: list[dict[str, Any]],
  *,
  decimated: bool,
  full: bool = True,
) -> None:
  path = _route_cache_file(route_path)
  try:
    payload = json.dumps({
      "version": CACHE_VERSION,
      "route": route_path.name,
      "decimated": decimated,
      "full": full,
      "frames": frames,
    }, separators=(",", ":")).encode("utf-8")
    path.write_bytes(gzip.compress(payload, compresslevel=3))
  except Exception as e:
    cloudlog.warning(f"cabana: cache write failed: {e}")


def _read_can_from_log(log_path: Path) -> list[dict[str, Any]]:
  frames: list[dict[str, Any]] = []
  if LogReader is None:
    return frames
  try:
    lr = LogReader(str(log_path))
  except Exception:
    return frames
  can_seen = 0
  stride = 1
  for msg in lr:
    if msg.which() != "can":
      continue
    mono = msg.logMonoTime / 1e9
    for cf in msg.can:
      can_seen += 1
      if can_seen > MAX_REPLAY_FRAMES * 2:
        stride = max(stride, can_seen // MAX_REPLAY_FRAMES)
      if can_seen % stride != 0:
        continue
      frames.append(_can_frame_to_dict(cf, mono))
  return frames


def _collect_can_frames(
  log_paths: list[Path],
  progress_cb: Any | None = None,
) -> tuple[list[dict[str, Any]], bool]:
  if LogReader is None or not log_paths:
    return [], False

  decimated = False
  last_report = time.monotonic()
  parts: list[list[dict[str, Any]]] = []

  def report(file_name: str, msgs: int, can_frames: int, phase: str = "scanning") -> None:
    nonlocal last_report
    if not progress_cb:
      return
    now = time.monotonic()
    if now - last_report < 0.5:
      return
    last_report = now
    progress_cb({
      "phase": phase,
      "file": file_name,
      "msgs": msgs,
      "can_frames": can_frames,
    })

  if len(log_paths) == 1:
    frames = _read_can_from_log(log_paths[0])
    report(log_paths[0].name, 0, len(frames))
    parts.append(frames)
  else:
    workers = min(4, len(log_paths))
    with ThreadPoolExecutor(max_workers=workers) as pool:
      futures = {pool.submit(_read_can_from_log, p): p for p in log_paths}
      done = 0
      total_can = 0
      for fut in as_completed(futures):
        path = futures[fut]
        done += 1
        try:
          chunk = fut.result()
        except Exception as e:
          if progress_cb:
            progress_cb({"phase": "error", "file": path.name, "error": str(e)})
          chunk = []
        total_can += len(chunk)
        parts.append(chunk)
        report(path.name, done, total_can, phase="parallel")

  all_frames = [f for chunk in parts for f in chunk]
  all_frames.sort(key=lambda f: f["time"])
  if len(all_frames) > MAX_REPLAY_FRAMES:
    stride = max(1, len(all_frames) // MAX_REPLAY_FRAMES)
    all_frames = all_frames[::stride]
    decimated = True
  return all_frames, decimated


def _iter_can_batches(log_paths: list[Path], batch_size: int = REPLAY_STREAM_BATCH):
  """Yield decimated CAN frame batches while reading (enables early playback)."""
  if LogReader is None:
    return
  can_seen = 0
  stride = 1
  batch: list[dict[str, Any]] = []
  for log_path in log_paths:
    try:
      lr = LogReader(str(log_path))
    except Exception:
      continue
    for msg in lr:
      if msg.which() != "can":
        continue
      mono = msg.logMonoTime / 1e9
      for cf in msg.can:
        can_seen += 1
        if can_seen > MAX_REPLAY_FRAMES * 2:
          stride = max(stride, can_seen // MAX_REPLAY_FRAMES)
        if can_seen % stride != 0:
          continue
        batch.append(_can_frame_to_dict(cf, mono))
        if len(batch) >= batch_size:
          yield log_path.name, batch
          batch = []
  if batch:
    yield log_path.name, batch


def _route_dir(route_name: str) -> Path | None:
  if not route_name or "/" in route_name or "\\" in route_name or ".." in route_name:
    return None
  routes_dir = _get_routes_dir()
  if routes_dir is None:
    return None
  base = routes_dir / route_name
  return base if base.is_dir() else None


def _list_route_media(route_name: str) -> dict[str, Any]:
  base = _route_dir(route_name)
  if base is None:
    return {"ok": False, "error": "Route not found"}

  segments: list[dict[str, Any]] = []
  for path in sorted(base.rglob("*")):
    if not path.is_file():
      continue
    low = path.name.lower()
    if low not in ("qcamera.ts", "fcamera.hevc", "ecamera.hevc", "dcamera.hevc"):
      continue
    rel = path.relative_to(base).as_posix()
    seg = path.parent.name if path.parent != base else "0"
    cam_type = "qcamera" if low == "qcamera.ts" else "hevc"
    segments.append({
      "segment": seg,
      "type": cam_type,
      "filename": path.name,
      "rel_path": rel,
    })

  preferred = next((s for s in segments if s["type"] == "qcamera"), segments[0] if segments else None)
  return {"ok": True, "route": route_name, "segments": segments, "preferred": preferred}


def _media_payload(route_name: str) -> dict[str, Any]:
  result = _list_route_media(route_name)
  if not result.get("ok"):
    return result
  for seg in result.get("segments", []):
    rel = quote(seg["rel_path"], safe="")
    seg["url"] = f"/api/cabana/route/{quote(route_name, safe='')}/file?path={rel}"
  pref = result.get("preferred")
  if pref:
    rel = quote(pref["rel_path"], safe="")
    pref["url"] = f"/api/cabana/route/{quote(route_name, safe='')}/file?path={rel}"
  return result


_ROUTE_DATETIME_RE = re.compile(
  r"^(?P<date>\d{4}-\d{2}-\d{2})--(?P<time>\d{2}-\d{2}-\d{2})",
)


def _route_datetime_from_name(
  name: str,
  *,
  display_tz: Any | None = None,
) -> datetime | None:
  """Parse route folder timestamp (UTC) and optionally convert for display."""
  m = _ROUTE_DATETIME_RE.match(name)
  if not m:
    return None
  try:
    dt_utc = datetime.strptime(
      f"{m.group('date')} {m.group('time').replace('-', ':')}",
      "%Y-%m-%d %H:%M:%S",
    ).replace(tzinfo=timezone.utc)
    if display_tz is not None:
      return dt_utc.astimezone(display_tz)
    return dt_utc
  except ValueError:
    return None


def _route_sort_ts(route_path: Path) -> float:
  dt = _route_datetime_from_name(route_path.name)
  if dt is not None:
    return dt.timestamp()
  try:
    return route_path.stat().st_mtime
  except OSError:
    return 0.0


def _route_date_label(route_path: Path, *, display_tz: Any) -> str:
  dt = _route_datetime_from_name(route_path.name, display_tz=display_tz)
  if dt is not None:
    return dt.strftime("%Y-%m-%d %H:%M")
  try:
    return datetime.fromtimestamp(route_path.stat().st_mtime, tz=display_tz).strftime("%Y-%m-%d %H:%M")
  except OSError:
    return ""


def _list_routes(params: Params | None = None) -> list[dict[str, Any]]:
  from ai.timezone_util import get_route_timezone, read_ai_timezone_name

  p = params or Params()
  display_tz = get_route_timezone(p)
  routes_dir = _get_routes_dir()
  if routes_dir is None:
    return []
  routes = []
  entries = [e for e in routes_dir.iterdir() if e.is_dir()]
  entries.sort(key=_route_sort_ts, reverse=True)
  for entry in entries:
    qlog = _find_qlogs(entry)
    rlog = _find_rlogs(entry)
    if not qlog and not rlog:
      continue
    routes.append({
      "name": entry.name,
      "path": str(entry),
      "date": _route_date_label(entry, display_tz=display_tz),
      "timezone": read_ai_timezone_name(p),
      "has_qlog": len(qlog) > 0,
      "has_rlog": len(rlog) > 0,
      "qlogs": [str(p) for p in qlog[:5]],
      "rlogs": [str(p) for p in rlog[:3]],
    })
  return routes


# -----------------------------------------------------------------------------
# API handlers
# -----------------------------------------------------------------------------

async def api_car(request: web.Request) -> web.Response:
  cp = _load_car_params()
  if cp is None:
    return _json_response({
      "ok": False,
      "error": "CarParams not available",
      "hint": "Drive once or set CarParams on device, then refresh.",
    }, status=404)

  dbc_dict = _get_dbc_dict(cp.get("carFingerprint", ""))
  suggested_dbc = _pick_preferred_dbc(list(dbc_dict.values())) if dbc_dict else _suggest_dbc_for_car(cp)
  return _json_response({
    "ok": True,
    "car": cp,
    "dbc_dict": dbc_dict,
    "suggested_dbc": suggested_dbc,
  })


async def api_dbcs(request: web.Request) -> web.Response:
  if DBC_PATH is None or not DBC_PATH:
    return _json_response({"ok": False, "error": "opendbc not available"}, status=503)
  catalog = _build_dbc_catalog()
  return _json_response({
    "ok": True,
    "dbcs": [item["name"] for item in catalog],
    "catalog": catalog,
  })


async def api_dbc(request: web.Request) -> web.Response:
  name = request.match_info["name"]
  if DBC is None:
    return _json_response({"ok": False, "error": "opendbc DBC parser not available"}, status=503)
  signals = _parse_dbc_signals(name)
  return _json_response({"ok": True, "name": name, "signals": signals})


async def api_route_media(request: web.Request) -> web.Response:
  name = request.match_info["name"]
  result = _media_payload(name)
  if not result.get("ok"):
    return _json_response(result, status=404)
  return _json_response(result)


async def api_route_summary(request: web.Request) -> web.Response:
  from ai.tools.diagnostics_tools import analyze_route_summary
  name = request.match_info["name"]
  return _json_response(analyze_route_summary(name))


async def api_route_file(request: web.Request) -> web.Response:
  name = request.match_info["name"]
  rel = request.query.get("path", "")
  if not rel or ".." in rel.replace("\\", "/"):
    return _json_response({"ok": False, "error": "Invalid path"}, status=400)
  base = _route_dir(name)
  if base is None:
    return _json_response({"ok": False, "error": "Route not found"}, status=404)
  target = (base / rel).resolve()
  try:
    if not str(target).startswith(str(base.resolve())):
      return _json_response({"ok": False, "error": "Forbidden"}, status=403)
  except Exception:
    return _json_response({"ok": False, "error": "Forbidden"}, status=403)
  if not target.is_file():
    return _json_response({"ok": False, "error": "File not found"}, status=404)
  return web.FileResponse(target)


async def api_routes(request: web.Request) -> web.Response:
  from ai.timezone_util import read_ai_timezone_name

  params = Params()
  tz_name = read_ai_timezone_name(params)
  return _json_response({
    "ok": True,
    "routes": _list_routes(params),
    "route_timezone": tz_name,
  })


async def ws_live(request: web.Request) -> web.WebSocketResponse:
  ws = web.WebSocketResponse()
  await ws.prepare(request)
  LIVE_CAN.add(ws)
  try:
    async for _ in ws:
      pass
  finally:
    LIVE_CAN.remove(ws)
  return ws


async def ws_offline(request: web.Request) -> web.WebSocketResponse:
  ws = web.WebSocketResponse()
  await ws.prepare(request)

  async def ws_send(payload: dict[str, Any]) -> bool:
    try:
      await ws.send_str(json.dumps(payload, separators=(",", ":")))
      return True
    except (ConnectionResetError, asyncio.CancelledError):
      return False
    except Exception as e:
      if e.__class__.__name__ == "ClientConnectionResetError":
        return False
      raise

  if LogReader is None:
    await ws_send({"type": "error", "error": "LogReader not available"})
    await ws.close()
    return ws

  route = request.query.get("route", "")
  routes_dir = _get_routes_dir()
  if not route or routes_dir is None:
    await ws.send_str(json.dumps({"type": "error", "error": "No route specified"}))
    await ws.close()
    return ws

  route_path = routes_dir / route
  if route_path.is_dir():
    qlogs = _find_qlogs(route_path)
    rlogs = _find_rlogs(route_path)
  else:
    qlogs = [route_path] if route_path.is_file() else []
    rlogs = []

  if not qlogs and not rlogs:
    await ws.send_str(json.dumps({
      "type": "error",
      "error": "No qlog/rlog found in route",
      "hint": "This folder has no driving logs (e.g. boot/ is not a route). Pick a route with qlog or rlog.",
    }))
    await ws.close()
    return ws

  speed = float(request.query.get("speed", "1.0"))
  start_time = float(request.query.get("start_time", "0"))
  autoplay = request.query.get("autoplay", "1").lower() in ("1", "true", "yes")
  full_can = request.query.get("full", "0").lower() in ("1", "true", "yes")
  paused = not autoplay
  seek_time: float | None = None

  async def control_loop():
    nonlocal paused, speed, seek_time
    async for msg in ws:
      try:
        data = json.loads(msg.data)
        cmd = data.get("action")
        if cmd == "pause":
          paused = True
        elif cmd == "play":
          paused = False
        elif cmd == "speed":
          speed = max(0.1, min(10.0, float(data.get("value", 1.0))))
        elif cmd == "seek":
          seek_time = max(0.0, float(data.get("time", 0.0)))
      except Exception:
        pass

  control_task = asyncio.create_task(control_loop())
  loop = asyncio.get_running_loop()
  progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

  def progress_cb(payload: dict[str, Any]) -> None:
    loop.call_soon_threadsafe(progress_queue.put_nowait, payload)

  stream_paths, source = _replay_log_paths(qlogs, rlogs, full=full_can)
  frame_queue: asyncio.Queue[Any] | None = None
  reader_task: asyncio.Task[Any] | None = None
  load_complete = asyncio.Event()
  streaming_load = False

  async def progress_reporter() -> None:
    if not await ws_send({
      "type": "loading",
      "phase": "start",
      "source": source,
      "files": len(stream_paths),
      "qlogs": len(qlogs),
      "rlogs": len(rlogs),
    }):
      return
    while True:
      try:
        payload = await asyncio.wait_for(progress_queue.get(), timeout=0.45)
        if not await ws_send({"type": "loading", **payload}):
          return
      except asyncio.TimeoutError:
        if not await ws_send({"type": "loading", "phase": "scanning", "heartbeat": True}):
          return

  async def drain_stream_queue() -> None:
    nonlocal all_frames
    if frame_queue is None:
      load_complete.set()
      return
    while True:
      item = await frame_queue.get()
      if item is None:
        break
      if isinstance(item, tuple) and item[0] == "error":
        raise RuntimeError(item[1])
      all_frames.extend(item)
    if reader_task is not None:
      await reader_task
    load_complete.set()
    if streaming_load and all_frames:
      await ws.send_str(json.dumps({
        "type": "metadata_update",
        "duration": all_frames[-1]["time"] - all_frames[0]["time"],
        "frame_count": len(all_frames),
      }))

  async def load_replay_frames() -> tuple[list[dict[str, Any]], bool, str, bool]:
    nonlocal frame_queue, reader_task, streaming_load
    if route_path.is_dir():
      cached = await loop.run_in_executor(
        None, lambda: _load_route_cache(route_path, want_full=full_can),
      )
      if cached:
        progress_cb({"phase": "cache_hit", "can_frames": len(cached)})
        return cached, False, source, True

    # Default fast path: qlog-only, read in one pass (no background drain / no rlog).
    if not full_can and source == "qlog":

      def read_qlog_only() -> tuple[list[dict[str, Any]], bool]:
        progress_cb({"phase": "fast_qlog", "files": len(stream_paths), "parallel": len(stream_paths) > 1})
        frames, dec = _collect_can_frames(stream_paths, progress_cb)
        progress_cb({"phase": "ready", "can_frames": len(frames)})
        if route_path.is_dir() and frames:
          _save_route_cache(route_path, frames, decimated=dec, full=False)
        return frames, dec

      frames, dec = await loop.run_in_executor(None, read_qlog_only)
      return frames, dec, source, False

    frame_queue = asyncio.Queue(maxsize=REPLAY_FRAME_QUEUE_SIZE)
    streaming_load = True

    def stream_logs() -> None:
      collected: list[dict[str, Any]] = []
      can_total = 0
      decimated_local = False
      try:
        progress_cb({
          "phase": "fast_rlog" if source == "rlog" else "qlog",
          "files": len(stream_paths),
          "parallel": len(stream_paths) > 1,
        })
        for file_name, batch in _iter_can_batches(stream_paths):
          collected.extend(batch)
          can_total += len(batch)
          progress_cb({"phase": "scanning", "file": file_name, "can_frames": can_total})
          _threadsafe_queue_put(frame_queue, batch, loop)
        collected.sort(key=lambda f: f["time"])
        if len(collected) > MAX_REPLAY_FRAMES:
          stride = max(1, len(collected) // MAX_REPLAY_FRAMES)
          collected = collected[::stride]
          decimated_local = True
        if route_path.is_dir() and collected:
          _save_route_cache(route_path, collected, decimated=decimated_local, full=full_can)
      except Exception as e:
        _threadsafe_queue_put(frame_queue, ("error", str(e)), loop)
      finally:
        _threadsafe_queue_put(frame_queue, None, loop)

    reader_task = loop.run_in_executor(None, stream_logs)
    partial: list[dict[str, Any]] = []
    while len(partial) < REPLAY_START_BUFFER:
      item = await frame_queue.get()
      if item is None:
        break
      if isinstance(item, tuple) and item[0] == "error":
        raise RuntimeError(item[1])
      partial.extend(item)
    return partial, False, source, False

  all_frames: list[dict[str, Any]] = []
  decimated = False
  from_cache = False

  reporter_task = asyncio.create_task(progress_reporter())
  try:
    all_frames, decimated, source, from_cache = await load_replay_frames()
  finally:
    reporter_task.cancel()
    try:
      await reporter_task
    except asyncio.CancelledError:
      pass

  drain_task: asyncio.Task[None] | None = None
  if streaming_load:
    drain_task = asyncio.create_task(drain_stream_queue())
  else:
    load_complete.set()

  try:
    if drain_task is not None:
      await load_complete.wait()

    if not all_frames:
      tried = []
      if qlogs:
        tried.append(f"qlog×{len(qlogs)}")
      if rlogs:
        tried.append(f"rlog×{len(rlogs)}")
      detail = ", ".join(tried) if tried else "no logs"
      await ws.send_str(json.dumps({
        "type": "error",
        "error": f"No CAN frames found ({detail}). qlog is heavily decimated; ensure rlog exists.",
      }))
      await ws.close()
      return ws

    first_time = all_frames[0]["time"]
    last_time = all_frames[-1]["time"]
    duration = last_time - first_time
    original_count = len(all_frames)

    await ws.send_str(json.dumps({
      "type": "loading",
      "phase": "ready",
      "can_frames": len(all_frames),
      "original_frame_count": original_count,
    }))

    snapshots = await loop.run_in_executor(
      None, lambda: _build_replay_snapshots(all_frames),
    )

    await ws.send_str(json.dumps({
      "type": "metadata",
      "duration": duration,
      "frame_count": len(all_frames),
      "original_frame_count": original_count,
      "decimated": decimated,
      "start_time": first_time,
      "source": source,
      "cached": from_cache,
      "full_can": full_can,
      "has_rlog": bool(rlogs),
      "streaming": False,
      "snapshots": len(snapshots),
    }))

    snap_idx = 0
    while snap_idx < len(snapshots) and snapshots[snap_idx][0] < start_time:
      snap_idx += 1

    if snap_idx < len(snapshots):
      init_progress, init_batch = snapshots[snap_idx]
      if init_batch:
        await ws_send({
          "type": "can",
          "frames": init_batch,
          "progress": init_progress,
          "preview": True,
        })

    playback_start = time.monotonic()
    first_snap_progress = snapshots[snap_idx][0] if snap_idx < len(snapshots) else 0.0

    while snap_idx < len(snapshots):
      if seek_time is not None:
        st = seek_time
        seek_time = None
        snap_idx = 0
        while snap_idx < len(snapshots) and snapshots[snap_idx][0] < st:
          snap_idx += 1
        playback_start = time.monotonic()
        first_snap_progress = snapshots[snap_idx][0] if snap_idx < len(snapshots) else st
        await ws.send_str(json.dumps({"type": "seeked", "time": st}))
        continue

      progress, ui_batch = snapshots[snap_idx]
      rel = (progress - first_snap_progress) / max(speed, 0.01)
      target = playback_start + rel
      while time.monotonic() < target and not paused:
        await asyncio.sleep(0.01)
      if paused:
        paused_at = time.monotonic()
        while paused:
          await asyncio.sleep(0.05)
        playback_start += time.monotonic() - paused_at
        first_snap_progress = progress

      if not ui_batch:
        if not await ws_send({
          "type": "can",
          "frames": [],
          "progress": progress,
        }):
          break
        snap_idx += 1
        continue

      if not await ws_send({
        "type": "can",
        "frames": ui_batch,
        "progress": progress,
      }):
        break
      snap_idx += 1
      await asyncio.sleep(0)

    await ws_send({"type": "done"})
  except Exception as e:
    await ws_send({"type": "error", "error": str(e)})
  finally:
    if drain_task is not None:
      drain_task.cancel()
      try:
        await drain_task
      except (asyncio.CancelledError, Exception):
        pass
    control_task.cancel()
    try:
      await control_task
    except asyncio.CancelledError:
      pass
    await ws.close()
  return ws


# Short functional labels for Cabana table (2–8 Chinese chars); rules checked in order.
_SIGNAL_LABEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
  (re.compile(r"brake|brk|brakepressed|brakelight", re.I), "刹车"),
  (re.compile(r"gas.?pedal|gas_pedal|throttle|pedal", re.I), "油门"),
  (re.compile(r"acc_?control|adaptive|cruise", re.I), "巡航"),
  (re.compile(r"steer|steering|steer_|angle_sensor|_lka|lkas|eps", re.I), "转向"),
  (re.compile(r"wheel.*speed|veh.*spd|vehicle.?speed|wheel_speed", re.I), "车速"),
  (re.compile(r"gear|shifter|trans", re.I), "档位"),
  (re.compile(r"turn|blink|indicator", re.I), "转向灯"),
  (re.compile(r"wiper", re.I), "雨刷"),
  (re.compile(r"door|hood|trunk", re.I), "车门"),
  (re.compile(r"seatbelt|buckle", re.I), "安全带"),
  (re.compile(r"esp|abs|stability|yaw", re.I), "稳定"),
  (re.compile(r"rpm|engine.?speed", re.I), "转速"),
  (re.compile(r"battery|hv|12v|volt", re.I), "电源"),
  (re.compile(r"temp|coolant", re.I), "温度"),
  (re.compile(r"fuel", re.I), "油量"),
  (re.compile(r"odometer|mileage", re.I), "里程"),
  (re.compile(r"park|epb|handbrake", re.I), "驻车"),
  (re.compile(r"horn", re.I), "喇叭"),
  (re.compile(r"light|headlamp|beam", re.I), "灯光"),
  (re.compile(r"radar|lead|dist|pre_collision|fcw", re.I), "雷达"),
  (re.compile(r"pcm|powertrain|engine", re.I), "动力"),
  (re.compile(r"hybrid|hev", re.I), "混动"),
  (re.compile(r"torque", re.I), "扭矩"),
  (re.compile(r"secoc|auth|mac_sync", re.I), "认证"),
  (re.compile(r"button|switch|btn|cancel", re.I), "按键"),
  (re.compile(r"display|hud|cluster", re.I), "仪表"),
  (re.compile(r"airbag|srs", re.I), "气囊"),
]


def _guess_signal_label(message: str, signal: str) -> str | None:
  hay = f"{message} {signal}"
  for pat, label in _SIGNAL_LABEL_PATTERNS:
    if pat.search(hay):
      return label
  return None


def _normalize_cabana_lang(lang: str) -> str:
  lang = (lang or "").strip().lower()
  if lang.startswith("zh"):
    return "zh"
  return "en"


def _cabana_analyze_system(lang: str) -> str:
  if _normalize_cabana_lang(lang) == "zh":
    return (
      "你是 CAN 总线分析助手。仅用简体中文回答。"
      "简洁列出关键报文功能（刹车、油门、车速、转向等）和异常；不要输出思考过程或英文。"
      "直接给出最终结论，不要复述用户要求。"
    )
  return (
    "You are a CAN bus analysis assistant. Reply only in English. "
    "Briefly list key message roles (brake, throttle, speed, steering, etc.) and anomalies. "
    "Output the final answer only — no chain-of-thought and no restating the prompt."
  )


def _cabana_explain_system(lang: str) -> str:
  if _normalize_cabana_lang(lang) == "zh":
    return (
      "你是汽车 CAN 报文标注助手。只输出 JSON 对象，键为输入 id，值为 2-6 个汉字的功能标签。"
      "例如：刹车、油门、车速、转向、巡航、车身。禁止句子、禁止解释数值、禁止超过 6 字。"
    )
  return (
    "You are a CAN message labeling assistant. Output only a JSON object mapping each input id "
    "to a 2-8 character English function tag (e.g. Brake, Throttle, Speed, Steer, Cruise, Body). "
    "No sentences, no value explanations."
  )


def _apply_cabana_analyze_lang(messages: list[dict[str, Any]], lang: str) -> list[dict[str, Any]]:
  """Replace system prompt and ensure user-facing analyze replies match UI language."""
  rest = [m for m in messages if str(m.get("role", "")) != "system"]
  return [{"role": "system", "content": _cabana_analyze_system(lang)}, *rest]

_GENERIC_LABELS = frozenset({"车身", "其他"})
_LABEL_CACHE_KEY = "cabana_label_cache"
_LABEL_CACHE_MAX_PER_DBC = 600


def _load_label_cache_store() -> dict[str, dict[str, str]]:
  try:
    raw = Params().get(_LABEL_CACHE_KEY)
    if raw:
      if isinstance(raw, bytes):
        raw = raw.decode()
      data = json.loads(raw)
      if isinstance(data, dict):
        store = {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}
        return _scrub_generic_from_label_store(store)
  except Exception:
    pass
  return {}


def _scrub_generic_from_label_store(store: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
  changed = False
  for bucket in store.values():
    for key, label in list(bucket.items()):
      if label in _GENERIC_LABELS:
        del bucket[key]
        changed = True
  if changed:
    _save_label_cache_store(store)
  return store


def _save_label_cache_store(store: dict[str, dict[str, str]]) -> None:
  try:
    Params().put(_LABEL_CACHE_KEY, json.dumps(store, ensure_ascii=False))
  except Exception as e:
    cloudlog.error(f"cabana: save label cache failed: {e}")


def _label_cache_keys(message: str, item_id: str) -> list[str]:
  keys: list[str] = []
  msg = (message or "").strip()
  if msg:
    keys.append(msg.upper())
    keys.append(msg)
  if item_id:
    keys.append(item_id)
  return keys


def _lookup_cached_label(store: dict[str, str], message: str, item_id: str) -> str | None:
  for key in _label_cache_keys(message, item_id):
    label = store.get(key)
    if label:
      return str(label)[:8]
  return None


def _labels_for_dbc(dbc: str) -> dict[str, str]:
  if not dbc:
    return {}
  raw = dict(_load_label_cache_store().get(dbc, {}))
  return {k: v for k, v in raw.items() if v not in _GENERIC_LABELS}


def _cache_labels_for_items(dbc: str, items: list[dict[str, str]]) -> dict[str, str]:
  if not dbc:
    return {}
  store = _labels_for_dbc(dbc)
  out: dict[str, str] = {}
  for it in items:
    iid = str(it.get("id", ""))
    msg = str(it.get("message", ""))
    label = _lookup_cached_label(store, msg, iid)
    if label:
      out[iid] = label
  return out


def _persist_labels(dbc: str, items: list[dict[str, str]], labels: dict[str, str]) -> None:
  if not dbc or not labels:
    return
  store = _load_label_cache_store()
  bucket = store.setdefault(dbc, {})
  items_by_id = {str(it.get("id", "")): it for it in items}
  for iid, label in labels.items():
    if not label or label in _GENERIC_LABELS:
      continue
    it = items_by_id.get(iid, {})
    msg = str(it.get("message", ""))
    for key in _label_cache_keys(msg, iid):
      bucket[key] = str(label)[:8]
  if len(bucket) > _LABEL_CACHE_MAX_PER_DBC:
    # Drop oldest arbitrary keys (dict preserves insertion in py3.7+)
    extra = len(bucket) - _LABEL_CACHE_MAX_PER_DBC
    for key in list(bucket.keys())[:extra]:
      bucket.pop(key, None)
  store[dbc] = bucket
  _save_label_cache_store(store)


def _resolve_label_from_parsed(parsed: dict[str, str], item: dict[str, str]) -> str | None:
  iid = str(item.get("id", ""))
  msg = str(item.get("message", ""))
  for key in (iid, msg, msg.upper()):
    if key and key in parsed:
      return str(parsed[key])[:8]
  return None


def _parse_explain_labels_json(text: str) -> dict[str, str]:
  text = text.strip()
  if not text:
    return {}
  candidates = [text]
  m = re.search(r"\{[\s\S]*\}", text)
  if m:
    candidates.insert(0, m.group(0))
  for raw in candidates:
    try:
      data = json.loads(raw)
    except json.JSONDecodeError:
      continue
    if isinstance(data, dict):
      out: dict[str, str] = {}
      for k, v in data.items():
        if v is None:
          continue
        label = str(v).strip().replace("\n", " ")
        if label:
          out[str(k)] = label[:8]
      return out
  return {}


_REASONING_META_RE = re.compile(
  r"(?i)^(we need|need to|need output|let me|i will|user says|maybe\b|so provide|concisely\b|must analyze|should output|the user\b|i should|i'll\b)",
)


def _looks_like_reasoning_meta(text: str) -> bool:
  t = (text or "").strip()
  if not t:
    return True
  if _REASONING_META_RE.match(t):
    return True
  if re.search(r"(?i)\b(user says|need output|maybe not|so provide|concisely|thinking about)\b", t):
    return True
  return False


def _cabana_salvage_reasoning(reasoning: str, *, lang: str) -> str:
  """Extract user-facing prose from model reasoning; drop planning/meta lines."""
  reasoning = reasoning.strip()
  if not reasoning:
    return ""
  chunks = [p.strip() for p in re.split(r"\n\s*\n", reasoning) if p.strip()]
  if not chunks:
    chunks = [ln.strip() for ln in reasoning.splitlines() if ln.strip()]

  best = ""
  best_score = 0
  for chunk in reversed(chunks):
    if _looks_like_reasoning_meta(chunk):
      continue
    zh_count = len(re.findall(r"[\u4e00-\u9fff]", chunk))
    if _normalize_cabana_lang(lang) == "zh":
      if zh_count < 4:
        continue
      score = zh_count
    else:
      if zh_count > max(4, len(chunk) // 3):
        continue
      score = len(chunk)
    if score > best_score:
      best_score = score
      best = chunk
  return best


def _cabana_finalize_ai_text(content: str, reasoning: str, *, allow_reasoning: bool, lang: str = "zh") -> str:
  """Prefer direct model content; optionally salvage user-facing text from reasoning."""
  text = content.strip()
  if text and not _looks_like_reasoning_meta(text):
    return text
  if not allow_reasoning:
    return ""
  salvaged = _cabana_salvage_reasoning(reasoning, lang=lang)
  if salvaged:
    return salvaged
  return ""


def _cabana_pick_ai_text(
  content: str,
  reasoning: str,
  *,
  allow_reasoning: bool,
  prefer_json: bool = False,
  lang: str = "zh",
) -> str:
  """Prefer direct model content; optionally salvage JSON or prose from reasoning."""
  content = content.strip()
  reasoning = reasoning.strip()
  if prefer_json:
    for blob in (content, reasoning):
      if blob and _parse_explain_labels_json(blob):
        match = re.search(r"\{[\s\S]*\}", blob)
        if match:
          return match.group(0)
  if content and not _looks_like_reasoning_meta(content):
    return content
  if not allow_reasoning:
    return ""
  return _cabana_finalize_ai_text("", reasoning, allow_reasoning=True, lang=lang)


def _cabana_ai_config():
  """Load AI config for Cabana."""
  from ai.client import load_config_from_params

  return load_config_from_params(Params())


async def _cabana_ai_complete(
  messages: list[dict[str, Any]],
  *,
  max_tokens: int = 2048,
  temperature: float = 0.5,
  use_reasoning_fallback: bool = False,
  prefer_json: bool = False,
  lang: str = "zh",
  timeout_total: float = 120,
  thinking_modes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
  """Run a read-only Cabana AI request (allowed while driving)."""
  from ai.client import chat_completion_collect, is_thinking_request_error

  config = _cabana_ai_config()
  if not config.is_configured:
    return {"ok": False, "error": config.configuration_error or "AI not configured"}

  if thinking_modes is None:
    primary = "user" if config.thinking_enabled else "omit"
    thinking_modes = (primary, "omit") if primary != "omit" else ("omit", "disabled")
  last_error = "Empty AI response"

  for mode in thinking_modes:
    content, reasoning, err = await chat_completion_collect(
      config,
      messages,
      temperature=temperature,
      max_tokens=max_tokens,
      thinking_mode=mode,
      timeout_total=timeout_total,
    )
    if err:
      if is_thinking_request_error(err):
        last_error = err
        continue
      return {"ok": False, "error": err}
    text = _cabana_pick_ai_text(
      content,
      reasoning,
      allow_reasoning=use_reasoning_fallback,
      prefer_json=prefer_json,
      lang=lang,
    )
    if text:
      return {"ok": True, "response": text}
    last_error = "Empty AI response"

  return {"ok": False, "error": last_error}


async def api_analyze(request: web.Request) -> web.Response:
  """Analyze CAN data using the configured AI provider (read-only)."""
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)

  lang = str(body.get("lang", "zh"))
  messages = body.get("messages", [])
  if not messages:
    question = str(body.get("question", "")).strip()
    if not question:
      return _json_response({"ok": False, "error": "messages or question required"}, status=400)
    context = str(body.get("context", "")).strip()
    frames_text = str(body.get("frames_text", "")).strip()
    user = question
    ctx_label = "Context" if _normalize_cabana_lang(lang) == "en" else "上下文"
    can_label = "CAN data" if _normalize_cabana_lang(lang) == "en" else "CAN 数据"
    if context:
      user += f"\n\n{ctx_label}:\n{context}"
    if frames_text:
      user += f"\n\n{can_label}:\n{frames_text}"
    messages = [
      {"role": "system", "content": _cabana_analyze_system(lang)},
      {"role": "user", "content": user},
    ]
  else:
    messages = _apply_cabana_analyze_lang(messages, lang)
  if not messages:
    return _json_response({"ok": False, "error": "messages required"}, status=400)

  try:
    config = _cabana_ai_config()
    analyze_mode = "user" if config.thinking_enabled else "omit"
    result = await _cabana_ai_complete(
      messages,
      max_tokens=2048,
      use_reasoning_fallback=True,
      lang=lang,
      timeout_total=300,
      thinking_modes=(analyze_mode,),
    )
    if not result.get("ok"):
      return _json_response(result, status=502)
    return _json_response(result)
  except Exception as e:
    cloudlog.error(f"cabana: api_analyze failed: {e}")
    return _json_response({"ok": False, "error": f"AI analysis failed: {e}"}, status=502)


async def api_explain_signal(request: web.Request) -> web.Response:
  """Explain a single CAN signal as a short functional label (read-only)."""
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)

  message = str(body.get("message", ""))
  signal = str(body.get("signal", ""))
  item_id = str(body.get("id", ""))
  address = str(body.get("address", ""))

  if not message and not signal:
    return _json_response({"ok": False, "error": "message or signal required"}, status=400)

  guessed = _guess_signal_label(message, signal)
  if guessed:
    return _json_response({"ok": True, "response": guessed, "source": "rule"})

  key = item_id or address or message
  batch = await _explain_signals_batch_llm(
    [{"id": key, "message": message, "signal": signal}],
    dbc=str(body.get("dbc", "")),
  )
  if not batch.get("ok"):
    return _json_response(batch, status=502)
  labels = batch.get("labels") or {}
  label = labels.get(key) or labels.get(address) or labels.get(message)
  if not label:
    return _json_response({"ok": False, "error": "Empty AI response"}, status=502)
  return _json_response({"ok": True, "response": label, "source": "ai"})


async def _explain_signals_batch_llm(
  items: list[dict[str, str]],
  *,
  dbc: str = "",
  lang: str = "zh",
) -> dict[str, Any]:
  if not items:
    return {"ok": True, "labels": {}}

  labels: dict[str, str] = dict(_cache_labels_for_items(dbc, items))
  need_llm: list[dict[str, str]] = []
  for it in items:
    iid = str(it.get("id", ""))
    msg = str(it.get("message", ""))
    sig = str(it.get("signal", ""))
    if iid in labels:
      continue
    guessed = _guess_signal_label(msg, sig)
    if guessed:
      labels[iid] = guessed
    else:
      need_llm.append({"id": iid, "message": msg, "signal": sig})

  if not need_llm:
    _persist_labels(dbc, items, labels)
    return {"ok": True, "labels": labels, "source": "cache" if dbc else "rule"}

  chunk_size = 35
  for start in range(0, len(need_llm), chunk_size):
    chunk = need_llm[start:start + chunk_size]
    payload = json.dumps(chunk, ensure_ascii=False)
    if _normalize_cabana_lang(lang) == "zh":
      prompt = (
        f"DBC: {dbc or 'unknown'}\n"
        f"报文列表 JSON:\n{payload}\n\n"
        "为每条返回功能标签。只输出一个 JSON 对象 {\"id\":\"标签\"}，键必须与 id 完全一致。"
        "无 DBC 名称的 hex 报文请结合 address 字段猜测，可写「车身」「其他」。"
      )
    else:
      prompt = (
        f"DBC: {dbc or 'unknown'}\n"
        f"Messages JSON:\n{payload}\n\n"
        'Return one function tag per row. Output only one JSON object {"id":"tag"} with exact id keys. '
        "For unnamed hex frames, guess from address/name; Body/Other are acceptable."
      )
    messages = [
      {"role": "system", "content": _cabana_explain_system(lang)},
      {"role": "user", "content": prompt},
    ]
    try:
      max_tokens = min(900, 14 * len(chunk) + 48)
      result = await _cabana_ai_complete(
        messages,
        max_tokens=max_tokens,
        temperature=0.1,
        use_reasoning_fallback=True,
        prefer_json=True,
        lang=lang,
      )
      if not result.get("ok"):
        for it in chunk:
          guessed = _guess_signal_label(it["message"], it.get("signal", ""))
          if guessed:
            labels[it["id"]] = guessed
        continue
      parsed = _parse_explain_labels_json(result.get("response", ""))
      for it in chunk:
        iid = it["id"]
        label = _resolve_label_from_parsed(parsed, it) or _guess_signal_label(it["message"], it.get("signal", ""))
        if label and label not in _GENERIC_LABELS:
          labels[iid] = label[:8]
    except Exception as e:
      cloudlog.error(f"cabana: explain batch chunk failed: {e}")
      for it in chunk:
        guessed = _guess_signal_label(it["message"], it.get("signal", ""))
        if guessed:
          labels.setdefault(it["id"], guessed)

  _persist_labels(dbc, items, labels)
  return {"ok": True, "labels": labels, "source": "mixed"}


async def api_explain_batch(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except json.JSONDecodeError:
    return _json_response({"ok": False, "error": "Invalid JSON"}, status=400)

  items = body.get("items", [])
  if not isinstance(items, list) or not items:
    return _json_response({"ok": False, "error": "items required"}, status=400)
  if len(items) > 100:
    items = items[:100]

  normalized: list[dict[str, str]] = []
  for raw in items:
    if not isinstance(raw, dict):
      continue
    iid = str(raw.get("id", "")).strip()
    message = str(raw.get("message", "")).strip()
    signal = str(raw.get("signal", "")).strip()
    address = str(raw.get("address", "")).strip()
    if not iid or (not message and not signal):
      continue
    normalized.append({"id": iid, "message": message, "signal": signal, "address": address})

  if not normalized:
    return _json_response({"ok": False, "error": "no valid items"}, status=400)

  result = await _explain_signals_batch_llm(
    normalized,
    dbc=str(body.get("dbc", "")),
    lang=str(body.get("lang", "zh")),
  )
  if not result.get("ok"):
    return _json_response(result, status=502)
  return _json_response(result)


async def api_explain_cache(request: web.Request) -> web.Response:
  dbc = request.query.get("dbc", "").strip()
  if not dbc:
    return _json_response({"ok": False, "error": "dbc required"}, status=400)
  return _json_response({"ok": True, "dbc": dbc, "labels": _labels_for_dbc(dbc)})


async def cabana_explain_signal_tool(args: dict[str, Any]) -> dict[str, Any]:
  """LLM tool: explain one CAN signal."""
  message = str(args.get("message", ""))
  signal = str(args.get("signal", ""))
  if not message and not signal:
    return {"ok": False, "error": "message or signal required"}
  guessed = _guess_signal_label(message, signal)
  if guessed:
    return {"ok": True, "response": guessed}
  key = str(args.get("address", "")) or message
  batch = await _explain_signals_batch_llm(
    [{"id": key, "message": message, "signal": signal}],
    dbc=str(args.get("dbc", "")),
  )
  if not batch.get("ok"):
    return batch
  labels = batch.get("labels") or {}
  label = labels.get(key) or "其他"
  return {"ok": True, "response": label}


async def cabana_analyze_tool(question: str, frames_text: str = "") -> dict[str, Any]:
  """LLM tool: analyze CAN data."""
  user = question
  if frames_text:
    user += f"\n\nCAN data:\n{frames_text}"
  messages = [
    {"role": "system", "content": "你是 Dragonpilot CAN 分析助手。指出异常与关键信号。"},
    {"role": "user", "content": user},
  ]
  return await _cabana_ai_complete(messages, max_tokens=2048)


def _json_response(data: Any, status: int = 200) -> web.Response:
  return web.Response(
    text=json.dumps(data, ensure_ascii=False, default=str),
    status=status,
    content_type="application/json",
  )


def register_routes(app: web.Application, static_root: Path) -> None:
  """Register Cabana API routes (UI is embedded in op助手 main page)."""

  async def _cabana_redirect(_request: web.Request) -> web.HTTPFound:
    return web.HTTPFound(location="/?cabana=1")

  app.router.add_get("/cabana", _cabana_redirect)
  app.router.add_get("/cabana/", _cabana_redirect)

  app.router.add_get("/api/cabana/car", api_car)
  app.router.add_get("/api/cabana/dbcs", api_dbcs)
  app.router.add_get("/api/cabana/dbc/{name}", api_dbc)
  app.router.add_get("/api/cabana/routes", api_routes)
  app.router.add_get("/api/cabana/route/{name}/media", api_route_media)
  app.router.add_get("/api/cabana/route/{name}/summary", api_route_summary)
  app.router.add_get("/api/cabana/route/{name}/file", api_route_file)
  app.router.add_get("/api/cabana/ws", ws_live)
  app.router.add_get("/api/cabana/offline/ws", ws_offline)
  app.router.add_post("/api/cabana/analyze", api_analyze)
  app.router.add_post("/api/cabana/explain", api_explain_signal)
  app.router.add_post("/api/cabana/explain_batch", api_explain_batch)
  app.router.add_get("/api/cabana/explain_cache", api_explain_cache)

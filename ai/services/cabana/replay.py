"""Cabana replay module."""
from ai.services.cabana.deps import *
from ai.services.cabana.frame import can_frame_to_dict as _can_frame_to_dict
from ai.services.cabana.car_params import _resolve_car_params
from ai.services.cabana.dbc import _suggest_dbc_for_car

# -----------------------------------------------------------------------------
# Route / qlog helpers
# -----------------------------------------------------------------------------

def _get_routes_dir() -> Path | None:
  from ai.system.paths import routes_dir
  rd = Path(routes_dir())
  if rd.is_dir():
    return rd
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


LOG_SEGMENT_LENGTH_SEC = 60
_THUMB_CACHE: dict[str, bytes] = {}
_THUMB_CACHE_ORDER: list[str] = []
_THUMB_CACHE_MAX = 64
_ENCODE_IDX_CACHE: dict[str, list[tuple[float, int, int]]] = {}
_QCAMERA_FPS = 20.0


def _qcamera_paths_sorted(route_name: str) -> list[tuple[int, Path]]:
  base = _route_dir(route_name)
  if base is None:
    return []
  segs: list[tuple[int, Path]] = []
  for path in sorted(base.rglob("qcamera.ts")):
    if not path.is_file():
      continue
    parent = path.parent.name
    try:
      num = int(parent) if parent.isdigit() else 0
    except ValueError:
      num = 0
    segs.append((num, path))
  segs.sort(key=lambda x: x[0])
  return segs


def _thumb_cache_get(key: str) -> bytes | None:
  return _THUMB_CACHE.get(key)


def _thumb_cache_put(key: str, data: bytes) -> None:
  if key in _THUMB_CACHE:
    return
  _THUMB_CACHE[key] = data
  _THUMB_CACHE_ORDER.append(key)
  while len(_THUMB_CACHE_ORDER) > _THUMB_CACHE_MAX:
    old = _THUMB_CACHE_ORDER.pop(0)
    _THUMB_CACHE.pop(old, None)


def _encode_index_samples(route_name: str) -> list[tuple[float, int, int]]:
  """Build [(route_rel_sec, segment_num, frame_id)] from qRoadEncodeIdx / roadEncodeIdx."""
  cached = _ENCODE_IDX_CACHE.get(route_name)
  if cached is not None:
    return cached
  if LogReader is None:
    return []
  routes_dir = _get_routes_dir()
  if routes_dir is None:
    return []
  route_path = routes_dir / route_name
  if not route_path.is_dir():
    return []
  samples: list[tuple[float, int, int]] = []
  origin: int | None = None
  for qlog in _find_qlogs(route_path):
    try:
      lr = LogReader(str(qlog))
      for msg in lr:
        if origin is None:
          origin = int(msg.logMonoTime)
        which = msg.which()
        if which not in ("qRoadEncodeIdx", "roadEncodeIdx"):
          continue
        enc = getattr(msg, which)
        seg = int(getattr(enc, "segmentNum", 0) or 0)
        fid = int(getattr(enc, "frameId", 0) or 0)
        t_rel = (int(msg.logMonoTime) - origin) / 1e9
        samples.append((t_rel, seg, fid))
    except Exception:
      continue
  samples.sort(key=lambda x: x[0])
  if len(samples) > 50_000:
    samples = samples[:50_000]
  _ENCODE_IDX_CACHE[route_name] = samples
  return samples


def _qcamera_offset_in_segment(route_name: str, rel_sec: float, seg_num: int) -> float | None:
  samples = _encode_index_samples(route_name)
  if not samples:
    return None
  best_fid: int | None = None
  best_dt = 1e9
  for t_rel, seg, fid in samples:
    if seg != seg_num:
      continue
    dt = abs(t_rel - rel_sec)
    if dt < best_dt:
      best_dt = dt
      best_fid = fid
  if best_fid is not None and best_dt < 12.0:
    return best_fid / _QCAMERA_FPS
  best_fid = None
  best_dt = 1e9
  for t_rel, _seg, fid in samples:
    dt = abs(t_rel - rel_sec)
    if dt < best_dt:
      best_dt = dt
      best_fid = fid
  if best_fid is not None and best_dt < 12.0:
    return best_fid / _QCAMERA_FPS
  return None


def _extract_qcamera_jpeg(path: Path, offset_sec: float, *, max_width: int = 480) -> bytes | None:
  if not path.is_file():
    return None
  cmd = [
    "ffmpeg", "-hide_banner", "-loglevel", "error",
    "-ss", f"{max(0.0, offset_sec):.3f}",
    "-i", str(path),
    "-frames:v", "1",
    "-f", "image2pipe",
    "-vcodec", "mjpeg",
    "-q:v", "4",
    "pipe:1",
  ]
  try:
    raw = subprocess.check_output(cmd, timeout=10, stderr=subprocess.DEVNULL)
  except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
    return None
  if not raw:
    return None
  if max_width <= 0:
    return raw
  try:
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(raw))
    if im.width > max_width:
      ratio = max_width / im.width
      im = im.resize((max_width, max(1, int(im.height * ratio))))
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=82)
    return out.getvalue()
  except Exception:
    return raw


def _qcamera_thumbnail_at_time(route_name: str, rel_sec: float) -> bytes | None:
  segs = _qcamera_paths_sorted(route_name)
  if not segs:
    return None
  rel_sec = max(0.0, rel_sec)
  seg_idx = int(rel_sec // LOG_SEGMENT_LENGTH_SEC)
  if seg_idx >= len(segs):
    seg_idx = len(segs) - 1
  seg_num = segs[seg_idx][0]
  offset = _qcamera_offset_in_segment(route_name, rel_sec, seg_num)
  if offset is None:
    offset = rel_sec - seg_idx * LOG_SEGMENT_LENGTH_SEC
  cache_key = f"{route_name}:{seg_num}:{offset:.2f}"
  cached = _thumb_cache_get(cache_key)
  if cached:
    return cached
  jpeg = _extract_qcamera_jpeg(segs[seg_idx][1], offset)
  if jpeg:
    _thumb_cache_put(cache_key, jpeg)
  return jpeg


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


_ROUTES_LIST_CACHE: tuple[float, list[dict[str, Any]]] | None = None
_ROUTES_LIST_CACHE_TTL = 45.0


def _list_routes(params: Params | None = None) -> list[dict[str, Any]]:
  global _ROUTES_LIST_CACHE
  from ai.infra.timezone import get_route_timezone, read_ai_timezone_name

  now = time.monotonic()
  if _ROUTES_LIST_CACHE is not None:
    cached_at, cached_routes = _ROUTES_LIST_CACHE
    if now - cached_at < _ROUTES_LIST_CACHE_TTL:
      return list(cached_routes)

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
  _ROUTES_LIST_CACHE = (time.monotonic(), list(routes))
  return routes

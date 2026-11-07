"""Cabana handlers module."""
from __future__ import annotations

import asyncio
import csv
import io
import re

from aiohttp import web

from ai.services.cabana.deps import DBC, DBC_PATH, Params
from ai.services.cabana.http import json_response as _json_response
from ai.services.cabana.car_params import _resolve_car_params
from ai.services.cabana.dbc import (
  _build_dbc_catalog,
  _dbc_catalog_cache,
  _get_dbc_dict,
  _parse_dbc_signals,
  _pick_preferred_dbc,
  _quick_dbc_catalog,
  _suggest_dbc_for_fingerprint,
)
from ai.services.cabana.decoder import decode_frames as _decode_frames
from ai.services.cabana.decoder import get_decoder as _get_decoder
from ai.services.cabana.replay import (
  _list_routes,
  _media_payload,
  _qcamera_thumbnail_at_time,
  _query_frames,
  _route_dir,
)

_FRAMES_MAX_BUCKETS = 5000
_SIMILAR_BITS_MAX_SAMPLES = 200
_SIMILAR_BITS_MAX_TOP_N = 50

# -----------------------------------------------------------------------------
# API handlers
# -----------------------------------------------------------------------------

async def api_car(request: web.Request) -> web.Response:
  route = request.query.get("route", "").strip()
  loop = asyncio.get_running_loop()
  cp = await loop.run_in_executor(None, lambda: _resolve_car_params(route))
  if cp is None:
    return _json_response({
      "ok": False,
      "error": "CarParams not available",
      "hint": "Drive once, pick a route with carParams in qlog/rlog, or choose a DBC manually.",
      "car": None,
      "dbc_dict": {},
      "suggested_dbc": None,
    })

  suggested_dbc = _suggest_dbc_for_fingerprint(
    cp.get("carFingerprint", ""),
    brand=cp.get("brand", ""),
  )
  dbc_dict = _get_dbc_dict(cp.get("carFingerprint", ""))
  if not suggested_dbc and dbc_dict:
    suggested_dbc = _pick_preferred_dbc(list(dbc_dict.values()))
  return _json_response({
    "ok": True,
    "car": cp,
    "dbc_dict": dbc_dict,
    "suggested_dbc": suggested_dbc,
    "source": cp.get("source", "device"),
  })


async def api_dbcs(request: web.Request) -> web.Response:
  if DBC_PATH is None or not DBC_PATH:
    return _json_response({"ok": False, "error": "opendbc not available"}, status=503)
  quick = str(request.query.get("quick") or "").lower() in ("1", "true", "yes")
  loop = asyncio.get_running_loop()
  if _dbc_catalog_cache is not None:
    catalog = _dbc_catalog_cache
  elif quick:
    catalog = _quick_dbc_catalog()
    loop.run_in_executor(None, _build_dbc_catalog)
  else:
    catalog = await loop.run_in_executor(None, _build_dbc_catalog)
  return _json_response({
    "ok": True,
    "dbcs": [item["name"] for item in catalog],
    "catalog": catalog,
    "quick": quick and _dbc_catalog_cache is None,
  })


def warm_dbc_catalog() -> int:
  """Build DBC catalog cache (safe to call from a background thread)."""
  if DBC_PATH is None or not DBC_PATH:
    return 0
  return len(_build_dbc_catalog())


async def api_dbc(request: web.Request) -> web.Response:
  name = request.match_info["name"]
  if DBC is None:
    return _json_response({"ok": False, "error": "opendbc DBC parser not available"}, status=503)
  loop = asyncio.get_running_loop()
  signals = await loop.run_in_executor(None, lambda: _parse_dbc_signals(name))
  return _json_response({"ok": True, "name": name, "signals": signals})


async def api_route_thumbnail(request: web.Request) -> web.Response:
  name = request.match_info["name"]
  try:
    rel_sec = max(0.0, float(request.query.get("time", "0")))
  except (TypeError, ValueError):
    return _json_response({"ok": False, "error": "Invalid time"}, status=400)
  loop = asyncio.get_running_loop()
  jpeg = await loop.run_in_executor(None, lambda: _qcamera_thumbnail_at_time(name, rel_sec))
  if not jpeg:
    return _json_response({"ok": False, "error": "No qcamera thumbnail"}, status=404)
  return web.Response(
    body=jpeg,
    content_type="image/jpeg",
    headers={"Cache-Control": "private, max-age=120"},
  )


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
  from ai.infra.timezone import read_ai_timezone_name

  params = Params()
  tz_name = read_ai_timezone_name(params)
  loop = asyncio.get_running_loop()
  routes = await loop.run_in_executor(None, lambda: _list_routes(params))
  return _json_response({
    "ok": True,
    "routes": routes,
    "route_timezone": tz_name,
  })


# -----------------------------------------------------------------------------
# Frame query endpoints (B/C/D)
# -----------------------------------------------------------------------------

def _parse_query_float(request: web.Request, key: str) -> tuple[float | None, str | None]:
  raw = request.query.get(key)
  if raw is None or raw == "":
    return None, None
  try:
    return float(raw), None
  except (TypeError, ValueError):
    return None, f"Invalid {key}"


def _parse_query_address(request: web.Request) -> tuple[int | None, str | None]:
  raw = request.query.get("address")
  if raw is None or raw == "":
    return None, "address (int) is required"
  try:
    return int(raw, 0), None
  except (TypeError, ValueError):
    return None, "Invalid address"


def _filter_frames_rel(
  frames: list[dict],
  address: int,
  t0: float | None,
  t1: float | None,
) -> tuple[list[dict], float]:
  """Filter frames by address and route-relative time window; returns (out, base).

  ``base`` is the first frame's absolute time (route time origin); the returned
  frames carry ``time`` rewritten to route-relative seconds, sorted ascending.
  """
  base = float(frames[0]["time"]) if frames else 0.0
  out: list[dict] = []
  for f in frames:
    try:
      if int(f.get("address", -1)) != address:
        continue
      rel = float(f["time"]) - base
    except (TypeError, ValueError):
      continue
    if t0 is not None and rel < t0 - 1e-9:
      continue
    if t1 is not None and rel > t1 + 1e-9:
      continue
    out.append({**f, "time": round(rel, 6)})
  out.sort(key=lambda f: f["time"])
  return out, base


def _decode_annotated(signals: list[dict], frames: list[dict]) -> list[dict]:
  """Attach decoded "values" to frames without dropping undecodable ones."""
  decoded = _decode_frames(signals, frames)
  by_key: dict[tuple[float, str], dict] = {}
  for f in decoded:
    by_key[(float(f.get("time", 0.0)), str(f.get("data", "")))] = f.get("values", {})
  out: list[dict] = []
  for f in frames:
    values = by_key.get((float(f.get("time", 0.0)), str(f.get("data", ""))))
    out.append({**f, "values": values} if values else f)
  return out


def _downsample_buckets(frames: list[dict], n: int, table: dict | None) -> list[dict]:
  """Uniform buckets over the (already filtered, sorted) frame list.

  Without a decoder table the min/max are raw first-payload-byte values —
  a documented limitation: physical-value min/max requires a DBC. With a
  table, each bucket carries per-signal physical ``{min, max}`` (sparkline
  semantics matching the desktop chart's SegmentTree aggregation).
  """
  if not frames:
    return []
  lo = float(frames[0]["time"])
  hi = float(frames[-1]["time"])
  span = max(hi - lo, 1e-9)
  n = max(1, min(int(n), _FRAMES_MAX_BUCKETS))
  buckets: list[dict] = []
  for i in range(n):
    b: dict = {"t": round(lo + span * i / n, 6), "count": 0}
    if table is None:
      b["min"] = None
      b["max"] = None
    buckets.append(b)
  signals = [s for sigs in (table or {}).values() for s in sigs]
  dec_by_key: dict[tuple[float, str], dict] = {}
  if table and signals:
    for f in _decode_frames(signals, frames):
      dec_by_key[(float(f.get("time", 0.0)), str(f.get("data", "")))] = f.get("values", {})
  for f in frames:
    rel = float(f["time"])
    idx = min(n - 1, int((rel - lo) / span * n))
    b = buckets[idx]
    b["count"] += 1
    try:
      data = bytes.fromhex(str(f.get("data", "")))
    except ValueError:
      data = b""
    if not table:
      if data:
        first = int(data[0])
        b["min"] = first if b["min"] is None else min(b["min"], first)
        b["max"] = first if b["max"] is None else max(b["max"], first)
      continue
    values = dec_by_key.get((rel, str(f.get("data", ""))), {})
    sig_vals = b.setdefault("signals", {})
    for name, v in values.items():
      cur = sig_vals.setdefault(str(name), {"min": v, "max": v})
      cur["min"] = min(cur["min"], v)
      cur["max"] = max(cur["max"], v)
  return buckets


def _frames_worker(
  route_name: str,
  address: int,
  t0: float | None,
  t1: float | None,
  downsample: int,
  dbc_name: str,
  signal_names: list[str],
) -> dict:
  frames, err = _query_frames(route_name)
  if err or frames is None:
    return {"ok": False, "error": err or "Route not found"}
  out, _base = _filter_frames_rel(frames, address, t0, t1)
  result: dict = {
    "ok": True,
    "route": route_name,
    "address": address,
    "t0": t0,
    "t1": t1,
    "count": len(out),
  }
  table: dict | None = None
  if dbc_name:
    loaded = _get_decoder(dbc_name)
    if loaded:
      sigs = loaded.get(address, [])
      if signal_names:
        wanted = set(signal_names)
        sigs = [s for s in sigs if str(s.get("signal")) in wanted]
      table = {address: sigs} if sigs else None
    if table is None:
      result["warning"] = "decode unavailable"
  if downsample and downsample > 0:
    result["buckets"] = _downsample_buckets(out, downsample, table)
  elif table is not None:
    result["frames"] = _decode_annotated([s for sigs in table.values() for s in sigs], out)
  else:
    result["frames"] = out
  return result


async def api_route_frames(request: web.Request) -> web.Response:
  """GET /api/cabana/route/{name}/frames — frame range query + sparkline buckets."""
  name = request.match_info["name"]
  address, err = _parse_query_address(request)
  if err:
    return _json_response({"ok": False, "error": err}, status=400)
  t0, err = _parse_query_float(request, "t0")
  if err:
    return _json_response({"ok": False, "error": err}, status=400)
  t1, err = _parse_query_float(request, "t1")
  if err:
    return _json_response({"ok": False, "error": err}, status=400)
  downsample = 0
  if request.query.get("downsample"):
    try:
      downsample = int(request.query["downsample"])
    except (TypeError, ValueError):
      return _json_response({"ok": False, "error": "Invalid downsample"}, status=400)
  dbc_name = (request.query.get("dbc") or "").strip()
  signal_names = [s.strip() for s in (request.query.get("signals") or "").split(",") if s.strip()]
  loop = asyncio.get_running_loop()
  result = await loop.run_in_executor(
    None, _frames_worker, name, address, t0, t1, downsample, dbc_name, signal_names,
  )
  status = 200 if result.get("ok") else 404
  return _json_response(result, status=status)


def _export_csv(
  route_name: str,
  address: int,
  t0: float | None,
  t1: float | None,
  dbc_name: str,
  decode_on: bool,
) -> tuple[str | None, str | None]:
  """CSV export aligned with desktop export.cc: time,bus,address columns + data.

  Default columns are ``time,bus,address,data_hex``; with ``decode`` + ``dbc``
  one physical-value column per signal (``signal_name(unit)``) is appended.
  """
  frames, err = _query_frames(route_name)
  if err or frames is None:
    return None, err or "Route not found"
  out, _base = _filter_frames_rel(frames, address, t0, t1)
  signals: list[dict] = []
  if decode_on and dbc_name:
    table = _get_decoder(dbc_name)
    if table:
      signals = [s for s in table.get(address, []) if int(s.get("signal_type", 0) or 0) == 0]
  buf = io.StringIO()
  writer = csv.writer(buf)
  header = ["time", "bus", "address", "data_hex"]
  header.extend(
    f"{s['signal']}({s.get('unit') or ''})" if s.get("unit") else str(s["signal"])
    for s in signals
  )
  writer.writerow(header)
  dec_by_key: dict[tuple[float, str], dict] = {}
  if signals:
    for f in _decode_frames(signals, out):
      dec_by_key[(float(f.get("time", 0.0)), str(f.get("data", "")))] = f.get("values", {})
  for f in out:
    bus = int(f.get("bus", 0) or 0)
    row = [
      f"{float(f['time']):.3f}",
      str(bus),
      f"0x{int(f['address']):x}",
      str(f.get("data", "")),
    ]
    if signals:
      values = dec_by_key.get((float(f["time"]), str(f.get("data", ""))), {})
      for s in signals:
        v = values.get(str(s["signal"]))
        row.append("" if v is None else f"{float(v):.3f}")
    writer.writerow(row)
  return buf.getvalue(), None


async def api_route_export(request: web.Request) -> web.Response:
  """GET /api/cabana/route/{name}/export — CSV download (desktop export.cc parity)."""
  name = request.match_info["name"]
  address, err = _parse_query_address(request)
  if err:
    return _json_response({"ok": False, "error": err}, status=400)
  t0, err = _parse_query_float(request, "t0")
  if err:
    return _json_response({"ok": False, "error": err}, status=400)
  t1, err = _parse_query_float(request, "t1")
  if err:
    return _json_response({"ok": False, "error": err}, status=400)
  dbc_name = (request.query.get("dbc") or "").strip()
  decode_on = (request.query.get("decode") or "").strip().lower() in ("1", "true", "yes")
  loop = asyncio.get_running_loop()
  csv_text, err = await loop.run_in_executor(
    None, _export_csv, name, address, t0, t1, dbc_name, decode_on,
  )
  if err or csv_text is None:
    return _json_response({"ok": False, "error": err or "Export failed"}, status=404)
  safe_route = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[-60:] or "route"
  filename = f"{safe_route}_{address:x}.csv"
  return web.Response(
    text=csv_text,
    content_type="text/csv",
    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
  )


def _similar_bits_results(
  frames: list[dict],
  ref_address: int,
  ref_bus: int | None,
  t_rel: float,
  mask: bytes,
  top_n: int,
) -> tuple[list[dict] | None, str | None]:
  """Top-N messages whose selected bits best match the reference frame (desktop
  findsimilarbits.cc parity, simplified per-message instead of per-bit).

  The reference frame is the (bus, address) frame closest to route-relative
  time ``t_rel``. ``mask`` is a byte mask over the payload: mask byte bit b
  (LSB-first, ``1 << b``) selects bit ``b`` of that byte. For every other
  (bus, address) group the selected-bit consistency with the reference frame
  is averaged over sampled frames (up to 200 per group); results are sorted
  by descending match ratio.
  """
  if not frames:
    return None, "No CAN frames"
  base = float(frames[0]["time"])
  ref = None
  best_dt = 1e18
  for f in frames:
    try:
      if int(f.get("address", -1)) != ref_address:
        continue
      if ref_bus is not None and int(f.get("bus", 0) or 0) != ref_bus:
        continue
      dt = abs((float(f["time"]) - base) - t_rel)
    except (TypeError, ValueError):
      continue
    if dt < best_dt:
      best_dt = dt
      ref = f
  if ref is None:
    return None, "Reference frame not found"
  try:
    ref_bytes = bytes.fromhex(str(ref.get("data", "")))
  except ValueError:
    return None, "Reference frame data is not hex"
  positions: list[tuple[int, int]] = []
  for i, m in enumerate(mask):
    if i >= len(ref_bytes):
      break
    for b in range(8):
      if m & (1 << b):
        positions.append((i, b))
  if not positions:
    return None, "Empty mask"
  ref_bits = [(i, b, (ref_bytes[i] >> b) & 1) for (i, b) in positions]
  try:
    ref_pair = (int(ref.get("bus", 0) or 0), ref_address)
  except (TypeError, ValueError):
    ref_pair = (0, ref_address)
  groups: dict[tuple[int, int], list[dict]] = {}
  for f in frames:
    try:
      pair = (int(f.get("bus", 0) or 0), int(f.get("address", -1)))
    except (TypeError, ValueError):
      continue
    if pair == ref_pair:
      continue
    groups.setdefault(pair, []).append(f)
  results: list[dict] = []
  for (bus, addr), flist in groups.items():
    sample = flist
    if len(flist) > _SIMILAR_BITS_MAX_SAMPLES:
      stride = max(1, len(flist) // _SIMILAR_BITS_MAX_SAMPLES)
      sample = flist[::stride]
    matched = 0
    compared = 0
    sample_data = ""
    for f in sample:
      try:
        data = bytes.fromhex(str(f.get("data", "")))
      except ValueError:
        continue
      sample_data = sample_data or str(f.get("data", ""))
      for (i, b, ref_bit) in ref_bits:
        if i >= len(data):
          continue
        compared += 1
        if ((data[i] >> b) & 1) == ref_bit:
          matched += 1
    if compared <= 0:
      continue
    results.append({
      "address": addr,
      "bus": bus,
      "match_ratio": round(matched / compared, 4),
      "sample_data": sample_data,
      "frames": len(flist),
    })
  results.sort(key=lambda r: (-r["match_ratio"], r["address"]))
  return results[: max(1, min(int(top_n), _SIMILAR_BITS_MAX_TOP_N))], None


def _similar_bits_worker(
  route_name: str,
  ref_address: int,
  ref_bus: int | None,
  t_rel: float,
  mask: bytes,
  top_n: int,
) -> dict:
  frames, err = _query_frames(route_name)
  if err or frames is None:
    return {"ok": False, "error": err or "Route not found"}
  results, err = _similar_bits_results(frames, ref_address, ref_bus, t_rel, mask, top_n)
  if err or results is None:
    return {"ok": False, "error": err or "No results"}
  return {"ok": True, "route": route_name, "results": results}


async def api_similar_bits(request: web.Request) -> web.Response:
  """POST /api/cabana/tools/similar_bits — find messages with similar bits."""
  try:
    body = await request.json()
  except Exception:
    return _json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
  if not isinstance(body, dict):
    return _json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
  route = str(body.get("route") or "").strip()
  if not route:
    return _json_response({"ok": False, "error": "route is required"}, status=400)
  raw_addr = body.get("address")
  try:
    address = int(str(raw_addr), 0) if isinstance(raw_addr, str) else int(raw_addr)
  except (TypeError, ValueError):
    return _json_response({"ok": False, "error": "address (int) is required"}, status=400)
  try:
    t_rel = float(body.get("t") or 0.0)
  except (TypeError, ValueError):
    return _json_response({"ok": False, "error": "Invalid t"}, status=400)
  try:
    mask = bytes.fromhex(str(body.get("mask_hex") or ""))
  except ValueError:
    return _json_response({"ok": False, "error": "Invalid mask_hex"}, status=400)
  if not mask:
    return _json_response({"ok": False, "error": "mask_hex must not be empty"}, status=400)
  raw_top_n = body.get("top_n")
  if raw_top_n is None:
    top_n = 10
  else:
    try:
      top_n = int(raw_top_n)
    except (TypeError, ValueError):
      return _json_response({"ok": False, "error": "Invalid top_n"}, status=400)
  raw_bus = body.get("bus")
  ref_bus: int | None
  try:
    ref_bus = int(raw_bus) if raw_bus is not None else None
  except (TypeError, ValueError):
    ref_bus = None
  loop = asyncio.get_running_loop()
  result = await loop.run_in_executor(
    None, _similar_bits_worker, route, address, ref_bus, t_rel, mask, top_n,
  )
  status = 200 if result.get("ok") else 404
  return _json_response(result, status=status)

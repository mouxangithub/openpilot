"""Cabana ai_explain module."""
from ai.services.cabana.deps import *
from ai.services.cabana.http import json_response as _json_response
from ai.services.cabana.dbc import _parse_dbc_signals

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
  from ai.server.deps import read_ai_config

  return read_ai_config(Params())


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
  from ai.core.llm.client import chat_completion_collect, is_thinking_request_error

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
    {"role": "system", "content": "你是 openpilot CAN 分析助手。指出异常与关键信号，用简洁中文。"},
    {"role": "user", "content": user},
  ]
  return await _cabana_ai_complete(messages, max_tokens=2048)


"""Cabana dbc module."""
from ai.services.cabana.deps import *
from ai.services.cabana.frame import can_frame_to_dict as _can_frame_to_dict
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
_dbc_catalog_lock = threading.Lock()


def _quick_dbc_catalog() -> list[dict[str, Any]]:
  return [{"name": name, "searchText": name} for name in _list_dbc_names()]


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

  with _dbc_catalog_lock:
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


def _suggest_dbc_for_fingerprint(car_fingerprint: str, *, brand: str = "") -> str | None:
  dbc_dict = _get_dbc_dict(car_fingerprint)
  if dbc_dict:
    return _pick_preferred_dbc(list(dbc_dict.values()))
  try:
    from opendbc.car.fingerprints import MIGRATION
    from openpilot.tools.cabana.dbc.generate_dbc_json import generate_dbc_dict

    platform = MIGRATION.get(car_fingerprint, car_fingerprint)
    dbc = generate_dbc_dict().get(platform)
    if dbc:
      return dbc
  except Exception:
    pass
  return _suggest_dbc_for_car({"carFingerprint": car_fingerprint, "brand": brand})


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

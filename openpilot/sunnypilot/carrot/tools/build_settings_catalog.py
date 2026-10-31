#!/usr/bin/env python3
"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Regenerate `carrot_settings_sp.json`, the one settings catalog this fork serves on 7000.

CarrotPilot's `carrot_settings.json` is the shape the panel wants - every entry carries
ko/en/zh labels, min/max/unit, options and a menu tree. This fork cannot serve it as-is:

  * 33 of its params are not declared in `openpilot/common/params_keys.h`, so a control
    built from them could only ever fail to write;
  * 46 params this fork tunes are not in it at all (`carrot/config.py::_DEFAULT_NAV_PARAMS`
    is this fork's carrot surface, and it is the source the panel used to read);
  * 10 more are declared here and named by CarrotPilot's menu but missing from its params;
  * and sunnypilot's own settings - the 134 params the car's UI groups across its 19
    settings pages - are not in it at all, so the panel hid them.

The output is CarrotPilot's structure with those three differences applied, so the panel,
the setting profiles, the popular-value upload and the intro presets all read one catalog
instead of two.

Usage:
    python -m openpilot.sunnypilot.carrot.tools.build_settings_catalog
"""
import importlib.util
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]          # the checkout root
CARROT = ROOT / "openpilot" / "sunnypilot" / "carrot"
UPSTREAM_JSON = ROOT / "openpilot" / "sunnypilot" / "carrot_settings.json"
OUTPUT_JSON = ROOT / "openpilot" / "sunnypilot" / "carrot_settings_sp.json"
PARAMS_KEYS_H = ROOT / "openpilot" / "common" / "params_keys.h"

from openpilot.sunnypilot.carrot.tools.sp_param_labels import (
  FAMILY_LABELS, IMU_PARAMS, MAPS_PARAMS, PAGE_LABELS, apply_param_labels,
)
from openpilot.sunnypilot.carrot.tools.ui_control_extractor import extract_page_controls, po_translations

TRANSLATIONS_DIR = ROOT / "openpilot" / "selfdrive" / "ui" / "translations"

# The menu node the fork-only params live under.
SP_NODE_ID = "SUNNYPILOT"
SP_GROUP_ID = "CARROT_SP"

# Prefix -> menu group for the fork-only params, so they land somewhere sensible instead of
# all in one bucket. First match wins.
SP_SUBGROUPS = (
  ("AUTO_FORK", "Auto"),
  ("LONGITUDINAL", ("Cruise", "Stop", "Accel", "TStop", "TFollow")),
  ("LATERAL", ("Steer", "Lat", "Bsd", "Lane")),
  ("SPEED", ("Speed", "Road", "Curve")),
  ("DISPLAY", ("Show", "Color", "Sound", "Ui")),
)


_DECL_RE = re.compile(r'\{"([A-Za-z0-9_]+)",\s*\{([^}]*)\}')


def declared() -> dict[str, tuple[str, object]]:
  """`{key: (json_type, default)}` for every key `params_keys.h` declares.

  The declaration is the only place that knows a key's type and default, and a control may
  only be built from a key that is declared - an undeclared one can be read (as its default)
  but never written.
  """
  types = {"BOOL": "bool", "INT": "int", "FLOAT": "float", "STRING": "str", "TIME": "int", "JSON": "str", "BYTES": "str"}
  out = {}
  for name, attrs in _DECL_RE.findall(PARAMS_KEYS_H.read_text(encoding="utf-8")):
    kind = "str"
    for token, json_type in types.items():
      if re.search(rf"\b{token}\b", attrs):
        kind = json_type
        break
    raw = re.search(r'"([^"]*)"\s*\}\s*$', "{" + attrs + "}")
    default = raw.group(1) if raw else ""
    try:
      value = {"bool": lambda v: v == "1", "int": int, "float": float}.get(kind, str)(default) if default != "" else \
        {"bool": False, "int": 0, "float": 0.0}.get(kind, "")
    except (TypeError, ValueError):
      value = {"bool": False, "int": 0, "float": 0.0}.get(kind, "")
    out[name] = (kind, value)
  return out


def declared_keys() -> set[str]:
  """Every key `params_keys.h` declares - the only keys a control may be built from."""
  return set(declared())


def sp_defaults() -> dict:
  """This fork's carrot surface: `carrot/config.py::_DEFAULT_NAV_PARAMS`.

  Parsed rather than imported: importing it pulls in `Params`, which needs zmq, and a
  catalog generator has no business needing the device runtime.
  """
  import ast

  tree = ast.parse((CARROT / "config.py").read_text(encoding="utf-8"))
  for node in ast.walk(tree):
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
      target, value = node.target.id, node.value
    elif isinstance(node, ast.Assign):
      names = [t.id for t in node.targets if isinstance(t, ast.Name)]
      target, value = (names[0] if names else None), node.value
    else:
      continue
    if target == "_DEFAULT_NAV_PARAMS" and isinstance(value, ast.Dict):
      out = {}
      for k, v in zip(value.keys, value.values, strict=True):
        if not isinstance(k, ast.Constant):
          continue
        try:
          out[k.value] = ast.literal_eval(v)
        except (ValueError, SyntaxError):
          out[k.value] = 0
      return out
  raise SystemExit("could not find _DEFAULT_NAV_PARAMS in carrot/config.py")


def humanize(name: str) -> str:
  """`AutoForkDistOffsetH` -> `Auto Fork Dist Offset H`."""
  return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " ").strip()


def sp_subgroup(name: str) -> str:
  for group, prefixes in SP_SUBGROUPS:
    if isinstance(prefixes, str):
      prefixes = (prefixes,)
    if name.startswith(prefixes):
      return group
  return "MISC"


def ui_page_params() -> dict:
  """`{page: [param, ...]}` for the params the car's own settings pages group.

  Reuses the scanner the 8088 panel already serves from, so the two panels cannot disagree
  about which page a setting belongs to. Its output is filtered to declared keys here: the
  scan also picks up UI strings and state names (`Scan`, `Back`, `active`), which are not
  settings and must not become controls.
  """
  spec = importlib.util.spec_from_file_location("_carrot_web_settings", CARROT / "web_settings.py")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)

  declared_set = declared_keys()
  pages = {}
  for page, keys in module.scan_ui_pages(module.ui_settings_dir()).items():
    kept = [k for k in keys if k in declared_set]
    if kept:
      pages[page] = kept
  return pages


def _type_of(value) -> str:
  if isinstance(value, bool):
    return "bool"
  if isinstance(value, int):
    return "int"
  if isinstance(value, float):
    return "float"
  return "str"


def _apply_page_control(entry: dict, ctrl: dict, zh_map: dict[str, str], ko_map: dict[str, str]) -> None:
  """Overwrite the entry with what the on-device page shows for this param.

  The page is the 1:1 truth: its tr() strings are what the driver reads, and the
  .po files translate exactly those strings for the other locales. The po msgids
  keep the pages' <br> markup, so look the raw text up and clean the translation.
  """
  def _localized(text: str, raw: str | None, mapping: dict[str, str]) -> str:
    for candidate in filter(None, (raw, text)):
      hit = mapping.get(candidate)
      if hit:
        return re.sub(r"<br\s*/?>", "\n", hit).strip()
    return text

  en_title = ctrl.get("title")
  en_descr = ctrl.get("descr")
  raw_title = ctrl.get("_raw_title")
  raw_descr = ctrl.get("_raw_descr")
  if en_title:
    entry["etitle"] = en_title
    entry["title"] = _localized(en_title, raw_title, ko_map)
    entry["ctitle"] = _localized(en_title, raw_title, zh_map)
  if en_descr:
    entry["edescr"] = en_descr
    entry["descr"] = _localized(en_descr, raw_descr, ko_map)
    entry["cdescr"] = _localized(en_descr, raw_descr, zh_map)
  if ctrl.get("min") is not None:
    entry["min"] = ctrl["min"]
  buttons = ctrl.get("buttons")
  if buttons:
    entry["options"] = {
      "ko": [ko_map.get(b, b) for b in buttons],
      "en": list(buttons),
      "zh": [zh_map.get(b, b) for b in buttons],
    }
    entry.setdefault("min", 0)
    entry["max"] = len(buttons) - 1
  elif ctrl.get("max") is not None:
    entry["max"] = ctrl["max"]
  if ctrl.get("step") not in (None, 1):
    entry["step"] = ctrl["step"]


def build() -> dict:
  upstream = json.loads(UPSTREAM_JSON.read_text(encoding="utf-8"))
  declared_map = declared()
  declared_set = set(declared_map)
  defaults = sp_defaults()

  kept_params = [p for p in upstream["params"] if p.get("name") in declared_set]
  kept_names = {p["name"] for p in kept_params}
  dropped = sorted({p.get("name") for p in upstream["params"]} - kept_names)
  added = sorted((set(defaults) | kept_names) - kept_names)

  def labelled_entry(name: str, default, group: str) -> dict:
    """An added param entry with its label slots filled from sp_param_labels."""
    kind = _type_of(default) if name not in declared_map else declared_map[name][0]
    value = default if name in defaults else (declared_map.get(name, (kind, default))[1])
    zh_group = PAGE_LABELS.get(group, (group,) * 3)[2]
    entry = {
      "group": group,
      "name": name,
      "title": humanize(name),
      "descr": "sunnypilot",
      "egroup": sp_subgroup(name) if group == "sunnypilot" else group.upper(),
      "etitle": humanize(name),
      "edescr": "sunnypilot",
      "cgroup": zh_group,
      "ctitle": humanize(name),
      "cdescr": "sunnypilot",
      "default": value,
      "type": kind,
    }
    apply_param_labels(entry)
    # the ko slots are the panel's last resort; the English text beats "sunnypilot"
    if entry["edescr"] and entry["descr"] == "sunnypilot":
      entry["descr"] = entry["edescr"]
    return entry

  # 1) fork-only params get an entry: labels come from sp_param_labels, the
  #    fork's own default is the value.
  extra_params = [labelled_entry(name, defaults.get(name, 0), "sunnypilot") for name in added]

  # 1b) sunnypilot's own settings, grouped the way the car's UI groups them. Their type and
  #     default come from params_keys.h, which is the only place that knows either.
  pages = ui_page_params()
  already = kept_names | set(defaults)
  page_params = []
  for page, keys in sorted(pages.items()):
    zh_page = PAGE_LABELS.get(page, (page, page, page))[2]
    for name in keys:
      if name in already:
        continue
      kind, value = declared_map.get(name, ("str", ""))
      entry = labelled_entry(name, value, page)
      entry["default"], entry["type"] = value, kind
      entry["cgroup"] = zh_page
      page_params.append(entry)
  extra_params.extend(page_params)

  # 1c) IMU calibration (this fork's locationd work): declared keys with no upstream
  #     entry and no on-device page.
  imu_params = []
  for name in IMU_PARAMS:
    if name in kept_names or name in {p["name"] for p in extra_params}:
      continue
    kind, value = declared_map.get(name, ("str", ""))
    entry = labelled_entry(name, value, "imu")
    entry["default"], entry["type"] = value, kind
    imu_params.append(entry)
  extra_params.extend(imu_params)

  # 1d) map-section params the panel tree references but no upstream entry carries.
  catalog_names = kept_names | {p["name"] for p in extra_params}
  for name in tuple(MAPS_PARAMS):
    if name in catalog_names:
      continue
    kind, value = declared_map.get(name, ("str", ""))
    entry = labelled_entry(name, value, "maps")
    entry["default"], entry["type"] = value, kind
    extra_params.append(entry)
    catalog_names.add(name)

  # de-dupe by name (a param can be claimed by two on-device pages; first wins)
  seen: set[str] = set()
  deduped_params = []
  for p in kept_params + extra_params:
    if p["name"] in seen:
      continue
    seen.add(p["name"])
    deduped_params.append(p)
  all_params = deduped_params

  # 1e) 1:1 pass: the on-device page sources are the truth for what a control
  #     looks like (title, description, range, button labels), and the UI's own
  #     .po files translate exactly those strings. Anything the pages define
  #     overwrites the generated/curated label.
  zh_map = po_translations(TRANSLATIONS_DIR / "app_zh-CHS.po")
  ko_map = po_translations(TRANSLATIONS_DIR / "app_ko.po")
  settings_dir = ROOT / "openpilot" / "selfdrive" / "ui" / "sunnypilot" / "layouts" / "settings"
  controls = extract_page_controls(settings_dir, declared_set)
  labelled_from_pages = 0
  for p in all_params:
    ctrl = controls.get(p["name"])
    if ctrl:
      _apply_page_control(p, ctrl, zh_map, ko_map)
      labelled_from_pages += 1

  # 2) the menu keeps CarrotPilot's tree, with the dropped names removed from its leaves.
  def prune(nodes):
    out = []
    for node in nodes:
      node = dict(node)
      if "params" in node:
        node["params"] = [n for n in node["params"] if n in declared_set or n in defaults]
        if not node["params"]:
          continue
      if "groups" in node:
        node["groups"] = prune(node["groups"])
        if not node["groups"]:
          continue
      out.append(node)
    return out

  menu = prune(upstream.get("menu") or [])

  # 3) and gains a SUNNYPILOT node: the fork-only carrot params by family, the on-device
  #    settings pages (the car's own grouping, filtered to declared keys) with real labels,
  #    and the map/IMU sections.
  by_sub: dict[str, list[str]] = {}
  for name in added:
    by_sub.setdefault(sp_subgroup(name), []).append(name)

  sp_groups = []
  if by_sub:
    sp_groups.append({
      "id": SP_GROUP_ID,
      "ko": "carrot (sp)",
      "en": "carrot (sp)",
      "zh": "carrot (sp)",
      "groups": [
        {"id": f"{SP_GROUP_ID}_{sub}",
         "ko": FAMILY_LABELS.get(sub, (sub,) * 3)[0],
         "en": FAMILY_LABELS.get(sub, (sub,) * 3)[1],
         "zh": FAMILY_LABELS.get(sub, (sub,) * 3)[2],
         "params": sorted(by_sub[sub])}
        for sub in sorted(by_sub)
      ],
    })
  if pages:
    ui_groups = []
    for page, keys in sorted(pages.items()):
      ko, en, zh = PAGE_LABELS.get(page, (page, page, page))
      refs = [k for k in keys if k in declared_set]
      if refs:
        ui_groups.append({"id": f"{SP_GROUP_ID}_UI_{page.upper()}", "ko": ko, "en": en, "zh": zh,
                          "params": refs})
    if ui_groups:
      sp_groups.append({
        "id": SP_GROUP_ID + "_UI",
        "ko": "차량 설정",
        "en": "On-device settings",
        "zh": "车机设置页",
        "groups": ui_groups,
      })
  # 地图: map-data display and decel settings, gathered where a user looks for them.
  map_refs = [k for k in MAPS_PARAMS if k in catalog_names]
  if map_refs:
    sp_groups.append({
      "id": SP_GROUP_ID + "_MAPS",
      "ko": "지도", "en": "Maps", "zh": "地图",
      "params": map_refs,
    })
  # IMU: this fork's locationd calibration surface.
  imu_refs = IMU_PARAMS if imu_params else []
  if imu_refs:
    sp_groups.append({
      "id": SP_GROUP_ID + "_IMU",
      "ko": "IMU", "en": "IMU calibration", "zh": "IMU 惯性测量",
      "params": list(imu_refs),
    })

  if sp_groups:
    menu.append({
      "id": SP_NODE_ID,
      "ko": "sunnypilot",
      "en": "sunnypilot",
      "zh": "sunnypilot 自有设置",
      "groups": sp_groups,
    })

  return {
    "apilot": upstream.get("apilot"),
    "menu": menu,
    "params": all_params,
    "_generated": {
      "note": "Generated by openpilot/sunnypilot/carrot/tools/build_settings_catalog.py - do not edit by hand.",
      "upstream_params": len(upstream["params"]),
      "kept": len(kept_params),
      "dropped_undeclared": dropped,
      "added_from_this_fork": added,
      "added_from_on_device_pages": sorted(p["name"] for p in page_params),
      "added_imu": [p["name"] for p in imu_params],
      "on_device_pages": sorted(pages),
      "labelled_by_sp_param_labels": len(extra_params),
      "labelled_from_on_device_pages": labelled_from_pages,
    },
  }


def main() -> int:
  built = build()
  OUTPUT_JSON.write_text(json.dumps(built, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
  info = built["_generated"]
  print(f"wrote {OUTPUT_JSON}")
  print(f"  upstream params : {info['upstream_params']}")
  print(f"  kept            : {info['kept']}")
  print(f"  dropped (undeclared here): {len(info['dropped_undeclared'])} {info['dropped_undeclared'][:6]}...")
  print(f"  added (this fork)        : {len(info['added_from_this_fork'])} {info['added_from_this_fork'][:6]}...")
  print(f"  menu top nodes  : {[n['id'] for n in built['menu']]}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

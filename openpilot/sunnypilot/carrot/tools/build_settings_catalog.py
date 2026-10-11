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
  * 10 more are declared here and named by CarrotPilot's menu but missing from its params.

The output is CarrotPilot's structure with those three differences applied, so the panel,
the setting profiles, the popular-value upload and the intro presets all read one catalog
instead of two.

Usage:
    python -m openpilot.sunnypilot.carrot.tools.build_settings_catalog
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]          # the checkout root
CARROT = ROOT / "openpilot" / "sunnypilot" / "carrot"
UPSTREAM_JSON = ROOT / "openpilot" / "sunnypilot" / "carrot_settings.json"
OUTPUT_JSON = ROOT / "openpilot" / "sunnypilot" / "carrot_settings_sp.json"
PARAMS_KEYS_H = ROOT / "openpilot" / "common" / "params_keys.h"

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


def declared_keys() -> set[str]:
  """Every key `params_keys.h` declares - the only keys a control may be built from."""
  return set(re.findall(r'\{"([A-Za-z0-9_]+)",\s*\{', PARAMS_KEYS_H.read_text(encoding="utf-8")))


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


def _type_of(value) -> str:
  if isinstance(value, bool):
    return "bool"
  if isinstance(value, int):
    return "int"
  if isinstance(value, float):
    return "float"
  return "str"


def build() -> dict:
  upstream = json.loads(UPSTREAM_JSON.read_text(encoding="utf-8"))
  declared = declared_keys()
  defaults = sp_defaults()

  kept_params = [p for p in upstream["params"] if p.get("name") in declared]
  kept_names = {p["name"] for p in kept_params}
  dropped = sorted({p.get("name") for p in upstream["params"]} - kept_names)
  added = sorted((set(defaults) | kept_names) - kept_names)

  # 1) fork-only params get a minimal entry: no ko/zh label exists for them, so the key
  #    itself is the title and the fork's own default is the value.
  extra_params = []
  for name in added:
    default = defaults.get(name, 0)
    extra_params.append({
      "group": "sunnypilot",
      "name": name,
      "title": humanize(name),
      "descr": "sunnypilot",
      "egroup": sp_subgroup(name),
      "etitle": humanize(name),
      "edescr": "sunnypilot",
      "cgroup": "sunnypilot",
      "ctitle": humanize(name),
      "cdescr": "sunnypilot",
      "default": default,
      "type": _type_of(default),
    })

  # 2) the menu keeps CarrotPilot's tree, with the dropped names removed from its leaves.
  def prune(nodes):
    out = []
    for node in nodes:
      node = dict(node)
      if "params" in node:
        node["params"] = [n for n in node["params"] if n in declared or n in defaults]
        if not node["params"]:
          continue
      if "groups" in node:
        node["groups"] = prune(node["groups"])
        if not node["groups"]:
          continue
      out.append(node)
    return out

  menu = prune(upstream.get("menu") or [])

  # 3) and gains one node for the fork-only params, grouped by family.
  by_sub: dict[str, list[str]] = {}
  for name in added:
    by_sub.setdefault(sp_subgroup(name), []).append(name)
  if by_sub:
    menu.append({
      "id": SP_NODE_ID,
      "ko": "sunnypilot",
      "en": "sunnypilot",
      "zh": "sunnypilot",
      "groups": [{
        "id": SP_GROUP_ID,
        "ko": "carrot (sp)",
        "en": "carrot (sp)",
        "zh": "carrot (sp)",
        "groups": [
          {"id": f"{SP_GROUP_ID}_{sub}", "ko": sub, "en": sub, "zh": sub,
           "params": sorted(by_sub[sub])}
          for sub in sorted(by_sub)
        ],
      }],
    })

  return {
    "apilot": upstream.get("apilot"),
    "menu": menu,
    "params": kept_params + extra_params,
    "_generated": {
      "note": "Generated by openpilot/sunnypilot/carrot/tools/build_settings_catalog.py - do not edit by hand.",
      "upstream_params": len(upstream["params"]),
      "kept": len(kept_params),
      "dropped_undeclared": dropped,
      "added_from_this_fork": added,
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

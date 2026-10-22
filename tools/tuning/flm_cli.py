#!/usr/bin/env python3
import argparse
import json

from openpilot.selfdrive.controls.lib import flm_workspace


def _classify_route_arg(arg: str) -> tuple[str, str]:
  """Map a CLI route argument to (route_id, footage_dir).

  Accepts a local qlog/rlog file path, a segment directory path, or a plain
  route id (resolved against the default log root).
  """
  from pathlib import Path

  path = Path(arg)
  if path.is_file():
    segment_dir = path.parent
    return segment_dir.name, str(segment_dir.parent)
  if path.is_dir():
    return path.name, str(path.parent)
  return arg, ""


def main() -> None:
  parser = argparse.ArgumentParser(description="Run the Firestar Lateral Method analyzer against local routes.")
  parser.add_argument("routes", nargs="*", help="One or more local route ids or log paths.")
  parser.add_argument("--route", dest="route_args", nargs="+", default=[], help="Alternative to positional routes: local qlog/rlog paths or route ids.")
  parser.add_argument("--report-id", dest="report_id", default=None, help="Optional report id override.")
  parser.add_argument("--platform", dest="platform", default=None, help="Optional car platform (fingerprint) override.")
  parser.add_argument("--out", dest="out", default=None, help="Optional path to write the report/suggestion JSON.")
  parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Analyze only; never write Params or apply a trial profile.")
  args = parser.parse_args()

  routes = [route for route in (list(args.routes) + list(args.route_args)) if str(route).strip()]
  if not routes:
    parser.error("at least one route is required")

  route_ids = []
  footage_paths = list(flm_workspace.get_flm_footage_paths())
  for route in routes:
    route_id, footage_dir = _classify_route_arg(str(route))
    route_ids.append(route_id)
    if footage_dir and footage_dir not in footage_paths:
      footage_paths.append(footage_dir)

  report = flm_workspace.analyze_routes(
    route_ids,
    footage_paths,
    report_id=args.report_id,
    platform_override=args.platform,
  )
  payload = {
    "reportId": report["reportId"],
    "htmlPath": report["htmlPath"],
    "jsonPath": report["jsonPath"],
  }
  if args.out:
    with open(args.out, "w", encoding="utf-8") as f:
      json.dump(report, f, indent=2, sort_keys=True)
    payload["outPath"] = str(args.out)
  print(json.dumps(payload, indent=2))


if __name__ == "__main__":
  main()

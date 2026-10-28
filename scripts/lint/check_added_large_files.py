#!/usr/bin/env python3
import argparse
import math
import os
import subprocess


def lfs_files(filenames: list[str]) -> set[str]:
  if not filenames:
    return set()

  result = subprocess.run(
    ("git", "check-attr", "filter", "-z", "--stdin"),
    input="\0".join(filenames),
    check=True,
    capture_output=True,
    text=True,
  )
  fields = result.stdout.rstrip("\0").split("\0") if result.stdout else []
  return {fields[i] for i in range(0, len(fields), 3) if fields[i + 2] == "lfs"}


# Fork-level allowlist: these files exceed the size gate but must ship as plain git
# blobs because this fork cannot push to the sunnypilot LFS endpoint (see the
# cluster rules in .gitattributes, same precedent as the UI fonts/icons).
FORK_LARGE_ALLOWLIST = {
  "openpilot/sunnypilot/carrot/cluster/cluster_renderer.py",
  "openpilot/sunnypilot/carrot/cluster/cluster_route_replay.py",
  "openpilot/sunnypilot/carrot/cluster/cluster_scene.py",
  "openpilot/sunnypilot/carrot/cluster/radar_trajectory_labels.json",
  "openpilot/sunnypilot/carrot/cluster/assets/models/cybertruck/cybertruck_cluster.obj",
  # Vision models. .gitattributes deliberately overrides the global *.onnx LFS
  # rule for these paths so they ship as plain blobs, which means the LFS
  # exemption above does not cover them.
  "openpilot/sunnypilot/assets/vision_models/speed_limit_us_detector.onnx",
  "openpilot/sunnypilot/assets/vision_models/speed_limit_us_reject_classifier.onnx",
  "openpilot/sunnypilot/assets/vision_models/speed_limit_us_value_classifier.onnx",
  "openpilot/sunnypilot/assets/vision_models/signal_light_detector.onnx",
  "openpilot/sunnypilot/carrot/xiaoge/assets/lane.onnx",
  "openpilot/sunnypilot/carrot/xiaoge/assets/v_asm_model.onnx",
  "openpilot/sunnypilot/carrot/xiaoge/assets/yolov8n_192.onnx",
}


def check_added_large_files(filenames: list[str], max_kb: int) -> int:
  failed = False
  ignored = lfs_files(filenames) | FORK_LARGE_ALLOWLIST
  for filename in filenames:
    if filename in ignored:
      continue

    size_kb = math.ceil(os.stat(filename).st_size / 1024)
    if size_kb > max_kb:
      print(f"{filename} ({size_kb} KB) exceeds {max_kb} KB.")
      failed = True

  return int(failed)


def main() -> int:
  parser = argparse.ArgumentParser(description="Check that tracked files do not exceed a size limit.")
  parser.add_argument("filenames", nargs="*")
  parser.add_argument("--maxkb", type=int, default=500, help="maximum allowable size in KiB")
  args = parser.parse_args()
  return check_added_large_files(args.filenames, args.maxkb)


if __name__ == "__main__":
  raise SystemExit(main())

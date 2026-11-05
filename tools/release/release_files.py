#!/usr/bin/env python3
import os
import re
import subprocess
import sys

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "../.."))

blacklist = [
  ".git/",
  ".venv/",
  ".github/workflows/",

  "matlab.*.md",

  # release scripts configure LFS for the big driving model and warps
  ".lfsconfig",
  ".gitattributes",
  ".git$",
  ".gitmodules",
  ".run/",
  ".idea/",

  # jetlink: the comma imports the package and runs scripts/comma/ (jetlink.comma.root);
  # the rest of the submodule is the Jetson's, the Mac's and the iPhone's
  "^jetlink_repo/(?!jetlink/|scripts/comma/|LICENSE$)",
]

# gets you through the blacklist
whitelist: list[str] = [r"^\.lfsconfig$"] if os.getenv("INCLUDE_BIG_MODEL") else []


if __name__ == "__main__":
  # --stage so modes are visible: a gitlink (mode 160000) packages as an empty
  # file and a merge conflict (stage != 0) packages garbage. Registered
  # submodules recurse into real files; an UNREGISTERED gitlink is a
  # dependency accidentally committed as a pointer -> refuse loudly.
  entries = subprocess.check_output(["git", "ls-files", "--stage", "-z", "--recurse-submodules"], cwd=ROOT).split(b"\0")
  registered_submodules = subprocess.check_output(
    ["git", "config", "-f", ".gitmodules", "--get-regexp", r"submodule\..*\.path"], cwd=ROOT
  ).decode().splitlines()
  registered_submodules = {
    line.split("=", 1)[1].strip() if "=" in line else line.split(None, 1)[1].strip()
    for line in registered_submodules if line.strip()
  }

  for entry in entries:
    if not entry:
      continue

    metadata, tracked_file = entry.split(b"\t", 1)
    mode, _, stage = metadata.split()
    rf = os.fsdecode(tracked_file)
    if mode == b"160000":
      if rf in registered_submodules:
        continue  # registered submodule pointer: contents are packaged by the recursion
      raise ValueError(f"Cannot package gitlink: {rf}; dependency sources must be tracked files")
    if stage != b"0":
      raise ValueError(f"Cannot package unresolved merge: {rf}")

    if not os.getenv("INCLUDE_BIG_MODEL") and rf.startswith("openpilot/selfdrive/modeld/models/big_"):
      continue
    blacklisted = any(re.search(p, rf) for p in blacklist)
    whitelisted = any(re.search(p, rf) for p in whitelist)
    if blacklisted and not whitelisted:
      continue

    sys.stdout.buffer.write(tracked_file + b"\0")

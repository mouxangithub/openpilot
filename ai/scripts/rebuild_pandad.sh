#!/usr/bin/env bash
# Rebuild pandad on comma hardware (nested sunnypilot layout).
set -euo pipefail

ROOT="${OPENPILOT_ROOT:-/data/openpilot}"
if [ -f "$ROOT/openpilot/selfdrive/pandad/pandad" ] || [ -d "$ROOT/openpilot/selfdrive/pandad" ]; then
  SRC="$ROOT/openpilot"
elif [ -d "$ROOT/selfdrive/pandad" ]; then
  SRC="$ROOT"
else
  echo "pandad source not found under $ROOT" >&2
  exit 1
fi

cd "$SRC"
scons -j"$(nproc)" selfdrive/pandad/pandad
echo "rebuild_done: $SRC/selfdrive/pandad/pandad"

#!/usr/bin/env bash
# Start op 助手 (ai.aid) with scons native modules + venv aiohttp.
set -euo pipefail
ROOT="${OPENPILOT_ROOT:-/data/openpilot}"
VENV_SITE="/usr/local/venv/lib/python3.12/site-packages"
PY=python3.12
command -v "$PY" >/dev/null 2>&1 || PY=python3
export PYTHONPATH="$ROOT:$VENV_SITE${PYTHONPATH:+:$PYTHONPATH}"

SO="$ROOT/openpilot/common/params_pyx.so"
[ -f "$SO" ] || SO="$ROOT/common/params_pyx.so"
if [ ! -f "$SO" ]; then
  echo "params_pyx.so not found — run: cd $ROOT/system/manager && ./build.py" >&2
  exit 1
fi

cd "$ROOT"
if pgrep -f "[p]ython.* -m ai\.aid" >/dev/null 2>&1; then
  echo "ai.aid already running"
  exit 0
fi
exec "$PY" -m ai.aid

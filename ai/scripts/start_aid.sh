#!/usr/bin/env bash

# Start op 助手 (ai.aid) with scons native modules + venv aiohttp.

set -euo pipefail

ROOT="${OPENPILOT_ROOT:-/data/openpilot}"

VENV_SITE="/usr/local/venv/lib/python3.12/site-packages"

PYDEPS="$ROOT/.pydeps"

PY=python3.12

command -v "$PY" >/dev/null 2>&1 || PY=python3

export PYTHONPATH="$ROOT:$VENV_SITE${PYDEPS:+:$PYDEPS}${PYTHONPATH:+:$PYTHONPATH}"



_params_native_ok=0

for rel in \

  openpilot/common/libparams_c.so \

  common/libparams_c.so \

  openpilot/common/params_pyx.so \

  common/params_pyx.so; do

  if [ -f "$ROOT/$rel" ]; then

    _params_native_ok=1

    break

  fi

done

if [ "$_params_native_ok" -eq 0 ]; then

  echo "Params native lib not found (libparams_c.so or legacy params_pyx.so)" >&2

  echo "  run: cd $ROOT/openpilot/system/manager && ./build.py" >&2

  echo "  (read_params/write_params need it; ai_* in /data/ai/config.json does not)" >&2

fi



cd "$ROOT"

if pgrep -f "[p]ython.* -m ai\.aid" >/dev/null 2>&1; then

  echo "ai.aid already running"

  exit 0

fi

exec "$PY" -m ai.aid


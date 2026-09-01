#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PYDEPS_DIR="/data/.pydeps"    # outside $DIR so overlay updates do not wipe pip deps

# AGNOS updates can drop /usr/local/venv/bin from PATH. Restore it so scons,
# pip and the venv Python wrappers are reachable.
export PATH="/usr/local/venv/bin:${PATH}"

source "$DIR/launch_env.sh"

# ---------------------------------------------------------------------------
# Shared helpers for Python path setup and dependency bootstrapping.
# AGNOS rootfs is read-only; pip deps are installed into $PYDEPS_DIR on first boot.
# ---------------------------------------------------------------------------
find_python() {
  local py="$1"
  command -v "$py" >/dev/null 2>&1 && echo "$py" && return 0
  command -v python3 >/dev/null 2>&1 && echo python3 && return 0
  return 1
}

setup_python_path() {
  local root="$1"
  local venv_site="/usr/local/venv/lib/python3.12/site-packages"
  local py_path="$root"
  [ -d "$venv_site" ] && py_path="$py_path:$venv_site"
  [ -d "$PYDEPS_DIR" ] && py_path="$py_path:$PYDEPS_DIR"
  echo "$py_path"
}

# Ensures pip is available and the requested module is importable.
# Installs pip bootstrap + target package into $PYDEPS_DIR if needed.
ensure_pip_dep() {
  local module="$1"
  local pydeps="$PYDEPS_DIR"
  local py=$(find_python python3.12) || return 1
  local py_path=$(setup_python_path "$DIR")
  local lockfile="/tmp/ensure_pip_dep_${module}.lock"

  # Fast path: skip import check if the package directory already exists.
  [ -d "$pydeps/$module" ] && return 0

  # Only one pip install at a time; concurrent calls from keep-alive loops
  # race on the same .pydeps directory and slow each other down.
  exec 200>"$lockfile"
  flock 200 || return 1

  # Re-check after acquiring lock in case another instance just installed it.
  [ -d "$pydeps/$module" ] && return 0

  if ! PYTHONPATH="$py_path" "$py" -c "import $module" 2>/dev/null; then
    [ -d "$pydeps" ] || mkdir -p "$pydeps" 2>/dev/null || return 1
    if ! "$py" -c "import pip" 2>/dev/null; then
      # Device network cannot reach bootstrap.pypa.io, so prefer Aliyun mirror.
      curl -fsSL "${GET_PIP_URL:-https://mirrors.aliyun.com/pypi/get-pip.py}" -o /tmp/get-pip.py 2>/dev/null && \
        "$py" /tmp/get-pip.py --target="$pydeps" --no-warn-script-location >> /tmp/bootstrap.log 2>&1 || true
    fi
    local index_url="${PIP_INDEX_URL:-https://pypi.org/simple}"
    PYTHONPATH="$py_path" "$py" -m pip install --index-url="$index_url" --target="$pydeps" "$module" >> /tmp/bootstrap.log 2>&1 || true
  fi
}

start_service() {
  local name="$1"
  local script="$2"
  local logfile="/tmp/${name}.log"
  local root="$DIR"

  [ -f "$root/$script" ] || return 0
  local py="$PY"
  [ -n "$py" ] || py=$(find_python python3.12) || return 1
  local py_path="$PY_PATH"
  [ -n "$py_path" ] || py_path=$(setup_python_path "$root")

  local module="${script%.py}"
  module="${module//\//.}"
  pgrep -f "[p]ython.*$module" >/dev/null 2>&1 && return 0
  echo "[$name] starting $(date)" >> "$logfile"
  (cd "$root" && PYTHONPATH="$py_path" WEBUI_TLS=1 "$py" -m "$module" >> "$logfile" 2>&1 &)
}

# Background keep-alive for a service. Starts immediately, then restarts every
# $interval seconds if it died. Port is kept for readability only.
keep_alive() {
  local name="$1"
  local script="$2"
  local port="$3"
  local interval="${4:-45}"
  start_service "$name" "$script"
  while true; do
    sleep "$interval"
    start_service "$name" "$script"
  done
}

# ---------------------------------------------------------------------------
# Hardware detection and initialization
# ---------------------------------------------------------------------------

is_headless_boot() {
  case "${OPENPILOT_HEADLESS,,}" in 1|true|yes) return 0 ;; esac
  [ -d /sys/class/backlight/panel0-backlight ] && \
    ! grep -q fts_ts /proc/interrupts 2>/dev/null && \
    [ ! -e /dev/input/by-path/platform-894000.i2c-event ]
}

comma_device_slug() {
  tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null | awk '{print $NF}'
}

is_comma_big_hw() {
  case "$(comma_device_slug)" in tici|tizi) return 0 ;; esac
  return 1
}

set_tici_hw() {
  is_comma_big_hw || return 0
  export TICI_HW=1

  local cache="/persist/sp_dev_panda_mcu_type"
  local legacy_cache="/persist/dp_dev_panda_mcu_type"
  local attempts=15 confirm=3 mcu="" count=0 last="" cur cached

  # Fast path: check sp cache, then dragonpilot legacy cache
  for c in "$cache" "$legacy_cache"; do
    cached=$(cat "$c" 2>/dev/null)
    case "$cached" in F4|H7)
      mcu="$cached"; echo "panda MCU $mcu [cached]"
      break
    esac
  done

  # Slow path: detect panda MCU, requiring $confirm consecutive identical reads
  if [ -z "$mcu" ]; then
    echo "Querying panda MCU type..."
    for _ in $(seq 1 "$attempts"); do
      [ -n "$last" ] && sleep 1 || sleep 3
      case "$(${PY:-python3} -c "from panda import Panda; p = Panda(cli=False); print(p.get_mcu_type()); p.close()" 2>/dev/null)" in
        *McuType.F4*) cur="F4" ;;
        *McuType.H7*) cur="H7" ;;
        *)            cur="" ;;
      esac
      if [ -n "$cur" ] && [ "$cur" = "$last" ]; then
        ((++count))
      else
        count=1; last="$cur"
      fi
      [ -n "$cur" ] && [ "$count" -ge "$confirm" ] && mcu="$cur" && break
      echo "panda MCU read='${cur:-UNKNOWN}' (confirmed $count/$confirm)"
    done

    if [ -z "$mcu" ]; then
      echo "TICI (UNKNOWN) detected after $attempts attempts"; exit 1
    fi

    # Persist to /persist (read-only partition — remount rw for one write)
    if sudo mount -o remount,rw /persist 2>/dev/null; then
      echo "$mcu" | sudo tee "$cache" "$legacy_cache" >/dev/null 2>&1
      sudo mount -o remount,ro /persist 2>/dev/null
    fi
  fi

  if [ "$mcu" = "F4" ]; then
    echo "TICI (DOS) detected"; mount_nvme; export TICI_DOS=1; set_aux_panda
  else
    echo "TICI (TRES) detected"; export TICI_TRES=1
  fi
}

set_aux_panda() {
  local mode="/sys/devices/platform/soc/a600000.ssusb/mode"
  [ -e "$mode" ] || return 0
  echo "Checking for aux panda (switching USB-C port to host mode)..."
  echo host | sudo tee "$mode" >/dev/null 2>&1
  for _ in $(seq 1 6); do
    sleep 0.5
    [ "$(lsusb 2>/dev/null | grep -c 'comma.ai panda')" -ge 2 ] && \
      echo "aux panda detected" && return 0
  done
  echo "no aux panda found; reverting USB-C port to device mode"
  echo none | sudo tee "$mode" >/dev/null 2>&1
}

mount_nvme() {
  for i in $(seq 1 10); do
    [ -b /dev/nvme0n1p1 ] && break
    sleep 1
  done
  [ ! -b /dev/nvme0n1p1 ] && return 0

  if ! mountpoint -q /data/media/0/realdata; then
    mount /dev/nvme0n1p1 /data/media/0/realdata
  fi

  if mountpoint -q /data/media/0/realdata; then
    OWNER="$(stat -c '%U' /data/media/0/realdata)"
    GROUP="$(stat -c '%G' /data/media/0/realdata)"
    PERM="$(stat -c '%a' /data/media/0/realdata)"
    [ "$OWNER" != "comma" ] || [ "$GROUP" != "comma" ] && chown comma:comma /data/media/0/realdata
    [ "$PERM" != "755" ] && chmod 755 /data/media/0/realdata
  fi
}

set_lite_hw() {
  [ "$(comma_device_slug)" = "tici" ] || return 0
  [ -z "$(i2cget -y 0 0x10 0x00 2>/dev/null)" ] && echo "Lite HW" && export LITE=1
}

agnos_init() {
  sudo rm -f /data/etc/NetworkManager/system-connections/*.nmmeta
  rm -f /data/scons_cache/config.lock
  sudo abctl --set_success
  sudo chgrp gpu /dev/adsprpc-smd /dev/ion /dev/kgsl-3d0
  sudo chmod 660 /dev/adsprpc-smd /dev/ion /dev/kgsl-3d0

  [ "$(< /VERSION)" = "$AGNOS_VERSION" ] && return 0

  local agnos_py="$DIR/openpilot/common/hardware/comma/agnos.py"
  local manifest="$DIR/openpilot/system/hardware/comma/agnos.json"
  if $agnos_py --verify $manifest; then
    sudo reboot
  fi
  if is_headless_boot; then
    echo "[agnos] headless: OS update required ($(cat /VERSION) -> $AGNOS_VERSION). Use WebUI Software → AGNOS, or SSH: $agnos_py --swap $manifest" | tee -a /tmp/agnos_pending.log
    return 0
  fi

  while true; do
    PYTHONPATH="$PY_PATH" "$PY" "$DIR/openpilot/common/hardware/comma/updater" "$agnos_py" "$manifest"
  done
}

link_repos() {
  for repo in msgq opendbc rednose teleoprtc tinygrad; do
    ln -sfn "${repo}_repo/$repo" "$repo"
  done
}

bootstrap_deps() {
  ensure_pip_dep aiohttp
  ensure_pip_dep jeepney
}

# Build the minimal Params shared library before starting services that need it.
# After an overlay update the compiled .so is missing; building it here avoids
# webui falling back to dev/mock mode.
ensure_params_build() {
  local so="$DIR/openpilot/common/libparams_c.so"
  [ -f "$so" ] && return 0
  local jobs=$(nproc 2>/dev/null || echo 2)
  echo "[ensure_params_build] building libparams_c.so ($jobs jobs)..."
  (cd "$DIR" && PYTHONPATH="$PY_PATH" scons -j"$jobs" openpilot/common/libparams_c.so >> /tmp/params_build.log 2>&1) || true
}

launch() {
  [ -f "$DIR/.git/index.lock" ] && rm -f "$DIR/.git/index.lock"

  if [ -f "${DIR}/.overlay_init" ]; then
    if find "${DIR}/.git" -newer "${DIR}/.overlay_init" | grep -q . 2>/dev/null; then
      echo "${DIR} has been modified, skipping overlay update installation"
    elif [ -f "${STAGING_ROOT}/finalized/.overlay_consistent" ] && [ ! -d /data/safe_staging/old_openpilot ]; then
      echo "Valid overlay update found, installing"
      local launcher="${BASH_SOURCE[0]}"
      mv "$DIR" /data/safe_staging/old_openpilot
      mv "${STAGING_ROOT}/finalized" "$DIR"
      cd "$DIR"
      echo "Restarting launch script ${launcher}"
      unset AGNOS_VERSION
      exec "${launcher}"
    fi
  fi

  ln -sfn "$(pwd)" /data/pythonpath
  export PYTHONPATH="$PWD"
  link_repos

  # Resolve Python interpreter and path once, then reuse in service loops.
  # Create .pydeps early so PY_PATH already includes it and does not need
  # to be recomputed after pip install.
  mkdir -p "$PYDEPS_DIR"
  PY=$(find_python python3.12) || PY=python3
  PY_PATH=$(setup_python_path "$DIR")
  export PY PY_PATH

  # Use a PyPI mirror by default; the device's network currently cannot reach
  # pypi.org (it resolves to a placeholder IP), so Aliyun mirror is used.
  export PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"

  # Bootstrap shared Python deps once at boot.
  bootstrap_deps

  sudo mkdir -p /cache/tsk
  sudo chown comma:comma /cache/tsk

  # AGNOS-specific hardware detection (slow on first boot, cached afterwards)
  [ -f /AGNOS ] && { set_tici_hw; set_lite_hw; }

  # Build Params .so before services need it; after an overlay update it is
  # missing and would cause webui to fall back to dev/mock mode.
  ensure_params_build

  # Start AI and WebUI before the AGNOS OS update so they stay reachable even
  # if the updater loops waiting for user confirmation.
  keep_alive aid ai/aid.py 5090 &
  keep_alive webui webui/webuid.py 5080 &

  # AGNOS OS update (may loop updater)
  [ -f /AGNOS ] && agnos_init

  tmux capture-pane -pq -S-1000 > /tmp/launch_log

  cd openpilot/system/manager
  [ ! -f "$DIR/prebuilt" ] && ./build.py
  ./manager.py

  while true; do sleep 1; done
}

launch

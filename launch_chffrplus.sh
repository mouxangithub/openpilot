#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

source "$DIR/launch_env.sh"

# ---------------------------------------------------------------------------
# Shared helpers for Python path setup and dependency bootstrapping.
# AGNOS rootfs is read-only; pip deps are installed into $DIR/.pydeps on first boot.
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
  local pydeps="$root/.pydeps"
  local py_path="$root"
  [ -d "$venv_site" ] && py_path="$py_path:$venv_site"
  [ -d "$pydeps" ] && py_path="$py_path:$pydeps"
  echo "$py_path"
}

# Ensures pip is available and the requested module is importable.
# Installs pip bootstrap + target package into $DIR/.pydeps if needed.
ensure_pip_dep() {
  local module="$1"
  local pydeps="$DIR/.pydeps"
  local py_path  # set by caller via setup_python_path before calling

  if ! PYTHONPATH="$py_path" "$py" -c "import $module" 2>/dev/null; then
    [ -d "$pydeps" ] || mkdir -p "$pydeps" 2>/dev/null || return 1
    if ! "$py" -c "import pip" 2>/dev/null; then
      curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py 2>/dev/null && \
        "$py" /tmp/get-pip.py --target="$pydeps" --no-warn-script-location >> /tmp/bootstrap.log 2>&1 || true
    fi
    PYTHONPATH="$py_path" "$py" -m pip install --target="$pydeps" "$module" >> /tmp/bootstrap.log 2>&1 || true
  fi
}

start_service() {
  local name="$1"           # webui|aid
  local script="$2"        # path relative to root, used for pgrep and module invocation
  local port="$3"          # unused but kept for parity
  local logfile="/tmp/${name}.log"
  local root="$DIR"

  [ -f "$root/$script" ] || return 0
  py=$(find_python python3.12) || return 1
  local py_path=$(setup_python_path "$root")

  ensure_pip_dep aiohttp
  # Re-evaluate py_path after potential install
  py_path=$(setup_python_path "$root")

  pgrep -f "[p]ython.* -m ${script%.py}" >/dev/null 2>&1 && return 0
  echo "[$name] starting $(date)" >> "$logfile"
  (cd "$root" && PYTHONPATH="$py_path" WEBUI_TLS=1 "$py" -m "$script" >> "$logfile" 2>&1 &)
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
      case "$(python -c "from panda import Panda; p = Panda(cli=False); print(p.get_mcu_type()); p.close()" 2>/dev/null)" in
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

function agnos_init {
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

  py=$(find_python python3.12) || py=python3
  local py_path=$(setup_python_path "$DIR")
  ensure_pip_dep jeepney
  py_path=$(setup_python_path "$DIR")

  while true; do
    PYTHONPATH="$py_path" "$py" "$DIR/openpilot/common/hardware/comma/updater" "$agnos_py" "$manifest"
  done
}

function launch {
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

  ln -sfn msgq_repo/msgq msgq
  ln -sfn opendbc_repo/opendbc opendbc
  ln -sfn rednose_repo/rednose rednose
  ln -sfn teleoprtc_repo/teleoprtc teleoprtc
  ln -sfn tinygrad_repo/tinygrad tinygrad

  [ -f /AGNOS ] && { set_tici_hw; set_lite_hw; agnos_init; }

  tmux capture-pane -pq -S-1000 > /tmp/launch_log

  sudo mkdir -p /cache/tsk
  sudo chown comma:comma /cache/tsk

  # WebUI and op_assistant with 45s keep-alive loop
  start_service webui webui/webuid.py 5080 &
  (while true; do sleep 45; start_service webui webui/webuid.py 5080; done) &
  start_service aid ai.aid.py 5090 &
  (while true; do sleep 45; start_service aid ai.aid.py 5090; done) &

  cd openpilot/system/manager
  [ ! -f "$DIR/prebuilt" ] && ./build.py
  ./manager.py

  while true; do sleep 1; done
}

launch

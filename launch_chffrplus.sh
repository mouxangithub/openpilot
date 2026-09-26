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
    PYTHONPATH="$py_path" "$py" -m pip install --index-url="$index_url" --target="$pydeps" "$module" >> /tmp/bootstrap.log 2>&1 || return 1
  fi
}

# Waits up to $1 seconds for a working DNS resolver. Returns 0 as soon as a
# known host resolves, 1 on timeout. Prevents pip install races at early boot
# when systemd-resolved is still populating its cache.
wait_for_dns() {
  local timeout="${1:-60}"
  # Resolve the interpreter the same way the rest of the script does: a bare
  # "python3.12" is not guaranteed to be on PATH at early boot, and a missing
  # command would report DNS failure forever instead of probing it.
  local py="${PY:-}"
  [ -n "$py" ] || py=$(find_python python3.12) || py=python3
  local waited=0
  while [ "$waited" -lt "$timeout" ]; do
    if "$py" -c "import socket; socket.getaddrinfo('mirrors.aliyun.com', None)" 2>/dev/null; then
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}

# Ensures a list of pip packages are importable.
# More efficient than repeated ensure_pip_dep calls because a single pip
# invocation resolves the dependency graph once. Failures are propagated so
# that overlay updates cannot silently leave ai/webui without dependencies.
ensure_pip_deps() {
  local pydeps="$PYDEPS_DIR"
  local py=$(find_python python3.12) || return 1
  local py_path=$(setup_python_path "$DIR")
  local lockfile="/tmp/ensure_pip_deps.lock"
  shift 0

  exec 200>"$lockfile"
  flock 200 || return 1

  local missing=()
  for module in "$@"; do
    if ! PYTHONPATH="$py_path" "$py" -c "import $module" 2>/dev/null; then
      missing+=("$module")
    fi
  done

  if [ ${#missing[@]} -eq 0 ]; then
    return 0
  fi

  echo "[ensure_pip_deps] missing: ${missing[*]}; waiting for DNS..." >> /tmp/bootstrap.log
  if ! wait_for_dns 60; then
    echo "[ensure_pip_deps] DNS not ready after 60s; deferring install" >> /tmp/bootstrap.log
    # Must report failure, not success: the caller uses this status to decide
    # whether to keep retrying. Returning 0 here would look like "deps are fine"
    # and the packages would never be installed, leaving aid/webui crash-looping
    # until someone restarted the device by hand.
    return 1
  fi

  [ -d "$pydeps" ] || mkdir -p "$pydeps" 2>/dev/null || return 1
  if ! "$py" -c "import pip" 2>/dev/null; then
    curl -fsSL "${GET_PIP_URL:-https://mirrors.aliyun.com/pypi/get-pip.py}" -o /tmp/get-pip.py 2>/dev/null && \
      "$py" /tmp/get-pip.py --target="$pydeps" --no-warn-script-location >> /tmp/bootstrap.log 2>&1 || return 1
  fi

  local index_url="${PIP_INDEX_URL:-https://pypi.org/simple}"
  # --upgrade makes this a real repair path: a package directory left behind by an
  # interrupted download makes plain install report "already exists" and skip the
  # copy, so the import check would keep failing and the retry loop would spin.
  if ! PYTHONPATH="$py_path" "$py" -m pip install --upgrade --index-url="$index_url" --target="$pydeps" "${missing[@]}" >> /tmp/bootstrap.log 2>&1; then
    echo "[ensure_pip_deps] install failed; will retry on next keep_alive cycle" >> /tmp/bootstrap.log
    return 1
  fi
  echo "[ensure_pip_deps] installed: ${missing[*]}" >> /tmp/bootstrap.log
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
  # WEBUI_TLS 默认关闭（HTTP），避免自签名证书导致浏览器 ERR_SSL_PROTOCOL_ERROR；
  # 需要 HTTPS 时手动 export WEBUI_TLS=1。
  local tls_env=""
  if [ "${WEBUI_TLS:-0}" = "1" ]; then
    tls_env="WEBUI_TLS=1"
  fi
  (cd "$root" && PYTHONPATH="$py_path" $tls_env "$py" -m "$module" >> "$logfile" 2>&1 &)
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
  # Only the explicit environment variable disables the native UI. Some C3
  # boots leave the touchscreen controller unprobed while the display panel
  # itself is functional. In that case we still want the native UI to start
  # (with a virtual touch fallback if necessary).
  case "${OPENPILOT_HEADLESS,,}" in 1|true|yes) return 0 ;; esac
  return 1
}

# The COMMA raylib platform and /usr/comma/magic.py require /dev/input/event2.
# When the real touch driver failed to probe, create a minimal virtual device
# via /dev/uinput so DRM/EGL initialization can succeed.
ensure_touch_input() {
  [ -e /dev/input/event2 ] && return 0
  sudo chmod 666 /dev/uinput 2>/dev/null || true
  keep_alive fake_touch openpilot/system/ui/lib/fake_touch.py 0 &
  local n=0
  while [ ! -e /dev/input/event2 ] && [ $n -lt 60 ]; do
    sleep 0.2
    n=$((n+1))
  done
}

# magic.py serves /tmp/drmfd.sock, which passes a DRM master fd to the UI.
# If the system magic.service failed (usually due to missing touch), start it
# ourselves once the touch input is available.
ensure_magic_service() {
  [ -S /tmp/drmfd.sock ] && return 0
  keep_alive magic scripts/magic_wrapper.py 0 &
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
      echo "[warn] TICI (UNKNOWN) detected after $attempts attempts, continuing without panda MCU detection"
      # 不退出：允许 panda 未连接/固件不兼容的设备继续启动 webui/manager，便于调试和首次安装
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
  # Core deps needed by ai/aid.py and webui/webuid.py. Installed together so a
  # single overlay update does not leave either service unable to import.
  ensure_pip_deps aiohttp jinja2 pyzmq zstandard numpy requests tqdm jeepney
}

# Retries bootstrap_deps() until it succeeds, because a single attempt at boot is
# not enough on a fresh install: DNS and the network are often not ready yet, and
# the pip mirror can fail transiently. Without this loop the deps would stay
# missing until the next manual restart and aid/webui would crash-loop the whole
# time. Exits as soon as the deps import, so there is no steady-state cost.
bootstrap_deps_retry() {
  local fast_interval=15 fast_attempts=40 slow_interval=300
  local attempt=0
  while true; do
    if bootstrap_deps; then
      echo "[bootstrap_deps_retry] dependencies satisfied (attempt $((attempt + 1)))" >> /tmp/bootstrap.log
      return 0
    fi
    attempt=$((attempt + 1))
    if [ "$attempt" -lt "$fast_attempts" ]; then
      sleep "$fast_interval"
    else
      # Keep retrying at a slow cadence so a device that boots offline still
      # heals on its own once a connection appears.
      [ "$attempt" -eq "$fast_attempts" ] && \
        echo "[bootstrap_deps_retry] still missing after $fast_attempts attempts; backing off to ${slow_interval}s" >> /tmp/bootstrap.log
      sleep "$slow_interval"
    fi
  done
}

# Build the minimal Params shared library before starting services that need it.
# After an overlay update the compiled .so is missing; building it here avoids
# webui falling back to dev/mock mode.
ensure_params_build() {
  local so="$DIR/openpilot/common/libparams_c.so"
  [ -f "$so" ] && return 0
  local jobs=$(nproc 2>/dev/null || echo 2)
  echo "[ensure_params_build] building libparams_c.so ($jobs jobs)..."
  if ! (cd "$DIR" && PYTHONPATH="$PY_PATH" scons -j"$jobs" openpilot/common/libparams_c.so >> /tmp/params_build.log 2>&1); then
    echo "[warn] ensure_params_build failed, webui may fall back to dev/mock mode"
  fi
}

# BlueZ is not shipped on C3, but the Carrot Bluetooth HID remote feature needs
# the org.bluez D-Bus service. Install it once per boot if it is missing; the
# actual work runs in the background so it does not block the boot sequence.
#
# The carrot-bluetooth-radio.service (which runs btattach to bring up hci0) has:
#   ExecCondition=/usr/bin/test -f /data/bluetooth/ENABLED
# Without this file the service is skipped and hci0 never appears.
#
# THREE-LAYER ENSURE STRATEGY to eliminate all race conditions:
#   1. Fast path (BlueZ already installed):  create ENABLED + start service in main shell.
#   2. First-boot (main shell, before subshell):  same – ensures the service never sees a
#      missing ENABLED file even when apt-get is still running in the background.
#   3. Retry path (subshell install):  re-creates ENABLED + restarts service when apt-get
#      finally succeeds (idempotent, no harm if called twice).
#
# HARDWARE COMPATIBILITY: carrot-bluetooth-radio needs /dev/btpower and /dev/ttyHS1.
# If /dev/ttyHS1 is missing the current AGNOS kernel does not expose the WCN3990
# Bluetooth UART; starting the service would just fail-loop.  We still create ENABLED
# (so the radio auto-starts after the user flashes a Bluetooth-capable AGNOS) but we
# skip starting the doomed service and log a clear warning instead.
ensure_bluez() {
  # Helper: create /data/bluetooth/ENABLED and start the BlueZ D-Bus service.
  # Idempotent – safe to call multiple times.
  start_bluez_dbus() {
    sudo mkdir -p /data/bluetooth
    sudo chmod 777 /data/bluetooth
    sudo touch /data/bluetooth/ENABLED
    sudo chmod 666 /data/bluetooth/ENABLED
    sudo systemctl start bluetooth >> /tmp/bluez_install.log 2>&1
  }

  # Helper: start the carrot-bluetooth-radio service only if the underlying hardware
  # nodes are available.  Without /dev/ttyHS1 the service's ExecStartPre will crash-loop,
  # so stop any already-running instance and do not start a new one.
  start_carrot_bt_radio() {
    if [ ! -e /dev/ttyHS1 ] || [ ! -e /dev/btpower ]; then
      local missing=""
      [ ! -e /dev/ttyHS1 ] && missing="/dev/ttyHS1"
      [ ! -e /dev/btpower ] && missing="${missing}${missing:+, }/dev/btpower"
      echo "[ensure_bluez] ${missing} missing; this device/AGNOS lacks Bluetooth radio hardware, stopping carrot-bluetooth-radio" >> /tmp/bluez_install.log
      sudo systemctl stop carrot-bluetooth-radio >> /tmp/bluez_install.log 2>&1 || true
      return 0
    fi
    sudo systemctl start carrot-bluetooth-radio >> /tmp/bluez_install.log 2>&1
  }

  if command -v bluetoothctl >/dev/null 2>&1 && command -v bluetoothd >/dev/null 2>&1; then
    # Fast path: BlueZ already installed – create ENABLED and bring up the radio now.
    echo "[ensure_bluez] bluez already present; ensuring radio is up" >> /tmp/bluez_install.log
    start_bluez_dbus
    start_carrot_bt_radio
    return 0
  fi

  # First-boot install: BlueZ is not installed yet.
  # LAYER 2 – create ENABLED and start the BlueZ service HERE in the main shell,
  # before we fork the background subshell.  This eliminates the race where systemd
  # starts carrot-bluetooth-radio.service before the subshell finishes creating ENABLED.
  echo "[ensure_bluez] bluez missing; creating ENABLED and starting dbus before background install" >> /tmp/bluez_install.log
  start_bluez_dbus
  start_carrot_bt_radio

  # If a previous install attempt already ran (and failed), do NOT retry here – the
  # ENABLED file is already created and the service is already running.  If BlueZ
  # eventually gets installed later (e.g. next boot or manual apt-get), a subsequent
  # call to ensure_bluez() will pick it up via the fast path above.
  [ -f /tmp/.bluez_install_attempted ] && return 0
  touch /tmp/.bluez_install_attempted

  # LAYER 3 – download and install in the background.  If it succeeds, re-creates
  # ENABLED and restarts the service (idempotent; also covers retries after a
  # previous failed attempt finally succeeded).
  (
    if sudo apt-get update >> /tmp/bluez_install.log 2>&1; then
      if sudo apt-get install -y bluez >> /tmp/bluez_install.log 2>&1; then
        # BlueZ package postinst handles enable; start it explicitly so we can
        # immediately create the ENABLED flag and bring up hci0.
        sudo systemctl enable bluetooth >> /tmp/bluez_install.log 2>&1
        start_bluez_dbus
        start_carrot_bt_radio
        echo "[ensure_bluez] installed and started" >> /tmp/bluez_install.log
      else
        echo "[ensure_bluez] install failed" >> /tmp/bluez_install.log
      fi
    else
      echo "[ensure_bluez] apt-get update failed" >> /tmp/bluez_install.log
    fi
  ) &
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
  # Resolve Python interpreter and path once, then reuse in service loops.
  # Create .pydeps early so PY_PATH already includes it and does not need
  # to be recomputed after pip install.
  mkdir -p "$PYDEPS_DIR"
  PY=$(find_python python3.12) || PY=python3
  PY_PATH=$(setup_python_path "$DIR")
  export PY PY_PATH

  # PYTHONPATH must be the SAME set as PY_PATH, not just $PWD.
  #
  # manager.py is started later with `./manager.py` and inherits PYTHONPATH, and
  # openpilot/system/manager/process.py launches every daemon via
  # subprocess.Popen(...) with no env= argument, so every daemon inherits it too.
  # With PYTHONPATH=$PWD alone, /data/.pydeps was on PY_PATH but NOT on the
  # environment, so daemons could not import the pip deps that bootstrap_deps()
  # installs there. The concrete symptom on a C3 was carrot_navi printing
  # "aiohttp is not installed; 7714 v2 WebSocket receiver cannot start" and then
  # idling forever, so port 7714 never listened while the process looked healthy.
  #
  # aid/webui were unaffected only because keep_alive passes PYTHONPATH="$py_path"
  # explicitly; manager's children get no such help.
  export PYTHONPATH="$PY_PATH"
  link_repos

  # Use a PyPI mirror by default; the device's network currently cannot reach
  # pypi.org (it resolves to a placeholder IP), so Aliyun mirror is used.
  export PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"

  # Bootstrap shared Python deps. The first attempt runs inline so the common
  # case (deps already installed) costs one import check. If it is not satisfied
  # yet, a background loop keeps retrying until the deps import so aid/webui
  # recover without a manual restart.
  if bootstrap_deps; then
    echo "[bootstrap_deps] satisfied at boot" >> /tmp/bootstrap.log
  else
    echo "[bootstrap_deps] not satisfied at boot; retrying in background" >> /tmp/bootstrap.log
    bootstrap_deps_retry >> /tmp/bootstrap.log 2>&1 &
  fi

  sudo mkdir -p /cache/tsk
  sudo chown comma:comma /cache/tsk

  # AGNOS-specific hardware detection (slow on first boot, cached afterwards)
  [ -f /AGNOS ] && { set_tici_hw; set_lite_hw; }

  # Build Params .so before services need it; after an overlay update it is
  # missing and would cause webui to fall back to dev/mock mode.
  ensure_params_build

  # BlueZ is required for the Carrot Bluetooth HID remote panel. It is not
  # present on a fresh C3 image, so install it on first boot if missing.
  ensure_bluez

  # Start AI and WebUI before the AGNOS OS update so they stay reachable even
  # if the updater loops waiting for user confirmation.
  keep_alive aid ai/aid.py 5090 &
  keep_alive webui webui/webuid.py 5080 &

  # Ensure DRM fd socket is available for the native UI. On devices where the
  # panel backlight is present but the touch controller did not probe, the
  # system magic.service fails; we fall back to a virtual touch device and a
  # userspace magic.py instance.
  is_comma_big_hw && { ensure_touch_input; ensure_magic_service; }

  # AGNOS OS update (may loop updater)
  [ -f /AGNOS ] && agnos_init

  tmux capture-pane -pq -S-1000 > /tmp/launch_log

  cd openpilot/system/manager
  if [ ! -f "$DIR/prebuilt" ]; then
    if ! ./build.py; then
      echo "[warn] build.py failed, UI resources may be missing"
    else
      touch "$DIR/prebuilt"
    fi
  fi
  ./manager.py

  while true; do sleep 1; done
}

launch

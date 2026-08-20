#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

source "$DIR/launch_env.sh"

is_headless_boot() {
  case "${OPENPILOT_HEADLESS,,}" in 1|true|yes) return 0 ;; esac
  if [ -d /sys/class/backlight/panel0-backlight ]; then
    if ! grep -q fts_ts /proc/interrupts 2>/dev/null && \
       [ ! -e /dev/input/by-path/platform-894000.i2c-event ]; then
      return 0
    fi
  fi
  return 1
}

function agnos_init {
  # TODO: move this to agnos
  sudo rm -f /data/etc/NetworkManager/system-connections/*.nmmeta
  rm -f /data/scons_cache/config.lock

  # set success flag for current boot slot
  sudo abctl --set_success

  # TODO: do this without udev in AGNOS
  # udev does this, but sometimes we startup faster
  sudo chgrp gpu /dev/adsprpc-smd /dev/ion /dev/kgsl-3d0
  sudo chmod 660 /dev/adsprpc-smd /dev/ion /dev/kgsl-3d0

  # Check if AGNOS update is required
  if [ $(< /VERSION) != "$AGNOS_VERSION" ]; then
    AGNOS_PY="$DIR/openpilot/common/hardware/comma/agnos.py"
    MANIFEST="$DIR/openpilot/common/hardware/comma/agnos.json"
    if [ ! -f "$MANIFEST" ]; then
      MANIFEST="$DIR/openpilot/system/hardware/comma/agnos.json"
    fi
    if [ ! -f "$MANIFEST" ]; then
      MANIFEST="$DIR/common/hardware/comma/agnos.json"
    fi
    if $AGNOS_PY --verify $MANIFEST; then
      sudo reboot
    fi
    if is_headless_boot; then
      echo "[agnos] headless: OS update required ($(cat /VERSION) -> $AGNOS_VERSION). Use WebUI Software → AGNOS, or SSH: $AGNOS_PY --swap $MANIFEST" | tee -a /tmp/agnos_pending.log
      return 0
    fi
    while true; do
      $DIR/openpilot/common/hardware/comma/updater $AGNOS_PY $MANIFEST
    done
  fi
}

# Determine the panda MCU type (F4=DOS, H7=TRES) and set the TICI_* env vars.
# The MCU type is a permanent hardware fact, so it is detected once and cached in
# /persist (survives fork switch / reset / reflash); every later boot reads the
# cache and skips the panda query entirely.
comma_device_slug() {
  tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null | awk '{print $NF}'
}

is_comma_big_hw() {
  case "$(comma_device_slug)" in
    tici|tizi) return 0 ;;
    *) return 1 ;;
  esac
}

set_tici_hw() {
  is_comma_big_hw || return 0
  export TICI_HW=1

  local cache="/persist/sp_dev_panda_mcu_type"
  local legacy_cache="/persist/dp_dev_panda_mcu_type"
  local attempts=15 confirm=3         # give up after N reads; trust after M in a row
  local mcu="" count=0 last="" cur cached

  # --- fast path: sp cache, then openpilot/dragonpilot legacy cache ---
  cached=$(cat "$cache" 2>/dev/null)
  case "$cached" in
    F4|H7) mcu="$cached"; echo "panda MCU $mcu [cached]" ;;
  esac

  if [ -z "$mcu" ]; then
    cached=$(cat "$legacy_cache" 2>/dev/null)
    case "$cached" in
      F4|H7) mcu="$cached"; echo "panda MCU $mcu [legacy cache]" ;;
    esac
  fi

  # --- slow path: detect, requiring M consecutive identical reads to reject a
  #     transient misread while the panda enumerates, then persist for next boot ---
  if [ -z "$mcu" ]; then
    echo "Querying panda MCU type..."
    for attempt in $(seq 1 "$attempts"); do
      # wait long while the panda is still coming up, short between confirmations
      if [ -n "$last" ]; then sleep 1; else sleep 3; fi

      # Only the internal panda exists here: the aux USB-C port isn't switched to
      # host mode until after this runs (see set_aux_panda), so a plain connect is
      # unambiguous - there is exactly one panda to read.
      case "$(python -c "from panda import Panda; p = Panda(cli=False); print(p.get_mcu_type()); p.close()" 2>/dev/null)" in
        *McuType.F4*) cur="F4" ;;
        *McuType.H7*) cur="H7" ;;
        *)            cur="" ;;
      esac

      if [ -n "$cur" ] && [ "$cur" = "$last" ]; then
        count=$((count + 1))
      else
        count=1
        last="$cur"
      fi

      if [ -n "$cur" ] && [ "$count" -ge "$confirm" ]; then
        mcu="$cur"
        break
      fi
      echo "panda MCU read='${cur:-UNKNOWN}' (confirmed $count/$confirm, attempt $attempt/$attempts)"
    done

    if [ -z "$mcu" ]; then
      echo "TICI (UNKNOWN) detected after $attempts attempts, stop processing."
      exit 1
    fi

    # Persist it so future boots skip detection. /persist is comma's protected,
    # read-only partition, so flip it rw just for this one write (happens once per
    # device) and back to ro. The fast-path cat above reads fine on a ro mount, so
    # only the write needs this. Any failure here is non-fatal: re-detect next boot.
    if sudo mount -o remount,rw /persist 2>/dev/null; then
      echo "$mcu" | sudo tee "$cache" "$legacy_cache" >/dev/null 2>&1
      sudo mount -o remount,ro /persist 2>/dev/null
    fi
  fi

  # --- apply: DOS (F4) also mounts the NVMe; TRES (H7) does not ---
  if [ "$mcu" = "F4" ]; then
    echo "TICI (DOS) detected"
    mount_nvme
    export TICI_DOS=1
    set_aux_panda              # pandad supports a 2nd (aux) USB panda on C3 DOS
  else
    echo "TICI (TRES) detected"
    export TICI_TRES=1
  fi
}

# The aux USB-C port (a600000.ssusb) boots in OTG idle ("none"); a 2nd panda
# plugged there only enumerates once the port is switched to USB host mode. Only
# pandad supports a 2nd USB panda on C3 DOS (F4 internal); runs for F4 only, and only
# after set_tici_hw has fingerprinted the internal panda alone. Keep host mode
# only if a 2nd panda actually shows up; otherwise revert to "none" so the port
# stays usable as a USB device (PC connect) on units with no aux panda. Aux
# presence is dynamic (plug/unplug), so it is probed every boot, not cached.
set_aux_panda() {
  local mode="/sys/devices/platform/soc/a600000.ssusb/mode"
  [ -e "$mode" ] || return 0

  echo "Checking for aux panda (switching USB-C port to host mode)..."
  echo host | sudo tee "$mode" >/dev/null 2>&1
  for _ in $(seq 1 6); do          # ~3s budget; aux enumerated in ~1-2s in testing
    sleep 0.5
    if [ "$(lsusb 2>/dev/null | grep -c 'comma.ai panda')" -ge 2 ]; then
      echo "aux panda detected (USB host mode kept)"
      return 0
    fi
  done

  echo "no aux panda found; reverting USB-C port to device mode"
  echo none | sudo tee "$mode" >/dev/null 2>&1
}

mount_nvme() {
  for i in $(seq 1 10); do
    [ -b /dev/nvme0n1p1 ] && break
    sleep 1
  done

  # Returns 0 (success) so the boot process continues without errors
  if [ ! -b /dev/nvme0n1p1 ]; then
    return 0
  fi

  # We assume /data/media/0/realdata exists per defaults
  if ! mountpoint -q /data/media/0/realdata; then
    mount /dev/nvme0n1p1 /data/media/0/realdata
  fi

  if mountpoint -q /data/media/0/realdata; then
    OWNER="$(stat -c '%U' /data/media/0/realdata)"
    GROUP="$(stat -c '%G' /data/media/0/realdata)"
    PERM="$(stat -c '%a' /data/media/0/realdata)"

    if [ "$OWNER" != "comma" ] || [ "$GROUP" != "comma" ]; then
      chown comma:comma /data/media/0/realdata
    fi

    if [ "$PERM" != "755" ]; then
      chmod 755 /data/media/0/realdata
    fi
  fi
}

set_lite_hw() {
  [ "$(comma_device_slug)" = "tici" ] || return 0
  output=$(i2cget -y 0 0x10 0x00 2>/dev/null)

  if [ -z "$output" ]; then
    echo "Lite HW"
    export LITE=1
  fi
}

function launch {
  # Remove orphaned git lock if it exists on boot
  [ -f "$DIR/.git/index.lock" ] && rm -f $DIR/.git/index.lock

  # Check to see if there's a valid overlay-based update available. Conditions
  # are as follows:
  #
  # 1. The DIR init file has to exist, with a newer modtime than anything in
  #    the DIR Git repo. This checks for local development work or the user
  #    switching branches/forks, which should not be overwritten.
  # 2. The FINALIZED consistent file has to exist, indicating there's an update
  #    that completed successfully and synced to disk.

  if [ -f "${DIR}/.overlay_init" ]; then
    find ${DIR}/.git -newer ${DIR}/.overlay_init | grep -q '.' 2> /dev/null
    if [ $? -eq 0 ]; then
      echo "${DIR} has been modified, skipping overlay update installation"
    else
      if [ -f "${STAGING_ROOT}/finalized/.overlay_consistent" ]; then
        if [ ! -d /data/safe_staging/old_openpilot ]; then
          echo "Valid overlay update found, installing"
          LAUNCHER_LOCATION="${BASH_SOURCE[0]}"

          mv $DIR /data/safe_staging/old_openpilot
          mv "${STAGING_ROOT}/finalized" $DIR
          cd $DIR

          echo "Restarting launch script ${LAUNCHER_LOCATION}"
          unset AGNOS_VERSION
          exec "${LAUNCHER_LOCATION}"
        else
          echo "openpilot backup found, not updating"
          # TODO: restore backup? This means the updater didn't start after swapping
        fi
      fi
    fi
  fi

  # handle pythonpath
  ln -sfn $(pwd) /data/pythonpath
  export PYTHONPATH="$PWD"

  # submodule package symlinks for PYTHONPATH imports on device.
  # on PC these come from editable installs via pyproject.toml / uv.
  ln -sfn msgq_repo/msgq msgq
  ln -sfn opendbc_repo/opendbc opendbc
  ln -sfn rednose_repo/rednose rednose
  ln -sfn teleoprtc_repo/teleoprtc teleoprtc
  ln -sfn tinygrad_repo/tinygrad tinygrad

  # hardware specific init
  if [ -f /AGNOS ]; then
    set_tici_hw
    set_lite_hw
    agnos_init
  fi

  # write tmux scrollback to a file
  tmux capture-pane -pq -S-1000 > /tmp/launch_log

  sudo mkdir -p /cache/tsk
  sudo chown comma:comma /cache/tsk

  start_webui() {
    local root="$DIR"
    if [ ! -f "$root/webui/webuid.py" ]; then
      return 0
    fi
    local web_py=python3.12
    command -v "$web_py" >/dev/null 2>&1 || web_py=python3
    local venv_site="/usr/local/venv/lib/python3.12/site-packages"
    local pydeps="$root/.pydeps"
    local py_path="$root"
    [ -d "$venv_site" ] && py_path="$py_path:$venv_site"
    [ -d "$pydeps" ] && py_path="$py_path:$pydeps"
    # AGNOS rootfs is read-only; install aiohttp into $pydeps on first boot.
    if ! "$web_py" -c "import aiohttp" 2>/dev/null; then
      if [ -d "$pydeps" ] || mkdir -p "$pydeps" 2>/dev/null; then
        if ! "$web_py" -c "import pip" 2>/dev/null; then
          curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py 2>/dev/null && \
            "$web_py" /tmp/get-pip.py --target="$pydeps" --no-warn-script-location >> /tmp/webui.log 2>&1 || true
        fi
        PYTHONPATH="$py_path" "$web_py" -m pip install --target="$pydeps" aiohttp >> /tmp/webui.log 2>&1 || true
        py_path="$root"
        [ -d "$venv_site" ] && py_path="$py_path:$venv_site"
        py_path="$py_path:$pydeps"
      fi
    fi
    if pgrep -f "[p]ython.* -m webui\.webuid" >/dev/null 2>&1; then
      return 0
    fi
    echo "[webui] starting :5080 TLS ($(date))" >> /tmp/webui.log
    # Headless (no builtin panel): native ui is skipped; WebUI is the primary UI.
    # Override detection: OPENPILOT_HEADLESS=1 force headless, =0 force display mode.
    # Auto-detect requires panel backlight sysfs AND fts_ts touch IRQ (disassembled units may lack touch).
    # Headless first boot: USB tether (RNDIS) -> https://10.255.128.121:5080/ (accept TLS cert once).
    (cd "$root" && PYTHONPATH="$py_path" WEBUI_TLS=1 "$web_py" -m webui.webuid >> /tmp/webui.log 2>&1 &)
  }

  start_op_assistant() {
    local root="$DIR"
    if [ ! -f "$root/ai/aid.py" ]; then
      return 0
    fi
    local aid_py=python3.12
    command -v "$aid_py" >/dev/null 2>&1 || aid_py=python3
    local venv_site="/usr/local/venv/lib/python3.12/site-packages"
    local pydeps="$root/.pydeps"
    local py_path="$root"
    [ -d "$venv_site" ] && py_path="$py_path:$venv_site"
    [ -d "$pydeps" ] && py_path="$py_path:$pydeps"
    # Share aiohttp bootstrap with WebUI (.pydeps on read-only AGNOS rootfs).
    if ! PYTHONPATH="$py_path" "$aid_py" -c "import aiohttp" 2>/dev/null; then
      if [ -d "$pydeps" ] || mkdir -p "$pydeps" 2>/dev/null; then
        if ! "$aid_py" -c "import pip" 2>/dev/null; then
          curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py 2>/dev/null && \
            "$aid_py" /tmp/get-pip.py --target="$pydeps" --no-warn-script-location >> /tmp/aid.log 2>&1 || true
        fi
        PYTHONPATH="$py_path" "$aid_py" -m pip install --target="$pydeps" aiohttp >> /tmp/aid.log 2>&1 || true
        py_path="$root"
        [ -d "$venv_site" ] && py_path="$py_path:$venv_site"
        py_path="$py_path:$pydeps"
      fi
    fi
    if pgrep -f "[p]ython.* -m ai\.aid" >/dev/null 2>&1; then
      return 0
    fi
    echo "[aid] starting :5090 ($(date))" >> /tmp/aid.log
    (cd "$root" && PYTHONPATH="$py_path" "$aid_py" -m ai.aid >> /tmp/aid.log 2>&1 &)
  }

  # start manager
  cd openpilot/system/manager
  if [ ! -f $DIR/prebuilt ]; then
    ./build.py
  fi

  start_webui
  (
    while true; do
      sleep 45
      start_webui
    done
  ) &

  start_op_assistant
  (
    while true; do
      sleep 45
      start_op_assistant
    done
  ) &

  ./manager.py

  # if broken, keep on screen error
  while true; do sleep 1; done
}

launch

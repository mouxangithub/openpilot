#!/usr/bin/env bash

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

# models get lower priority than ui
# - ui is ~5ms
# - modeld is 20ms
# - DM is 10ms
# in order to run ui at 60fps (16.67ms), we need to allow
# it to preempt the model workloads. we have enough
# headroom for this until ui is moved to the CPU.
export QCOM_PRIORITY=12

if [ -z "$AGNOS_VERSION" ]; then
  export AGNOS_VERSION="20.3-carrot-bt3"
fi

# RTC-less clone devices boot at 1970; every TLS operation (pip mirror,
# athena, sunnylink, git) fails certificate validation until the clock is
# sane, and nothing else syncs time this early. HTTP needs no TLS, so pull
# the date from an HTTP response header. This is sourced before WiFi is up,
# so poll briefly for DNS first; bounded at ~30s and only when the clock is
# actually implausible.
if [ "$(date +%s)" -lt 1735689600 ]; then
  _sync_tries=0
  while [ "$_sync_tries" -lt 10 ]; do
    if ! python3 -c "import socket; socket.getaddrinfo('www.baidu.com', None)" >/dev/null 2>&1; then
      sleep 3
      _sync_tries=$((_sync_tries + 1))
      continue
    fi
    for _sync_url in http://www.baidu.com http://www.qq.com http://github.com; do
      _sync_date=$(curl -fsSI -m 10 "$_sync_url" 2>/dev/null | grep -i '^date:' | cut -d' ' -f2- | tr -d '\r')
      if [ -n "$_sync_date" ]; then
        sudo date -s "$_sync_date" >/dev/null 2>&1 && break 2
      fi
    done
    break
  done
  unset _sync_tries _sync_url _sync_date
fi

export STAGING_ROOT="/data/safe_staging"

# NOTE: do not disable the cabin camera by device model here. Clone C3 units
# report model "comma tici" but DO have a working OS04C10 cabin camera; the
# camerad bringup-failure path (sensor_missing) already keeps hardware without
# that camera healthy, so disabling by model string only breaks clones.

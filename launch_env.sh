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
  export AGNOS_VERSION="20.2-carrot-bt2"
fi

export STAGING_ROOT="/data/safe_staging"

# The comma 3 (tici) has no cabin camera, but camerad's camera config enables
# it by default. The missing sensor fails its bringup and the first-frame
# sync then waits for a frame that never arrives, so the UI never gets a
# camera stream. Disable the cabin camera on that hardware; tizi (comma 3X)
# does have one and keeps it enabled.
if [ -z "$DISABLE_DRIVER" ]; then
  case "$(tr -d '\0' < /sys/firmware/devicetree/base/model 2>/dev/null | awk '{print $NF}')" in
    tici) export DISABLE_DRIVER=1 ;;
  esac
fi

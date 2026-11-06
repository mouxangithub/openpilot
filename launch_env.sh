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
  export AGNOS_VERSION="20.3-carrot-bt2"
fi

export STAGING_ROOT="/data/safe_staging"

# NOTE: do not disable the cabin camera by device model here. Clone C3 units
# report model "comma tici" but DO have a working OS04C10 cabin camera; the
# camerad bringup-failure path (sensor_missing) already keeps hardware without
# that camera healthy, so disabling by model string only breaks clones.

# IMU Auto-Calibration

sunnypilot can automatically estimate the full 3-D rotation between the device IMU and the vehicle frame. This is useful when the comma device is mounted at a large or arbitrary angle (for example, horizontally on the dashboard) and the forward-facing camera is physically separated from the device.

When enabled, the stock `calibrationd` is replaced by `imu_calibrationd`, which computes a full 3×3 rotation matrix used by `locationd` instead of the small-angle `rpyCalib`.

## Enabling IMU auto-calibration

1. Open **Settings → IMU Calibration**.
2. Toggle **Use IMU Calibration** on.
3. The device will prompt for an onroad cycle; confirm if requested.

## Calibration procedure

The calibration runs in two phases while the car is onroad:

### 1. Static phase — keep the car parked

- Park on reasonably level ground.
- Keep the vehicle stationary for at least **1.5 seconds**.
- The daemon averages accelerometer and gyroscope readings to estimate gravity and gyro zero-rate bias.
- If the ground slope is steeper than **5°**, calibration fails with a slope error.

### 2. Dynamic phase — drive straight

- Drive straight at **≥ 5 m/s (18 km/h)** for at least **3 seconds**.
- Avoid hard steering, high lateral acceleration, or low-confidence camera odometry.
- The daemon compares integrated gyro rotation against camera-odometry rotation to solve the remaining yaw rotation around gravity.
- Brief interruptions (e.g., traffic lights) up to **2 seconds** are allowed without losing already-collected data.

## Calibration quality

The UI shows two quality indicators during and after calibration:

- **Yaw std** — standard deviation of the yaw estimate in degrees. Lower is better.
- **Inliers** — percentage of camera-odometry frames that passed the outlier rejection. Higher is better.

A calibration with very high yaw std or low inlier ratio may produce poor driving behavior. If calibration fails, repeat the procedure on flatter ground and with a longer straight-driving segment.

## Resetting calibration

1. Open **Settings → IMU Calibration**.
2. Tap **Reset IMU Calibration**.
3. Confirm the prompt.

Reset clears the saved rotation matrix and disables IMU auto-calibration, returning `locationd` to the stock small-angle calibration.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| "Calibration failed — vehicle not stationary enough" | Car moved during static phase | Re-park and keep the vehicle still |
| "Calibration failed — slope too steep" | Ground is tilted > 5° | Move to flatter ground |
| "Calibration failed — no straight road" | Not enough straight driving | Drive straight for at least 3 seconds at ≥ 5 m/s |
| "Calibration failed — too many dynamic outliers" | Camera odometry unreliable | Avoid sun glare, lane-less roads, or sharp maneuvers |
| "Calibration failed — dynamic calibration timed out" | No successful dynamic phase within 5 minutes | Repeat the full procedure |


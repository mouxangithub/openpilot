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
- A stationary accelerometer cannot tell "the device is mounted at an angle" from "the car is on a slope" — they are mathematically the same reading — so this is not a slope test. It only rejects a device orientation no reasonable mount would produce (more than **45°** off vertical, e.g. lying flat on its face). Park on reasonably level ground so the recovered pitch/roll is accurate.

### 2. Dynamic phase — drive straight

- Drive straight at **≥ 5 m/s (18 km/h)** for at least **3 seconds**.
- Avoid hard steering, high lateral acceleration, or low-confidence camera odometry.
- The daemon compares integrated gyro rotation against camera-odometry rotation to solve the remaining yaw rotation around gravity.
- Brief interruptions (e.g., traffic lights) up to **2 seconds** are allowed without losing already-collected data.

## Calibration quality

The UI shows two quality indicators during and after calibration:

- **Yaw std** — standard deviation of the yaw estimate in degrees. Lower is better.
- **Inliers** — percentage of camera-odometry frames that passed the outlier rejection. Higher is better.

The dynamic phase finishes only when the estimate is good enough: the run needs at least 3 seconds of straight driving **and** a yaw std of **10° or less**. Above that threshold the daemon keeps collecting straight-driving data instead of saving a poorly converged matrix; if the estimate never converges within 5 minutes, the calibration fails with a timeout. A calibration with very high yaw std or low inlier ratio would produce poor driving behavior, so it is never saved. If calibration fails, repeat the procedure on flatter ground and with a longer straight-driving segment.

## Resetting calibration

1. Open **Settings → IMU Calibration**.
2. Tap **Reset IMU Calibration**.
3. Confirm the prompt.

Reset clears the saved rotation matrix and disables IMU auto-calibration, returning `locationd` to the stock small-angle calibration.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| "Calibration failed — vehicle not stationary enough" | Car moved during static phase | Re-park and keep the vehicle still |
| "Calibration failed — device is not vertical" | Device orientation no mount would produce (> 45° off vertical) | Check the mounting |
| "Calibration failed — no straight road" | Not enough straight driving | Drive straight for at least 3 seconds at ≥ 5 m/s |
| "Calibration failed — too many dynamic outliers" | Camera odometry unreliable | Avoid sun glare, lane-less roads, or sharp maneuvers |
| "Calibration failed — yaw estimate too noisy" | The yaw estimate never converged below 10° | Drive a longer, straighter segment on a road with confident lane markings |
| "Calibration failed — static calibration timed out" | The car never came to rest within 5 minutes of starting | Park, then start the calibration |
| "Calibration failed — dynamic calibration timed out" | No converged dynamic phase within 5 minutes | Repeat the full procedure on a longer straight road |

## Re-calibrating

Press **Start calibration** again on the IMU Calibration page. A completed, failed or cancelled run can be restarted directly — you do not need to reset first. Re-calibrating after moving or re-aiming the device is allowed: the new mount may differ from the old one by a large angle. Use **Reset** only to remove the saved matrix and return to the stock calibration.


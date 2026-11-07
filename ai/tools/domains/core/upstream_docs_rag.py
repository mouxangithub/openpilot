"""Built-in RAG full-text seeds from upstream openpilot docs (comma.ai originals)."""

from __future__ import annotations

from typing import Any

# All ids use builtin_op_* prefix; refresh=True so text tracks upstream doc changes on restart.
UPSTREAM_DOCS_RAG: list[dict[str, Any]] = [
  {
    "id": "builtin_op_logs_full",
    "title": "openpilot 日志与录像格式（全文）",
    "tags": ["logs", "data", "can", "diagnosis"],
    "refresh": True,
    "text": """来源：openpilot 上游 docs（comma.ai 原版）docs/concepts/logs.md
适用范围：route/segment 日志与录像文件格式、读取工具的英文原文全文。

# Logging

openpilot records routes in one minute chunks called segments. A route starts on the rising
edge of ignition and ends on the falling edge.

Check out our Python library (openpilot/tools/lib/logreader.py) for reading openpilot logs.
Also checkout our tools (openpilot/tools) to replay and view your data. These are the same
tools we use to debug and develop openpilot.

For each segment, openpilot records the following log types:

## rlog.zst

rlogs contain all the messages passed amongst openpilot's processes. See
openpilot/cereal/services.py for a list of all the logged services. They're a zstd archive of
the serialized Cap'n Proto messages.

## camera video files

Each camera stream is H.265 encoded and written to its respective file.

* `fcamera.hevc` is the narrow road camera (the main forward camera)
* `ecamera.hevc` is the wide road camera
* `dcamera.hevc` is the cabin camera

## qlog.zst & qcamera.ts

qlogs are a decimated subset of the rlogs. Check out openpilot/cereal/services.py for the
decimation.

qcameras are H.264 encoded, lower res versions of the fcamera.hevc. The video shown in
comma connect (connect.comma.ai) is from the qcameras.

qlogs and qcameras are designed to be small enough to upload instantly on slow internet, yet
useful enough for most analysis and debugging.""",
  },
  {
    "id": "builtin_op_car_port_full",
    "title": "车型移植 Car Port 官方指南（全文）",
    "tags": ["vehicle", "car-port", "opendbc"],
    "refresh": True,
    "text": """来源：openpilot 上游 docs（comma.ai 原版）docs/how-to/car-port.md
适用范围：car port 目录结构与 brand/model port 区别的英文原文全文。

# What is a car port?

A car port enables openpilot support on a particular car. Each car model openpilot supports
needs to be individually ported. The complexity of a car port varies depending on many
factors including:

* existing openpilot support for similar cars
* architecture and APIs available in the car

# Structure of a car port

All car-specific code is contained in the opendbc project.

## opendbc

Each car brand is supported by a standard interface structure in `opendbc/car/[brand]`:

* `interface.py`: Interface for the car, defines the CarInterface class
* `carstate.py`: Reads CAN messages from the car and builds openpilot CarState messages
* `carcontroller.py`: Control logic for executing openpilot CarControl actions on the car
* `[brand]can.py`: Composes CAN messages for carcontroller to send
* `values.py`: Limits for actuation, general constants for cars, and supported car
  documentation
* `radar_interface.py`: Interface for parsing radar points from the car, if applicable

## safety

* `opendbc/safety/modes/[brand].h`: Brand-specific safety logic
* `opendbc/safety/tests/test_[brand].py`: Brand-specific safety CI tests

## openpilot

For historical reasons, openpilot still contains a small amount of car-specific logic. This
will eventually be migrated to opendbc or otherwise removed.

* `openpilot/selfdrive/car/car_specific.py`: Brand-specific event logic

# How do I port car?

Jason Young gave a talk at COMMA_CON with an overview of the car porting process. The talk
is available on YouTube: https://www.youtube.com/watch?v=XxPS5TpTUnI

## Brand Port

A brand port is a port of openpilot to a substantially new car brand or platform within a
brand. Example: github.com/commaai/openpilot/pull/23331.

## Model Port

A model port is a port of openpilot to a new car model within an already supported brand.
Model ports are easier than brand ports because the car's existing APIs are already known.
Example: github.com/commaai/openpilot/pull/30672.""",
  },
  {
    "id": "builtin_op_imu_calibration_full",
    "title": "IMU 自标定指南（全文）",
    "tags": ["tune", "imu", "calibration", "vehicle"],
    "refresh": True,
    "text": """来源：openpilot 上游 docs（comma.ai 原版）docs/how-to/imu-calibration.md
适用范围：IMU 自动标定的启用与排障流程英文原文全文。
注意：IMU 自标定为本项目（sunnypilot fork）实现，上游 openpilot 无此功能。

# IMU Auto-Calibration

sunnypilot can automatically estimate the full 3-D rotation between the device IMU and the
vehicle frame. This is useful when the comma device is mounted at a large or arbitrary angle
(for example, horizontally on the dashboard) and the forward-facing camera is physically
separated from the device.

When enabled, the stock `calibrationd` is replaced by `imu_calibrationd`, which computes a
full 3×3 rotation matrix used by `locationd` instead of the small-angle `rpyCalib`.

## Enabling IMU auto-calibration

1. Open **Settings → IMU Calibration**.
2. Toggle **Use IMU Calibration** on.
3. The device will prompt for an onroad cycle; confirm if requested.

## Calibration procedure

The calibration runs in two phases while the car is onroad:

### 1. Static phase — keep the car parked

- Park on reasonably level ground.
- Keep the vehicle stationary for at least **1.5 seconds**.
- The daemon averages accelerometer and gyroscope readings to estimate gravity and gyro
  zero-rate bias.
- If the ground slope is steeper than **5°**, calibration fails with a slope error.

### 2. Dynamic phase — drive straight

- Drive straight at **≥ 5 m/s (18 km/h)** for at least **3 seconds**.
- Avoid hard steering, high lateral acceleration, or low-confidence camera odometry.
- The daemon compares integrated gyro rotation against camera-odometry rotation to solve the
  remaining yaw rotation around gravity.
- Brief interruptions (e.g., traffic lights) up to **2 seconds** are allowed without losing
  already-collected data.

## Calibration quality

The UI shows two quality indicators during and after calibration:

- **Yaw std** — standard deviation of the yaw estimate in degrees. Lower is better.
- **Inliers** — percentage of camera-odometry frames that passed the outlier rejection.
  Higher is better.

A calibration with very high yaw std or low inlier ratio may produce poor driving behavior.
If calibration fails, repeat the procedure on flatter ground and with a longer
straight-driving segment.

## Resetting calibration

1. Open **Settings → IMU Calibration**.
2. Tap **Reset IMU Calibration**.
3. Confirm the prompt.

Reset clears the saved rotation matrix and disables IMU auto-calibration, returning
`locationd` to the stock small-angle calibration.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| "Calibration failed — vehicle not stationary enough" | Car moved during static phase | Re-park and keep the vehicle still |
| "Calibration failed — slope too steep" | Ground is tilted > 5° | Move to flatter ground |
| "Calibration failed — no straight road" | Not enough straight driving | Drive straight for at least 3 seconds at ≥ 5 m/s |
| "Calibration failed — too many dynamic outliers" | Camera odometry unreliable | Avoid sun glare, lane-less roads, or sharp maneuvers |
| "Calibration failed — dynamic calibration timed out" | No successful dynamic phase within 5 minutes | Repeat the full procedure |""",
  },
  {
    "id": "builtin_op_integration_full",
    "title": "与原厂功能集成（全文）",
    "tags": ["integration", "concept", "faq"],
    "refresh": True,
    "text": """来源：openpilot 上游 docs（comma.ai 原版）docs/INTEGRATION.md
适用范围：openpilot 与车辆原厂 ADAS 功能替换/保留关系的英文原文全文。

# Integration with Stock Features

In all supported cars:
* Stock Lane Keep Assist (LKA) and stock ALC are replaced by openpilot ALC, which only
  functions when openpilot is engaged by the user.
* Stock LDW is replaced by openpilot LDW.

Additionally, on specific supported cars (see ACC column in supported cars CARS.md):
* Stock ACC is replaced by openpilot ACC.
* openpilot FCW operates in addition to stock FCW.

openpilot should preserve all other vehicle's stock features, including, but not limited to:
FCW, Automatic Emergency Braking (AEB), auto high-beam, blind spot warning, and side
collision warning.""",
  },
  {
    "id": "builtin_op_connect_comma_full",
    "title": "连接 comma 设备（全文）",
    "tags": ["devops", "connect", "ssh", "adb", "official"],
    "refresh": True,
    "text": """来源：openpilot 上游 docs（comma.ai 原版）docs/how-to/connect-to-comma.md
适用范围：comma 3X / comma four 设备串口、SSH、ADB 与 ssh.comma.ai 代理接入方法的英文原文全文。

# connect to a comma 3X or comma four

A comma device is a normal Linux (AGNOS) computer that exposes SSH and a serial console.

## Serial Console

On the comma 3X, the serial console is accessible from the main OBD-C port, forwarded
through the panda. Access it using `panda/scripts/som_debug.sh`.

comma four also exposes a serial console, albeit through an internal debug connector.
Dedicated debug hardware coming soon to the comma shop.

Login to the default user with:

  * Username: `comma`
  * Password: `comma`

## SSH

In order to SSH into your device, you'll need a GitHub account with SSH keys. See the
GitHub article "Connecting to GitHub with SSH" for getting your account setup with SSH keys.

* Enable SSH in your device's settings
* Enter your GitHub username in the device's settings
* Connect to your device
    * Username: `comma`
    * Port: `22`

Example command for connecting to your device using its tethered connection:
`ssh comma@192.168.43.1 -i ~/.ssh/my_github_key`

For doing development work on device, it's recommended to use SSH agent forwarding.

## ADB

In order to use ADB on your device, you'll need to perform the following steps:

* Plug your device into constant power using port 2, letting the device boot up
* Enable ADB in your device's settings
* Plug in your device to your PC using port 1
* Connect to your device
    * `adb shell` over USB
    * `adb connect` over WiFi
    * Example command for connecting to your device using its tethered connection:
      `adb connect 192.168.43.1:5555`

> The default port for ADB is 5555.

For more info on ADB, see the Android Debug Bridge (ADB) documentation.

### Notes

The public keys are only fetched from your GitHub account once. In order to update your
device's authorized keys, you'll need to re-enter your GitHub username.

The `id_rsa` key in this directory only works while your device is in the setup state with
no software installed. After installation, that default key will be removed.

## ssh.comma.ai proxy

With a comma prime subscription, you can SSH into your comma device from anywhere.

With the below SSH configuration, you can type `ssh comma-{dongleid}` to connect to your
device through `ssh.comma.ai`.

```
Host comma-*
  Port 22
  User comma
  IdentityFile ~/.ssh/my_github_key
  ProxyCommand ssh %h@ssh.comma.ai -W %h:%p

Host ssh.comma.ai
  Hostname ssh.comma.ai
  Port 22
  IdentityFile ~/.ssh/my_github_key
```

### One-off connection

```
ssh -i ~/.ssh/my_github_key -o ProxyCommand="ssh -i ~/.ssh/my_github_key -W %h:%p -p %p %h@ssh.comma.ai" comma@ffffffffffffffff
```

(Replace `ffffffffffffffff` with your dongle_id)

### ssh.comma.ai host key fingerprint

```
Host key fingerprint is SHA256:X22GOmfjGb9J04IA2+egtdaJ7vW9Fbtmpz9/x8/W1X4
```""",
  },
  {
    "id": "builtin_op_debugging_safety_full",
    "title": "安全代码调试指南（全文）",
    "tags": ["devops", "debugging", "safety", "official"],
    "refresh": True,
    "text": """来源：openpilot 上游 docs（comma.ai 原版）docs/DEBUGGING_SAFETY.md
适用范围：用回放驾驶 + LLDB 调试 panda 安全代码（VS Code 工作流）的英文原文全文。

# Debugging Panda Safety with Replay Drive + LLDB

## 1. Start the debugger in VS Code

* Select **Replay drive + Safety LLDB**.
* Enter the route or segment when prompted.

## 2. Attach LLDB

* When prompted, pick the running **`replay_drive` process**.
* ⚠️ Attach quickly, or `replay_drive` will start consuming messages.

> TIP: Add a Python breakpoint at the start of `replay_drive.py` to pause execution and
> give yourself time to attach LLDB.

## 3. Set breakpoints in VS Code

Breakpoints can be set directly in `modes/xxx.h` (or any C file).
No extra LLDB commands are required — just place breakpoints in the editor.

## 4. Resume execution

Once attached, you can step through both Python (on the replay) and C safety code as CAN
logs are replayed.

> NOTE:
> * Use short routes for quicker iteration.
> * Pause `replay_drive` early to avoid wasting log messages.

## Video

View a demo of this workflow on the PR that added it:
https://github.com/commaai/openpilot/pull/36055#issue-3352911578""",
  },
]

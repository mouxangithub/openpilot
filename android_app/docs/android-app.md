# Jetlink for Android

**Experimental, and not yet run on a phone.** Runs the Jetlink server in an
Android app, on the phone's Snapdragon NPU, connected to the comma by USB. You
build it from source. Run the [Benchmark](#benchmark) before you drive to see
if your phone keeps up.

Mac: [Jetlink for Mac](macos-app.md). iPhone: [Jetlink for iPhone and iPad](iphone-app.md).
Jetson or PC: [README](../README.md#quick-start).

## Requirements

- An Android 12 or later phone with a Snapdragon 8 Gen 2 or newer. See
  [Which phones](#which-phones).
- USB 3 on the phone, a USB 3 hub or adapter, and a USB 3 cable. See
  [Connect the comma](#connect-the-comma).
- About 3 GB free per model.
- A Mac or Linux PC to build the app: see [Android development](../android/README.md).
- A comma running a zoompilot build with Jetlink, set up per the
  [README](../README.md#comma-setup-all-platforms), with **Accelerator Link**
  on **USB**.

### Which phones

The model runs on the phone's NPU, the Hexagon in a Snapdragon, through
Qualcomm's QNN runtime. Other phones run it on the CPU, far too slowly.

| Snapdragon | NPU | Expect |
| --- | --- | --- |
| 8 Elite Gen 5, 8 Elite, 8 Gen 3 | v81, v79, v75 | Fast enough (estimated) |
| 8 Gen 2, 8s Gen 3 | v73 | Maybe |
| 8+ Gen 1, 8 Gen 1 | v69 | Probably too slow |
| 888 and older, 7-series | v68 and older | No fp16 on the NPU |

Settings > About shows your phone's chip. The estimates are from Qualcomm's
published numbers for similar models; no phone has been measured.

## Install

1. Build the APK: [Android development](../android/README.md#build).
2. On the phone, turn on **Developer options** (tap **Build number** seven
   times) and **USB debugging**, then `adb install` it. Or copy the APK to the
   phone and allow your file manager to install unknown apps.
3. Open Jetlink. Allow notifications: the notification is how Jetlink keeps
   running with the screen off.

There is no Play Store build.

## Connect the comma

1. On the comma, while offroad, set **Accelerator Link** to **USB** in the
   models settings, as for a Jetson or Mac.
2. Connect the phone to a USB 3 hub with USB-C power pass-through, and the hub
   to the comma with a USB-A to USB-C cable. Plug a charger into the hub so the
   phone charges while it runs the model.
3. Android asks whether to open Jetlink for the device. Tap **OK** and tick
   **Always open**; otherwise it asks again whenever the comma reconnects.
4. The title reads **Connected over USB 3**. **USB 2** (orange) means the
   phone, hub or cable is not USB 3.

- A USB-C to USB-A adapter instead of the hub works, but the phone then powers
  the link and does not charge.
- A direct USB-C to USB-C cable is untried.
- On OnePlus, OPPO and realme phones, turn on **OTG connection** in Settings
  first. It turns itself off after a while unused.
- The app has these steps under Settings > **Help > Connecting the Comma**.

How the link works: [what the comma presents](transport.md#what-the-comma-presents).

## Prepare a model before you drive

Open **Models** and tap **Get** on your comma's model. It downloads, prepares
and loads in one step. The first preparation for the NPU takes minutes.

- The download needs Wi-Fi or mobile data.
- If you skip this, the comma sends its model on connect and drives on its small
  model until the phone has it ready.
- **Add Model File** imports an `.onnx` from the phone's storage.

## Benchmark

Run it before the first drive, and after a new model or a **Processor** change.

1. Load a model and leave the comma disconnected.
2. Set the phone up as in the car (charging, in its mount).
3. Open **Benchmark** and tap **1 Minute**.

It runs the model 20 times a second on made-up frames and times the phone's
share of each frame (not the cable).

- **Verdict:** **Fast Enough** (green) is a P99 at or under 35 ms with nothing
  over 50. **Tight** (orange) is a P99 under 50 ms. **Too Slow** (red) misses
  20 frames a second.
- **Totals:** frames, frames over 50 ms (and over 35), the phone's temperature
  at start and end, and the model alone.
- **Over Time:** P99 and temperature per 10 seconds. A phone that slows as it
  heats shows here.
- **10 Minutes** heats the phone: compare the first and last windows.
- The share button sends the report.

The app fills in two commands to copy, as the iPhone app does: the comma's live
bench (`jetlink_repo/scripts/comma/jetlink_live_bench.sh 180` over SSH, offroad,
with the phone connected), and `scripts/verify_parity.py` from a Mac on the same
Wi-Fi, which should end with OK.

## Status

Mount the phone where you can see it. The screen stays on while Jetlink is open,
and Jetlink keeps serving with the screen off or another app in front.

| Tile | Shows |
| --- | --- |
| **Headroom** | Room left in the 50 ms frame budget at P99 over the last 10 seconds. Green **Good**, orange **Tight** (under 10 ms left), red **Over Budget**. The comma's time and the cable come out of the same 50 ms. |
| **Latency** | The average frame: Input, Model, Other and Send. |
| **History** | The slowest frames of every 5 seconds, over the last 2 minutes. |
| **Link** | Frame rate (the comma sends 20 a second), slow frames, and USB 3 or USB 2. |
| **Phone** | Temperature, battery, memory and link. A hot phone slows down, and it shows here first. |

## Logs

**Settings > Help > Logs**. Warnings are orange and errors red. The share
button sends the log as a file; **Clear** empties the view. Over USB debugging,
`adb logcat -s jetlink` shows the same lines.

## Heat

A hot phone slows down and frames miss 50 ms.

- Keep the phone out of the sun and out of a thick case.
- The 10-minute benchmark shows how your phone and mount fare.
- **Keep NPU Awake** off trades a little speed for less heat.

## Limits

- **Jetlink runs in the background** while its notification shows. **Stop** in
  the notification stops the server. Android may still close it if the phone
  runs out of memory; the comma then drives on its small model.
- **Battery optimization.** If Jetlink stops on its own, set its battery use to
  **Unrestricted** in the app's settings.
- **Heat.** See [Heat](#heat).
- **The comma cannot power the phone off.** The app says the comma asked.
- **One comma at a time.** A new connection replaces the current one.

## Settings

| Setting | What it does |
| --- | --- |
| Link | USB 3 or USB 2 while connected (Wi-Fi for a bench tool) |
| Port | The TCP port for `verify_parity.py` from a Mac, 5599 by default |
| Wi-Fi | The phone's Wi-Fi address and port, for a Mac's bench tools |
| Processor | **NPU + GPU** (default): the vision model on the NPU, the rest on the GPU, as a Mac splits it. **NPU**: the whole model on the NPU. **GPU**: when something else keeps the NPU busy. **CPU**: for the emulator. Changing it prepares the model again |
| Keep NPU Awake | On by default. Holds the NPU at full speed between frames. Uses some power |
| Keep CPU Awake | With the NPU: holds the CPU's clocks up between frames, through Android's performance hints, or a busy core on a phone without them. Uses some power |
| Keep Screen On | On by default |
| Help | How to connect the comma, and the logs |
| Server | **Restart Server** starts it again with the same settings; **Stop Server** stops serving until **Start Server** |

# Jetlink for iPhone and iPad

**Experimental.** The model has run on an iPhone; the link to the comma has
only been tested with a Mac standing in for the phone. Runs the Jetlink server
in an iOS app, connected to the comma by one USB cable. You build it from
source. Run the [Benchmark](#benchmark) before you drive to see if your phone
keeps up.

On an iPad with USB-C, read iPad wherever this page says iPhone or phone.

Mac: [Jetlink for Mac](macos-app.md). Jetson or PC: [README](../README.md#quick-start).

## Requirements

- An iPhone with USB-C on iOS 26.1 or later, or an iPad with USB-C on iPadOS
  26.1 or later. iPads with Lightning are not supported.
- Ideally a USB 3 model: see [USB 3 matters](#usb-3-matters).
- A USB 3 USB-C cable, or a USB-A to USB-C cable with a USB-C adapter.
- A powered USB-C hub between them keeps the phone charging (it runs the model
  20 times a second).
- About 3 GB free per model.
- A Mac with Xcode 26 and the iOS 26 platform. There is no App Store or
  TestFlight build. A free Apple account is enough.
- A comma running a zoompilot build with Jetlink, set up per the
  [README](../README.md#comma-setup-all-platforms), with **Accelerator Link**
  on **iOS**.

## Install

1. In Xcode, open **Settings > Components** and install the **iOS 26**
   platform if it is missing.
2. Under **Settings > Accounts**, add your Apple ID. A free account shows as a
   **Personal Team**, with the ten-character team ID beside it.
3. In a checkout, copy `ios/Config/Local.xcconfig.example` to
   `ios/Config/Local.xcconfig` and set your team ID and your own bundle
   identifier. Git ignores the file. Do not set them under Signing &
   Capabilities (that writes them into the project file).
4. On the iPhone, turn on **Settings > Privacy & Security > Developer Mode** and
   restart. The switch appears once the phone has been plugged into a Mac with
   Xcode open.
5. Install xcodegen (`brew install xcodegen`) and run `make -C ios open`.
   Connect the iPhone, select it as the run destination and click **Run**. The
   first build fetches onnxruntime.
6. Trust the developer before the first launch: on the iPhone,
   **Settings > General > VPN & Device Management**, your Apple ID, **Trust**.

A free account's install stops opening after **7 days**. Click **Run** again to
renew it; models and settings are kept. A paid membership's install lasts a year.

Building and testing without a phone: [iPhone development](../ios/README.md).

## Connect the comma

1. On the comma, while offroad, set **Accelerator Link** to **iOS** in the
   models settings. **USB** is for a Jetson, Linux PC or Mac.
2. Open Jetlink. The first time, allow **Local Network** access.
3. Connect the phone to the comma with a USB 3 USB-C cable, or a USB-A to USB-C
   cable with a USB-C adapter. A powered USB-C hub between them keeps it charging.
4. The title reads **Connected over USB 3**. **USB 2** (orange title, and on the
   Link tile) means the phone, hub or cable is not USB 3. See
   [USB 3 matters](#usb-3-matters).

- There is nothing to type: the app finds the comma itself.
- Open the app before plugging in. Opened later, it still connects, just later.
- A direct cable to a phone is untried. If the comma restarts when you plug in,
  use a powered USB-C hub.
- The app has these steps under Settings > **Help > Connecting the Comma**.

How the link works: [what the comma presents](transport.md#what-the-comma-presents).

### USB 3 matters

Every hop must be USB 3: the phone, the cable and any hub.

| USB 3 | USB 2 |
| --- | --- |
| iPhone 15 Pro and later Pro models | Other USB-C iPhones, and the cable in the iPhone box |
| iPad Pro, iPad Air and iPad mini with USB-C | iPad (10th generation), iPad (A16) |

Sources: [Apple, iPhone](https://support.apple.com/en-us/105099),
[Identify your iPad model](https://support.apple.com/en-us/108043).

- USB 2 adds an estimated 4 to 6 ms a frame (not yet measured).
- To check the speed on the comma, run `sudo scripts/comma/jetlink-root.sh check`:
  `super-speed` is USB 3, `high-speed` is USB 2.

## Prepare a model before you drive

Open **Models** and tap **Get** on your comma's model. It downloads, prepares
and loads in one step.

- The download needs Wi-Fi or cellular data.
- Keep Jetlink open until it finishes: iOS suspends background downloads.
- If you skip this, the comma sends its model on connect and drives on its small
  model until the phone has it ready.
- You can also copy a model file in from the Finder or Files app, or use **Add
  Model File**.

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
- The share button copies the report or puts it in a note.

The app fills in two commands to copy:

- **From the comma:** `jetlink_repo/scripts/comma/jetlink_live_bench.sh 180`
  over SSH, offroad, with **Accelerator Link** on **iOS** and the phone
  connected. It reports the frame times the car will see. Frames over 50 ms
  should be 0.
- **From a Mac:** `scripts/verify_parity.py ...` on the same Wi-Fi. It checks
  the phone computes what onnxruntime does on a computer, and should end with OK.

## Status

Mount the phone where you can see it, in either orientation. The screen stays on
while Jetlink is open. The subtitle shows the state: **Connected over USB 3** (or
**USB 2**, or **Wi-Fi**), **Waiting for Comma**, **Preparing Model**,
**Disconnected**, or what is wrong.

| Tile | Shows |
| --- | --- |
| **Headroom** | Room left in the 50 ms frame budget at P99 over the last 10 seconds. Green **Good**, orange **Tight** (under 10 ms left), red **Over Budget**. The comma's time and the cable come out of the same 50 ms. |
| **Latency** | The average frame: Input, Model, Other and Send. |
| **History** | The slowest frames of every 5 seconds, over the last 2 minutes. |
| **Link** | Frame rate (the comma sends 20 a second), slow frames, and USB 3, USB 2, or Wi-Fi for a bench tool. |
| **iPhone** (**iPad**) | Temperature, battery, memory and link. A hot phone slows down, and it shows here first. Memory turns orange under 1 GB, where preparing a model may not fit. |

- An orange banner means the app left the screen while serving: iOS suspends it.
- On other tabs, tap the bar at the bottom to return.

## Logs

**Settings > Help > Logs**, or the document button on Status. Warnings are orange
and errors red. The share button sends the whole text; **Clear** empties the view.

## Heat

A hot phone slows down and frames miss 50 ms.

- Keep the phone out of the sun and out of a thick case.
- The 10-minute benchmark shows how your phone and mount fare.
- On the road, the Temperature tile and the logs show throttling.

## Limits

- **Keep Jetlink on screen.** iOS suspends it in the background or when the
  phone locks. The comma then drives on its small model and, if engaged, asks
  you to take over. Do not use other apps on the phone while driving.
- **Heat.** See [Heat](#heat).
- **The comma cannot power the phone off.** The app refuses and tells you the
  comma asked.
- **One comma at a time.** A new connection replaces the current one.
- **A free account's install expires after 7 days.** Run it again from Xcode.

## Settings

| Setting | What it does |
| --- | --- |
| Link | USB 3 or USB 2 while connected (Wi-Fi for a bench tool), Connecting while it dials the comma |
| Port | The TCP port for `verify_parity.py` from a Mac, 5599 by default |
| Wi-Fi | The phone's Wi-Fi address and port, for a Mac's bench tools |
| Processor | **Neural Engine + GPU** (default): the vision layers on the Neural Engine, the rest on the GPU, as a Mac runs it (14 ms a frame on an iPhone 18 Pro). **GPU**: when another app keeps the Neural Engine busy. **CPU**: the Simulator only. Changing it prepares the model again |
| Keep CPU Awake | On by default. Keeps a CPU core busy between frames so the next frame starts sooner. Uses some power |
| Keep GPU Awake | Keeps the GPU from slowing down between frames. Uses some power |
| Keep Screen On | On by default. Off, auto-lock suspends Jetlink |
| Help | How to connect the comma, and the logs |

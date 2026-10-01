# Jetlink for Android development

To install and use the app, follow the [Android user guide](../docs/android-app.md).
This page covers building and testing it from source. Run the commands from the
repository root.

## Layout

The app is a Kotlin shell over the same Swift server every platform runs.
`JetlinkKit` builds for Android with the Swift SDK for Android, into one
native library, `libjetlink.so`:

| Part | What it is |
| --- | --- |
| `JetlinkKit` | The server, the model registry and the ONNX preparation, shared with every platform |
| `JetlinkORT/OrtBackend.swift` | onnxruntime's profiles; `htp`, `htp-whole` and `gpu` use its QNN provider on a Snapdragon's NPU and GPU |
| `JetlinkServer/UsbfsPipes.swift`, `CUsbfs` | The comma's bulk pair through usbdevfs, on the descriptor the app opened |
| `JetlinkKit/AppSnapshot.swift` | The app's state as the screens draw it, from the server's events |
| `JetlinkAndroid` | The JNI functions `io.zoompilot.jetlink.server.Native` calls |
| `android/app` | Kotlin and Compose: the screens, the foreground service, USB permission, the phone's health |

Kotlin holds no server logic. It sends control commands in the control
protocol's JSON ([control-protocol.md](../docs/control-protocol.md)) and draws the
snapshot the server hands back, whose Models rows come from the same
`ModelRowBuilder` as the other apps. `JetlinkKit/Tests/JetlinkKitTests/Fixtures/android_snapshot.json`
pins that JSON: the Swift tests write and check it, and the app's unit tests
parse it.

## Setup

- JDK 17 or newer, and the Android SDK with platform 37 and NDK 30.0.16248370
  (Android Studio installs them; `sdkmanager "platforms;android-37.0"
  "ndk;30.0.16248370"` does too).
- The open-source Swift 6.4.0 toolchain and the Swift SDK for Android of the
  same version. Xcode's Swift cannot use the SDK.

```
swiftly install 6.4.0
swift sdk install https://download.swift.org/swift-6.4.0-release/android-sdk/swift-6.4.0-RELEASE/swift-6.4.0-RELEASE_android.artifactbundle.tar.gz \
  --checksum 21fb555122a3d801ad943d48df7ebffdd8824de61c25c180bb792d3edaee0b43
```

Without swiftly, the toolchain's installer package from swift.org installs for
your user with `installer -pkg swift-6.4.0-RELEASE-osx.pkg -target CurrentUserHomeDirectory`.
`android/scripts/swift-build.sh` finds either, links the SDK to the NDK on its
first run, and says what is missing.

## Build

```
cd android
./gradlew :app:assembleRelease
adb install -r app/build/outputs/apk/release/app-release.apk
```

The `swiftBuild` task runs `scripts/swift-build.sh`, which cross-compiles
`JetlinkKit`'s `jetlink` library with the Swift runtime linked in, always
optimized. `-Pjetlink.prebuiltSwift=DIR` packages `DIR/arm64-v8a/libjetlink.so`
instead, for work on the Kotlin side without the Swift toolchain. The APK is
arm64 only, as the QNN runtime is.

Release builds are signed with the debug key so they install over debug ones;
the app is sideloaded, never published.

`python3 android/scripts/make-icon.py` makes the launcher and notification icons
from the iPhone app's, with Pillow. The outputs are committed.

## Test

```
cd JetlinkKit && swift test          # the server, on the Mac
cd android && ./gradlew :app:testDebugUnitTest
```

The Swift suites cover the server as on the other platforms, plus the usbfs
pipes against a fake kernel and the snapshot's JSON. The Kotlin tests parse the
snapshot fixture and check the gadget's IDs, the port and the onnxruntime
release against `Pinned.swift`.

The same Swift suites run on Android itself, on a device or the emulator, with
their fixtures pushed beside them:

```
android/scripts/swift-test-device.sh path/to/onnxruntime-android-qnn-1.29.0.aar
```

On the emulator they pass, the whole server included, on onnxruntime's CPU
provider. Its Android build runs an fp16 graph's MatMul in fp16, so the fp16
golden model lands within a few percent of the golden frames rather than bit
for bit, and is held to `verify_parity`'s correlation there instead.

## The emulator

An Android emulator on an Apple silicon Mac runs arm64, so the APK runs there on
the CPU (Settings > Processor > CPU). It has no USB host, so a bench tool on the
Mac stands in for the comma over TCP:

```
adb forward tcp:5599 tcp:5599
python3 scripts/bench_link.py --host 127.0.0.1 --onnx big_driving_supercombo.onnx --rate 20
```

`adb logcat -s jetlink` shows the server's log. Launch extras open a tab or run
a benchmark, as the iPhone app's launch arguments do:

```
adb shell am start -n io.zoompilot.jetlink.android/io.zoompilot.jetlink.MainActivity -e tab models
adb shell am start -n io.zoompilot.jetlink.android/io.zoompilot.jetlink.MainActivity --ei benchmark 60
```

## On a phone

Nothing of this has run on a phone yet. What to check first, in order:

1. The gadget enumerates, Android asks to open Jetlink, and `adb logcat -s
   jetlink` shows the server's `comma attached` with the endpoints and a hello.
2. A model prepares on **NPU + GPU**: the log names the sessions it built
   (`QNN(htp) then QNN(gpu)`) and how long the NPU compile took.
3. Benchmark 1 Minute, then 10 Minutes while charging in the car mount.
4. The comma's live bench (`jetlink_repo/scripts/comma/jetlink_live_bench.sh 180`)
   and `scripts/verify_parity.py` from a Mac on the same Wi-Fi.

## Licenses

The APK carries onnxruntime (MIT) and Qualcomm's QNN runtime libraries from
Maven (`com.qualcomm.qti:qnn-runtime`, which `onnxruntime-android-qnn`
depends on), under Qualcomm's AI Stack License: redistributable only inside an
app, not on their own. That license also advises against what it calls
high-risk applications, those making consequential decisions; read it before
you share a build.

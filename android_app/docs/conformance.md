# Keeping the server in step with the comma

The comma runs this repo's Python (`jetlink/`); every server is the Swift one
(`JetlinkKit`): the Jetson, a Linux PC, the Mac, iPhone and Android apps. The
comma must work with it unchanged, so what crosses between them is held to the
Python:

- **Comma-facing contracts are Python-sourced.** Constants, wire bytes, queue
  staging and the registry's pointers and catalog are generated from the
  Python, committed, and read by the Swift tests. The Python tests check the
  Python still writes exactly those files.
- **The server's own behaviour is Swift-owned.** Goldens the Python server
  wrote before it was deleted are frozen; nothing regenerates them.
- **A live test runs the comma's client against the Swift server.**

## Python-sourced

| What | Written by | Read by the Swift in |
| --- | --- | --- |
| Constants: the wire's magic, version, sizes, message, flag and status numbers; USB ids and packet sizes; USB speeds; model constants; the product version; the onnxruntime release | `make_pins.py` writes `JetlinkKit/Sources/JetlinkKit/Pinned.swift` | the Swift code uses `Pinned`; `ConformanceTests` checks every Swift constant against it |
| Wire bytes: headers and INFER bodies; the byte streams of TCP, a USB host and the gadget's 16 KB bursts | `make_conformance_fixtures.py wire` | `JetlinkServerTests/ConformanceTests.swift` |
| Tensors the queues stage each frame at frame_skip 1, 2 and 4, each frame's hidden state fed into the next, with a reset, a hello, a non-finite frame and desires with NaNs, signed zeros and infinities | `make_conformance_fixtures.py staging` | the same file |
| Where the reply leaves hidden_state out, for slices with open ends, ends counted from the back or past the end, and whether a queued graph's queues can feed it back | `make_conformance_fixtures.py layout` | the same file |
| LFS pointers, model identities, catalog parsing and merging | `make_conformance_fixtures.py registry` | `JetlinkRegistryTests/ConformanceTests.swift` |

Generators live in `JetlinkKit/Scripts` and import the `jetlink` package of
their own checkout, whatever the environment has installed.

## Swift-owned

| What | Where | Changed by |
| --- | --- | --- |
| The `stats` event from fixed samples | `JetlinkServerTests/Fixtures/conformance/stats.json` | editing the file |
| One cache directory's catalog and inventory payloads | the `cache` block of `tests/fixtures/conformance/registry.json` | editing the file; the generator copies the block through |
| Whole-server runs: driving output of the tiny queued and stateful graphs | `JetlinkServerTests/Fixtures/tiny_*` | editing the files |
| ONNX preparation for every layout, byte for byte | `JetlinkONNXTests/Fixtures/*.expected.onnx` | editing the files |
| The Android app's snapshot | `JetlinkKitTests/Fixtures/android_snapshot.json` | `JETLINK_WRITE_FIXTURES=1` on its test |

A change to one of these is a change to what the server does: say why in the
commit. A bump of `OrtBackend.prepareVersion` rebuilds every cached onnxruntime artifact
on its next load.

## The live test

`tests/test_swift_server.py` serves `tests/tiny_model.py`'s graphs from a real
`jetlink-server` (`--backend ort --device cpu --listen`) and drives it through
`jetlink.client`, as a comma does: upload and build, inference, the hidden
state, resets, NOT_FINITE, telemetry, NOT_READY, deadlines, a shutdown request
without `--poweroff` (answered, and the server stays up) and the stateful
graph. The binary comes from `JETLINK_SERVER_BIN`, else
the newest build in `JetlinkKit/.build`; `JETLINK_SERVER_BUILD=1` builds it
first. Without one it skips.

## How it runs

- `tests/test_conformance.py` reruns each generator into a temporary directory
  and compares byte for byte with the committed files. It also checks that
  `Pinned.swift` is current and that the Swift package links the pinned
  onnxruntime.
- The staging spec comes from a graph onnx shape-infers, so the staging files
  are compared only under the onnx in `JetlinkKit/Scripts/fixture-pins.txt`.
  CI's Python 3.12 job installs with those releases (`pip install -c`), so
  nothing skips there.
- `swift test --package-path JetlinkKit` reads the fixtures on macOS and Linux
  (arm64 and x86_64), and on Android through `JETLINK_TEST_ROOT`
  (`android/scripts/swift-test-device.sh`).
- The live test runs in CI against the macOS build and both Linux builds.
- Published numbers round as Python's `round()` does (half to even on the
  exact binary value), through `pythonRound` in JetlinkKit.

## Linux and Android

The whole package builds on Linux. onnxruntime is opened at run time from the
official `onnxruntime-linux-*` tarball of the release `Pinned` names: the build
needs its headers, and the tests that run a model need its library.

- The golden frames of an fp16 graph are held to a 0.999 correlation rather than
  bit for bit: onnxruntime's Linux and Android builds compute fp16 MatMul and
  ReduceMean in fp16, where the Apple build does not. The fp32 stateful graph
  still matches bit for bit.
- The registry's network tests run on Linux too: each mock network has its own
  URLProtocol class, and `LocalServer` serves over Glibc sockets.
- Stand-ins: swift-crypto for CryptoKit; `JetlinkLog` takes `os.Logger`'s
  calls; element loops instead of vImage; the capped HTTP read fetches the
  whole body and cuts it (Linux URLSession has no byte stream).
- Not on Linux: JetlinkUI, the IOUSBHost gadget, CoreML and Metal.

Locally, run the steps of CI's `swift-linux` job (`.github/workflows/ci.yml`)
in `swift:6.3.3-jammy`, the image it and the release builds use.
`scripts/build-linux.sh <flavor> ort` fetches the pinned onnxruntime and prints
its directory (`linux-aarch64` on Apple silicon).

## When a change is intentional

1. Change the Python, or the Swift-owned golden.
2. Regenerate what moved, from the checkout root:

   ```bash
   .venv/bin/python JetlinkKit/Scripts/make_pins.py
   .venv/bin/python JetlinkKit/Scripts/make_conformance_fixtures.py   # or one part: wire, staging, layout, registry
   ```

   The staging files match only under the pinned onnx
   (`pip install -r JetlinkKit/Scripts/fixture-pins.txt`). A version bump in
   `jetlink/__init__.py` needs `make_pins.py` too: it writes
   `Pinned.productVersion`.
3. Change the Swift until `swift test --package-path JetlinkKit` passes.
4. Commit the Python, fixtures and Swift together.

## What the Swift preparation refuses on purpose

It has no shape or type inferrer. Where an export omits a shape or type, the
Python preparation inferred it; the Swift refuses the layout, saying what is
missing, or leaves a Gather index as it is. The frozen `noshape`, `notype`,
`noentry` and `unrecorded` fixtures in `JetlinkONNXTests/Fixtures` record each
case. The driving models checked so far record every shape and type these
passes read.

#!/usr/bin/env bash
# Runs JetlinkKit's Swift tests on an Android device or emulator: the same
# suites as on the Mac and Linux, built with the Swift SDK for Android, pushed
# with their fixtures and the libraries they load, and run through adb.
#
#   swift-test-device.sh ONNXRUNTIME_AAR [TARGET...]
#
# TARGET is JetlinkKitTests, JetlinkONNXTests, JetlinkRegistryTests or
# JetlinkServerTests; all four by default. The fixtures are read in place on
# the Mac, so the device gets a copy of those folders and JETLINK_TEST_ROOT
# points the tests at it (Tests/JetlinkTestSupport/SourceTree.swift).
#
# Uses the toolchain, SDK and NDK swift-env.sh finds, and the one adb device.
set -euo pipefail
source "$(dirname "$0")/swift-env.sh"

DEVICE_DIR=/data/local/tmp/jetlink-tests
AAR=${1:?usage: swift-test-device.sh ONNXRUNTIME_AAR [TARGET...]}
shift
TARGETS=("$@")
[[ ${#TARGETS[@]} -gt 0 ]] || TARGETS=(JetlinkKitTests JetlinkONNXTests JetlinkRegistryTests JetlinkServerTests)

BUILD="$ANDROID_DIR/build/swift-tests"
STAGE="$BUILD/device"
ADB=${ADB:-$(command -v adb || echo "${ANDROID_HOME:-$HOME/Library/Android/sdk}/platform-tools/adb")}
HEADERS="$BUILD/onnxruntime/include"
onnxruntime_headers "$AAR" "$HEADERS"

# The tests link the Swift runtime dynamically: swift-testing has no static
# build in the SDK. Its libraries go to the device beside the runners.
args=(--package-path "$REPO/JetlinkKit" --build-tests --swift-sdk "$TRIPLE" --build-path "$BUILD" -Xcc "-I$HEADERS")
"$SWIFT" build "${args[@]}"
PRODUCTS=$("$SWIFT" build "${args[@]}" --show-bin-path)

rm -rf "$STAGE"
mkdir -p "$STAGE/repo/JetlinkKit/Tests" "$STAGE/repo/tests"
for target in "${TARGETS[@]}"; do
  cp "$PRODUCTS/$target-test-runner" "$PRODUCTS/$target.so" "$STAGE/"
done
cp -R "$PRODUCTS"/*.bundle "$STAGE/" 2>/dev/null || true
cp "$BUNDLE"/swift-resources/usr/lib/swift-aarch64/android/*.so "$STAGE/"
cp "$LIBCXX" "$STAGE/"
unzip -o -q -j "$AAR" 'jni/arm64-v8a/libonnxruntime.so' -d "$STAGE"
for fixtures in JetlinkServerTests JetlinkONNXTests; do
  mkdir -p "$STAGE/repo/JetlinkKit/Tests/$fixtures"
  cp -R "$REPO/JetlinkKit/Tests/$fixtures/Fixtures" "$STAGE/repo/JetlinkKit/Tests/$fixtures/"
done
cp -R "$REPO/tests/fixtures" "$STAGE/repo/tests/"

"$ADB" shell rm -rf "$DEVICE_DIR"
"$ADB" shell mkdir -p "$DEVICE_DIR"
"$ADB" push "$STAGE/." "$DEVICE_DIR/" >/dev/null

status=0
for target in "${TARGETS[@]}"; do
  echo "== $target"
  "$ADB" shell "cd $DEVICE_DIR && chmod +x $target-test-runner && JETLINK_TEST_ROOT=$DEVICE_DIR/repo LD_LIBRARY_PATH=. ./$target-test-runner --testing-library swift-testing" || status=1
done
exit $status

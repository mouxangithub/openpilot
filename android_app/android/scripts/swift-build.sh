#!/usr/bin/env bash
# Builds libjetlink.so, the jetlink server the Android app runs in process:
# JetlinkKit's `jetlink` product, cross-compiled with the Swift SDK for
# Android, the Swift runtime and Foundation linked in statically. Copies it
# and the NDK's libc++_shared.so into OUT/arm64-v8a for the APK.
#
#   swift-build.sh OUT ONNXRUNTIME_AAR [release|debug]
#
# The app's Gradle build runs this (the swiftBuild task) with the
# onnxruntime AAR it resolved; the build needs only the AAR's C headers,
# because the library opens libonnxruntime.so at run time.
#
# Needs the toolchain, SDK and NDK swift-env.sh finds.
set -euo pipefail
source "$(dirname "$0")/swift-env.sh"

ABI=arm64-v8a
OUT=${1:?usage: swift-build.sh OUT ONNXRUNTIME_AAR [release|debug]}
AAR=${2:?usage: swift-build.sh OUT ONNXRUNTIME_AAR [release|debug]}
CONFIG=${3:-release}
BUILD="$ANDROID_DIR/build/swift"
HEADERS="$BUILD/onnxruntime/include"
onnxruntime_headers "$AAR" "$HEADERS"

args=(
  --package-path "$REPO/JetlinkKit"
  --product jetlink
  -c "$CONFIG"
  --swift-sdk "$TRIPLE"
  --build-path "$BUILD"
  -Xcc "-I$HEADERS"
  --static-swift-stdlib
  # Static FoundationNetworking's curl uses the SDK's OpenSSL, which nothing
  # else names (nor the zlib it inflates with): without these the library
  # fails to load on X509_free.
  -Xlinker -lssl -Xlinker -lcrypto -Xlinker -lz
)
"$SWIFT" build "${args[@]}"
BIN=$("$SWIFT" build "${args[@]}" --show-bin-path)

mkdir -p "$OUT/$ABI"
cp "$BIN/libjetlink.so" "$OUT/$ABI/libjetlink.so"
cp "$LIBCXX" "$OUT/$ABI/"
echo "swift-build.sh: $OUT/$ABI/libjetlink.so ($CONFIG)"

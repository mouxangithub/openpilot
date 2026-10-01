# Sourced by swift-build.sh and swift-test-device.sh: the Swift toolchain, the
# Swift SDK for Android of the same version, and the NDK the SDK was built
# with (android/README.md). Sets SWIFT, BUNDLE, TRIPLE and ANDROID_NDK_HOME.
#
#   SWIFT              the swift binary, if not the one found below
#   ANDROID_NDK_HOME   the NDK, if not $ANDROID_HOME/ndk/$NDK_VERSION

SWIFT_VERSION=6.4.0
# app/build.gradle.kts names the same NDK (PinnedTest holds them together).
NDK_VERSION=30.0.16248370
API=31
TRIPLE=aarch64-unknown-linux-android$API
SDK_NAME="swift-$SWIFT_VERSION-RELEASE_android"

ANDROID_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$ANDROID_DIR/.." && pwd)"

fail() {
  echo "$(basename "$0"): $*" >&2
  exit 1
}

# The toolchain: Xcode's swift cannot use a swift.org SDK, so look for the
# open-source one first.
if [[ -z "${SWIFT:-}" ]]; then
  for candidate in \
    "$HOME/Library/Developer/Toolchains/swift-$SWIFT_VERSION-RELEASE.xctoolchain/usr/bin/swift" \
    "$HOME/.local/share/swiftly/toolchains/$SWIFT_VERSION/usr/bin/swift" \
    "$(command -v swift || true)"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      SWIFT=$candidate
      break
    fi
  done
fi
[[ -n "${SWIFT:-}" ]] || fail "no Swift $SWIFT_VERSION toolchain; install it with swiftly (android/README.md)"
"$SWIFT" --version 2>&1 | grep -q "Swift version ${SWIFT_VERSION%.0}" ||
  fail "$SWIFT is not Swift $SWIFT_VERSION (the SDK for Android must match the toolchain exactly)"

# The SDK, and its link to the NDK. swiftpm on Linux keeps SDKs under the
# account's home from the password file, not $HOME, which differs in CI
# containers (GitHub sets HOME=/github/home for root).
BUNDLE=""
ACCOUNT_HOME="$(getent passwd "$(id -u)" 2>/dev/null | cut -d: -f6 || true)"
for root in "$HOME/Library/org.swift.swiftpm/swift-sdks" "$HOME/.swiftpm/swift-sdks" \
  "${XDG_CONFIG_HOME:-$HOME/.config}/swiftpm/swift-sdks" ${ACCOUNT_HOME:+"$ACCOUNT_HOME/.swiftpm/swift-sdks"}; do
  if [[ -d "$root/$SDK_NAME.artifactbundle" ]]; then
    BUNDLE="$root/$SDK_NAME.artifactbundle/swift-android"
    break
  fi
done
[[ -n "$BUNDLE" ]] || fail "the Swift SDK for Android ($SDK_NAME) is not installed (android/README.md)"

if [[ -z "${ANDROID_NDK_HOME:-}" ]]; then
  ANDROID_NDK_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}/ndk/$NDK_VERSION"
fi
[[ -d "$ANDROID_NDK_HOME/toolchains/llvm/prebuilt" ]] || fail "no NDK at $ANDROID_NDK_HOME (NDK $NDK_VERSION)"
export ANDROID_NDK_HOME
if [[ ! -d "$BUNDLE/ndk-sysroot" ]]; then
  bash "$BUNDLE/scripts/setup-android-sdk.sh"
fi
LIBCXX="$(echo "$ANDROID_NDK_HOME"/toolchains/llvm/prebuilt/*/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so)"

# onnxruntime's C headers, from the AAR the app ships, under DIR/onnxruntime.
onnxruntime_headers() {
  mkdir -p "$2/onnxruntime"
  unzip -o -q -j "$1" 'headers/*' -d "$2/onnxruntime"
}

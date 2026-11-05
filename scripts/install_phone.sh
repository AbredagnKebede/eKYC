#!/usr/bin/env bash
# USB install of Fayda Onboard APK against local Docker API via adb reverse.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${ANDROID_HOME:-$HOME/Android/Sdk}/platform-tools:$PATH"
export PUB_HOSTED_URL="${PUB_HOSTED_URL:-https://pub.flutter-io.cn}"
export FLUTTER_STORAGE_BASE_URL="${FLUTTER_STORAGE_BASE_URL:-https://storage.flutter-io.cn}"

APK="$ROOT/mobile/build/app/outputs/flutter-apk/app-debug.apk"

if [[ ! -f "$APK" ]]; then
  echo "Building debug APK..."
  (cd "$ROOT/mobile" && flutter build apk --debug)
fi

echo "Connected devices:"
adb devices -l

echo "Forwarding phone localhost:8005 -> host:8005"
adb reverse tcp:8005 tcp:8005

echo "Installing $APK"
adb install -r "$APK"

echo "Launching et.ekyc.ekyc_mobile"
adb shell am start -n et.ekyc.ekyc_mobile/.MainActivity || \
  adb shell monkey -p et.ekyc.ekyc_mobile -c android.intent.category.LAUNCHER 1

echo "Done. In the app keep API as http://127.0.0.1:8005 (adb reverse)."
echo "Pilot OTP from Fayda sandbox: 123456"

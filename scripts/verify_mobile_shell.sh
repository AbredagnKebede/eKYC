#!/usr/bin/env bash
# Objective mobile checks: analyze + PIN policy tests.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/mobile"
flutter pub get
flutter analyze
flutter test test/pin_change_policy_test.dart
echo "OK mobile analyze + PIN policy tests"

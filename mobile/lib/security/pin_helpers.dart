import 'dart:convert';

import 'package:crypto/crypto.dart';

/// Digits-only PIN, 4–6 characters.
bool isValidPinFormat(String pin) {
  if (pin.length < 4 || pin.length > 6) return false;
  return RegExp(r'^\d+$').hasMatch(pin);
}

String hashPin(String pin, String deviceFingerprint) {
  return sha256.convert(utf8.encode('ekyc-pin:$pin:$deviceFingerprint')).toString();
}

/// Business rules for set / change / disable without UI dependencies.
class PinChangePolicy {
  static bool requiresCurrentPinBeforeChange(String? existingHash) {
    return existingHash != null && existingHash.isNotEmpty;
  }

  /// When a PIN already exists, empty [newPin]+[confirmPin] means keep the same PIN
  /// (e.g. only toggle fingerprint). Still requires [currentPin] verification.
  static String? validateSetOrChange({
    required String? existingHash,
    required String? currentPin,
    required String newPin,
    required String confirmPin,
    required String Function(String pin) hash,
  }) {
    final hasExisting = requiresCurrentPinBeforeChange(existingHash);
    if (hasExisting) {
      if (currentPin == null || currentPin.isEmpty) {
        return 'current_required';
      }
      if (hash(currentPin) != existingHash) {
        return 'current_wrong';
      }
      final keepingPin = newPin.isEmpty && confirmPin.isEmpty;
      if (keepingPin) {
        return null;
      }
    }
    if (!isValidPinFormat(newPin)) {
      return 'format';
    }
    if (newPin != confirmPin) {
      return 'mismatch';
    }
    return null;
  }

  /// True when save should keep the stored hash instead of writing a new one.
  static bool isKeepExistingPin({
    required String? existingHash,
    required String newPin,
    required String confirmPin,
  }) {
    return requiresCurrentPinBeforeChange(existingHash) &&
        newPin.isEmpty &&
        confirmPin.isEmpty;
  }

  static String? validateDisable({
    required String? existingHash,
    required String? currentPin,
    required String Function(String pin) hash,
  }) {
    if (!requiresCurrentPinBeforeChange(existingHash)) {
      return null;
    }
    if (currentPin == null || currentPin.isEmpty) {
      return 'current_required';
    }
    if (hash(currentPin) != existingHash) {
      return 'current_wrong';
    }
    return null;
  }
}

const int kMaxPinUnlockAttempts = 5;

/// Tracks failed unlock attempts and temporary lockout.
class PinLockoutState {
  PinLockoutState({this.failedAttempts = 0, this.lockedUntil});

  int failedAttempts;
  DateTime? lockedUntil;

  bool get isLockedOut {
    final until = lockedUntil;
    if (until == null) return false;
    return DateTime.now().isBefore(until);
  }

  Duration? get remainingLockout {
    final until = lockedUntil;
    if (until == null || !isLockedOut) return null;
    return until.difference(DateTime.now());
  }

  /// Returns true if unlock succeeded.
  bool recordUnlockAttempt(bool success) {
    if (isLockedOut) return false;
    if (success) {
      failedAttempts = 0;
      lockedUntil = null;
      return true;
    }
    failedAttempts += 1;
    if (failedAttempts >= kMaxPinUnlockAttempts) {
      lockedUntil = DateTime.now().add(const Duration(minutes: 5));
      failedAttempts = 0;
    }
    return false;
  }
}

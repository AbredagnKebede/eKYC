import 'package:flutter_test/flutter_test.dart';

import 'package:ekyc_mobile/security/pin_helpers.dart';

void main() {
  const deviceFp = 'test-device-fp';

  String hash(String pin) => hashPin(pin, deviceFp);

  group('PinChangePolicy', () {
    test('requires current PIN when hash exists', () {
      expect(PinChangePolicy.requiresCurrentPinBeforeChange(null), isFalse);
      expect(PinChangePolicy.requiresCurrentPinBeforeChange(''), isFalse);
      expect(PinChangePolicy.requiresCurrentPinBeforeChange('abc'), isTrue);
    });

    test('changing PIN without current PIN is rejected when hash exists', () {
      final existing = hash('1234');
      final err = PinChangePolicy.validateSetOrChange(
        existingHash: existing,
        currentPin: null,
        newPin: '5678',
        confirmPin: '5678',
        hash: hash,
      );
      expect(err, 'current_required');
    });

    test('changing PIN with wrong current PIN is rejected', () {
      final existing = hash('1234');
      final err = PinChangePolicy.validateSetOrChange(
        existingHash: existing,
        currentPin: '9999',
        newPin: '5678',
        confirmPin: '5678',
        hash: hash,
      );
      expect(err, 'current_wrong');
    });

    test('changing PIN succeeds with correct current PIN', () {
      final existing = hash('1234');
      final err = PinChangePolicy.validateSetOrChange(
        existingHash: existing,
        currentPin: '1234',
        newPin: '567890',
        confirmPin: '567890',
        hash: hash,
      );
      expect(err, isNull);
    });

    test('enabling fingerprint keeps PIN when new fields are blank', () {
      final existing = hash('1234');
      final err = PinChangePolicy.validateSetOrChange(
        existingHash: existing,
        currentPin: '1234',
        newPin: '',
        confirmPin: '',
        hash: hash,
      );
      expect(err, isNull);
      expect(
        PinChangePolicy.isKeepExistingPin(
          existingHash: existing,
          newPin: '',
          confirmPin: '',
        ),
        isTrue,
      );
    });

    test('keep-PIN path still requires correct current PIN', () {
      final existing = hash('1234');
      final err = PinChangePolicy.validateSetOrChange(
        existingHash: existing,
        currentPin: '0000',
        newPin: '',
        confirmPin: '',
        hash: hash,
      );
      expect(err, 'current_wrong');
    });

    test('partial new PIN without confirm is rejected', () {
      final existing = hash('1234');
      final err = PinChangePolicy.validateSetOrChange(
        existingHash: existing,
        currentPin: '1234',
        newPin: '5678',
        confirmPin: '',
        hash: hash,
      );
      expect(err, 'mismatch');
    });

    test('first-time set rejects blank PIN (keep path only when hash exists)', () {
      final err = PinChangePolicy.validateSetOrChange(
        existingHash: null,
        currentPin: null,
        newPin: '',
        confirmPin: '',
        hash: hash,
      );
      expect(err, 'format');
      expect(
        PinChangePolicy.isKeepExistingPin(
          existingHash: null,
          newPin: '',
          confirmPin: '',
        ),
        isFalse,
      );
    });
  });
}

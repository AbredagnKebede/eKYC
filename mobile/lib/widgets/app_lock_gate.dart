import 'package:flutter/material.dart';
import 'package:local_auth/local_auth.dart';

import '../l10n/strings.dart';
import '../security/pin_helpers.dart';
import '../theme.dart';

class AppLockGate extends StatefulWidget {
  const AppLockGate({
    super.key,
    required this.locale,
    required this.title,
    required this.hint,
    required this.onUnlock,
    required this.lockout,
    this.biometricEnabled = false,
    this.onLockoutChanged,
  });

  final String locale;
  final String title;
  final String hint;
  final bool Function(String pin) onUnlock;
  final bool biometricEnabled;
  final PinLockoutState lockout;
  final void Function(PinLockoutState)? onLockoutChanged;

  @override
  State<AppLockGate> createState() => _AppLockGateState();
}

class _AppLockGateState extends State<AppLockGate> {
  final _ctrl = TextEditingController();
  final _auth = LocalAuthentication();
  String? _err;
  bool _bioBusy = false;

  S get s => S(widget.locale);

  @override
  void initState() {
    super.initState();
    if (widget.biometricEnabled) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _tryBiometric());
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _tryBiometric() async {
    if (_bioBusy || widget.lockout.isLockedOut) return;
    setState(() => _bioBusy = true);
    try {
      final can = await _auth.canCheckBiometrics;
      if (!can) return;
      final ok = await _auth.authenticate(
        localizedReason: s.t('lock.bio_reason'),
        options: const AuthenticationOptions(biometricOnly: true, stickyAuth: true),
      );
      if (ok && mounted) {
        widget.onLockoutChanged?.call(widget.lockout..recordUnlockAttempt(true));
        // Parent treats biometric as unlock without PIN — use sentinel.
        widget.onUnlock('__biometric__');
      }
    } catch (_) {
      // fall back to PIN
    } finally {
      if (mounted) setState(() => _bioBusy = false);
    }
  }

  void _tryPin() {
    if (widget.lockout.isLockedOut) {
      setState(() => _err = s.t('lock.lockout'));
      return;
    }
    final pin = _ctrl.text.trim();
    final ok = widget.onUnlock(pin);
    widget.onLockoutChanged?.call(widget.lockout..recordUnlockAttempt(ok));
    if (ok) {
      setState(() => _err = null);
    } else {
      setState(() => _err = s.t('lock.wrong'));
    }
  }

  @override
  Widget build(BuildContext context) {
    final lockout = widget.lockout;
    final remaining = lockout.remainingLockout;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Spacer(),
        Text(widget.title, style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        Text(widget.hint, style: const TextStyle(color: EkycColors.muted)),
        if (lockout.isLockedOut && remaining != null) ...[
          const SizedBox(height: 12),
          Text(
            s.t('lock.lockout_minutes').replaceAll('{n}', '${remaining.inMinutes.clamp(1, 99)}'),
            style: const TextStyle(color: EkycColors.danger, height: 1.35),
          ),
        ],
        const SizedBox(height: 20),
        TextField(
          controller: _ctrl,
          obscureText: true,
          keyboardType: TextInputType.number,
          maxLength: 6,
          enabled: !lockout.isLockedOut,
          decoration: InputDecoration(labelText: s.t('lock.pin')),
          onSubmitted: (_) => _tryPin(),
        ),
        if (_err != null) ...[
          const SizedBox(height: 8),
          Text(_err!, style: const TextStyle(color: EkycColors.danger)),
        ],
        const SizedBox(height: 16),
        FilledButton(
          onPressed: lockout.isLockedOut ? null : _tryPin,
          child: Text(s.t('lock.unlock')),
        ),
        if (widget.biometricEnabled && !lockout.isLockedOut) ...[
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: _bioBusy ? null : _tryBiometric,
            icon: const Icon(Icons.fingerprint_rounded),
            label: Text(s.t('lock.use_biometric')),
          ),
        ],
        const Spacer(),
      ],
    );
  }
}

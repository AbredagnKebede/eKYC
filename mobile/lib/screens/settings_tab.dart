import 'package:flutter/material.dart';

import '../l10n/strings.dart';
import '../theme.dart';

typedef ThemeModeSetter = void Function(ThemeMode mode);

class SettingsTab extends StatelessWidget {
  const SettingsTab({
    super.key,
    required this.locale,
    required this.themeMode,
    required this.appLockEnabled,
    required this.biometricEnabled,
    required this.onLocale,
    required this.onThemeMode,
    required this.onConfigureLock,
    required this.onSignOut,
    required this.onDevApiBase,
  });

  final String locale;
  final ThemeMode themeMode;
  final bool appLockEnabled;
  final bool biometricEnabled;
  final ValueChanged<String> onLocale;
  final ThemeModeSetter onThemeMode;
  final VoidCallback onConfigureLock;
  final VoidCallback onSignOut;
  final VoidCallback onDevApiBase;

  S get s => S(locale);

  @override
  Widget build(BuildContext context) {
    final isDark = themeMode == ThemeMode.dark;

    return ListView(
      children: [
        Text(s.t('settings.title'), style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 6),
        Text(s.t('settings.subtitle'), style: Theme.of(context).textTheme.bodyMedium),
        const SizedBox(height: 18),
        _SectionLabel(label: s.t('settings.language')),
        const SizedBox(height: 8),
        SegmentedButton<String>(
          segments: [
            ButtonSegment(value: 'en', label: Text(s.t('settings.lang_en'))),
            ButtonSegment(value: 'am', label: Text(s.t('settings.lang_am'))),
            ButtonSegment(value: 'om', label: Text(s.t('settings.lang_om'))),
          ],
          selected: {locale},
          onSelectionChanged: (v) => onLocale(v.first),
        ),
        const SizedBox(height: 22),
        _SectionLabel(label: s.t('settings.appearance')),
        const SizedBox(height: 8),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(s.t('settings.dark_mode')),
          subtitle: Text(s.t('settings.dark_mode_hint')),
          value: isDark,
          onChanged: (v) => onThemeMode(v ? ThemeMode.dark : ThemeMode.light),
        ),
        const SizedBox(height: 14),
        _SectionLabel(label: s.t('settings.security')),
        const SizedBox(height: 8),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(s.t('lock.configure')),
          subtitle: Text(appLockEnabled ? s.t('settings.lock_on') : s.t('settings.lock_off')),
          trailing: const Icon(Icons.chevron_right_rounded),
          onTap: onConfigureLock,
        ),
        if (appLockEnabled)
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(s.t('settings.biometric')),
            subtitle: Text(
              biometricEnabled ? s.t('settings.bio_on') : s.t('settings.bio_off'),
            ),
            trailing: const Icon(Icons.chevron_right_rounded),
            leading: Icon(Icons.fingerprint_rounded, color: Theme.of(context).colorScheme.secondary),
            onTap: onConfigureLock,
          ),
        const SizedBox(height: 22),
        OutlinedButton(
          onPressed: onSignOut,
          child: Text(s.t('nav.sign_out')),
        ),
        const SizedBox(height: 28),
        GestureDetector(
          onLongPress: onDevApiBase,
          child: Text(
            s.t('settings.dev_hint'),
            textAlign: TextAlign.center,
            style: const TextStyle(color: EkycColors.muted, fontSize: 12, height: 1.35),
          ),
        ),
      ],
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: const TextStyle(
        fontWeight: FontWeight.w700,
        color: EkycColors.ink,
        fontSize: 13,
        letterSpacing: 0.2,
      ),
    );
  }
}

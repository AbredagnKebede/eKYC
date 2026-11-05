import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Institutional Ethiopian banking onboarding — cool paper, navy, restrained teal.
/// Deliberately avoids dark-green/gold, purple SaaS, and cream/terracotta AI defaults.
class EkycColors {
  static const paper = Color(0xFFF7F8FA);
  static const surface = Color(0xFFFFFFFF);
  static const ink = Color(0xFF121826);
  static const muted = Color(0xFF5B6575);
  static const line = Color(0xFFD8DEE6);
  static const navy = Color(0xFF0A2540);
  static const teal = Color(0xFF0F766E);
  static const tealSoft = Color(0xFFE6F4F2);
  static const danger = Color(0xFFB42318);
  static const dangerSoft = Color(0xFFFEECEC);
}

ThemeData buildEkycTheme() {
  const ink = EkycColors.ink;
  const muted = EkycColors.muted;
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    scaffoldBackgroundColor: EkycColors.paper,
    colorScheme: const ColorScheme.light(
      primary: EkycColors.navy,
      secondary: EkycColors.teal,
      surface: EkycColors.surface,
      error: EkycColors.danger,
      onPrimary: Colors.white,
      onSecondary: Colors.white,
      onSurface: ink,
      onError: Colors.white,
    ),
    appBarTheme: const AppBarTheme(
      elevation: 0,
      scrolledUnderElevation: 0,
      backgroundColor: EkycColors.paper,
      foregroundColor: ink,
      systemOverlayStyle: SystemUiOverlayStyle.dark,
      titleTextStyle: TextStyle(
        color: ink,
        fontSize: 17,
        fontWeight: FontWeight.w600,
        letterSpacing: -0.2,
      ),
    ),
    textTheme: const TextTheme(
      displaySmall: TextStyle(
        fontSize: 34,
        height: 1.15,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.8,
        color: ink,
      ),
      headlineMedium: TextStyle(
        fontSize: 24,
        height: 1.25,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.4,
        color: ink,
      ),
      titleLarge: TextStyle(
        fontSize: 18,
        height: 1.3,
        fontWeight: FontWeight.w600,
        letterSpacing: -0.2,
        color: ink,
      ),
      titleMedium: TextStyle(
        fontSize: 16,
        height: 1.35,
        fontWeight: FontWeight.w600,
        color: ink,
      ),
      bodyLarge: TextStyle(fontSize: 16, height: 1.5, color: muted),
      bodyMedium: TextStyle(fontSize: 14, height: 1.45, color: muted),
      labelLarge: TextStyle(
        fontSize: 15,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.1,
        color: Colors.white,
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: EkycColors.navy,
        foregroundColor: Colors.white,
        elevation: 0,
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: EkycColors.navy,
        side: const BorderSide(color: EkycColors.line, width: 1.2),
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: EkycColors.teal,
        foregroundColor: Colors.white,
        elevation: 0,
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: EkycColors.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: EkycColors.line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: EkycColors.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: EkycColors.navy, width: 1.5),
      ),
      labelStyle: const TextStyle(color: muted),
      hintStyle: TextStyle(color: muted.withValues(alpha: 0.7)),
    ),
    dividerTheme: const DividerThemeData(color: EkycColors.line, thickness: 1, space: 1),
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: EkycColors.navy,
      contentTextStyle: TextStyle(color: Colors.white),
    ),
  );
}

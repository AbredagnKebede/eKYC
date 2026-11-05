import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

/// Fayda Onboard — highland paper, ink navy, river teal.
/// Avoids purple SaaS, cream/terracotta, and dark-green/gold clichés.
class EkycColors {
  static const paper = Color(0xFFF3F5F8);
  static const mist = Color(0xFFE8EEF4);
  static const surface = Color(0xFFFFFFFF);
  static const ink = Color(0xFF0E1A2B);
  static const muted = Color(0xFF5A6678);
  static const line = Color(0xFFD2DAE4);
  static const navy = Color(0xFF0A2540);
  static const navyDeep = Color(0xFF06182C);
  static const teal = Color(0xFF0F766E);
  static const tealBright = Color(0xFF14B8A6);
  static const tealSoft = Color(0xFFE4F4F1);
  static const gold = Color(0xFFB8923A);
  static const danger = Color(0xFFB42318);
  static const dangerSoft = Color(0xFFFEECEC);
}

ThemeData buildEkycTheme() {
  final base = GoogleFonts.plusJakartaSansTextTheme();
  final display = GoogleFonts.fraunces();

  TextStyle merge(TextStyle? a, TextStyle b) => (a ?? const TextStyle()).merge(b);

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
      onSurface: EkycColors.ink,
      onError: Colors.white,
    ),
    textTheme: base.copyWith(
      displaySmall: merge(
        display,
        const TextStyle(
          fontSize: 34,
          height: 1.12,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.7,
          color: EkycColors.ink,
        ),
      ),
      headlineMedium: merge(
        display,
        const TextStyle(
          fontSize: 24,
          height: 1.22,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.35,
          color: EkycColors.ink,
        ),
      ),
      titleLarge: merge(
        base.titleLarge,
        const TextStyle(
          fontSize: 18,
          height: 1.3,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.2,
          color: EkycColors.ink,
        ),
      ),
      titleMedium: merge(
        base.titleMedium,
        const TextStyle(
          fontSize: 16,
          height: 1.35,
          fontWeight: FontWeight.w600,
          color: EkycColors.ink,
        ),
      ),
      bodyLarge: merge(
        base.bodyLarge,
        const TextStyle(fontSize: 16, height: 1.5, color: EkycColors.muted),
      ),
      bodyMedium: merge(
        base.bodyMedium,
        const TextStyle(fontSize: 14, height: 1.45, color: EkycColors.muted),
      ),
      labelLarge: merge(
        base.labelLarge,
        const TextStyle(
          fontSize: 15,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.05,
          color: Colors.white,
        ),
      ),
    ),
    appBarTheme: AppBarTheme(
      elevation: 0,
      scrolledUnderElevation: 0,
      backgroundColor: EkycColors.paper,
      foregroundColor: EkycColors.ink,
      systemOverlayStyle: SystemUiOverlayStyle.dark,
      titleTextStyle: GoogleFonts.plusJakartaSans(
        color: EkycColors.ink,
        fontSize: 16,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.2,
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: EkycColors.navy,
        foregroundColor: Colors.white,
        elevation: 0,
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: GoogleFonts.plusJakartaSans(fontSize: 15, fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: EkycColors.navy,
        side: const BorderSide(color: EkycColors.line, width: 1.2),
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: GoogleFonts.plusJakartaSans(fontSize: 15, fontWeight: FontWeight.w600),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: EkycColors.teal,
        foregroundColor: Colors.white,
        elevation: 0,
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: GoogleFonts.plusJakartaSans(fontSize: 15, fontWeight: FontWeight.w700),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: EkycColors.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: EkycColors.line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: EkycColors.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: EkycColors.navy, width: 1.5),
      ),
      labelStyle: const TextStyle(color: EkycColors.muted),
      hintStyle: TextStyle(color: EkycColors.muted.withValues(alpha: 0.7)),
    ),
    dividerTheme: const DividerThemeData(color: EkycColors.line, thickness: 1, space: 1),
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: EkycColors.navy,
      contentTextStyle: TextStyle(color: Colors.white),
    ),
  );
}

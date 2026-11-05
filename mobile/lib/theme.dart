import 'package:flutter/material.dart';

/// Highland / coffee-belt palette — deep green, brass, parchment.
class EkycColors {
  static const forest = Color(0xFF0C2F24);
  static const canopy = Color(0xFF1A4D3A);
  static const leaf = Color(0xFF2F6B4F);
  static const brass = Color(0xFFC9A227);
  static const parchment = Color(0xFFF3E7D3);
  static const ink = Color(0xFF14201A);
  static const danger = Color(0xFFB33A3A);
  static const mist = Color(0xFFD7E5DC);
}

ThemeData buildEkycTheme() {
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: EkycColors.forest,
    colorScheme: const ColorScheme.dark(
      primary: EkycColors.brass,
      secondary: EkycColors.leaf,
      surface: EkycColors.canopy,
      error: EkycColors.danger,
      onPrimary: EkycColors.ink,
      onSurface: EkycColors.parchment,
    ),
    textTheme: const TextTheme(
      displayLarge: TextStyle(fontFamily: 'serif', fontSize: 40, color: EkycColors.parchment, fontWeight: FontWeight.w600),
      headlineMedium: TextStyle(fontFamily: 'serif', fontSize: 28, color: EkycColors.parchment, fontWeight: FontWeight.w600),
      titleLarge: TextStyle(fontFamily: 'serif', fontSize: 20, color: EkycColors.parchment, fontWeight: FontWeight.w600),
      bodyLarge: TextStyle(fontSize: 16, color: EkycColors.mist, height: 1.45),
      bodyMedium: TextStyle(fontSize: 14, color: EkycColors.mist, height: 1.4),
      labelLarge: TextStyle(fontSize: 15, color: EkycColors.ink, fontWeight: FontWeight.w700, letterSpacing: 0.4),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: EkycColors.brass,
        foregroundColor: EkycColors.ink,
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: EkycColors.parchment,
        side: const BorderSide(color: EkycColors.brass, width: 1.2),
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: EkycColors.canopy.withValues(alpha: 0.85),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: EkycColors.brass.withValues(alpha: 0.35)),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: EkycColors.brass.withValues(alpha: 0.35)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: EkycColors.brass, width: 1.6),
      ),
      labelStyle: const TextStyle(color: EkycColors.mist),
    ),
  );
}

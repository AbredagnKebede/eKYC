---
name: flutter-mobile-ui
description: Flutter mobile UI craft for Fayda Onboard — distinctive institutional screens, intentional type, and non-generic palettes. Use when redesigning or reviewing the Android/iOS client.
---

# Flutter Mobile UI (Fayda Onboard)

Operate as a product designer + Flutter engineer for Ethiopian digital banking onboarding.

## Visual direction

- Brand-first welcome: product name dominates the first viewport; one supporting sentence; one CTA.
- Palette: cool paper `#F3F5F8`, ink `#0E1A2B`, navy `#0A2540`, river teal `#0F766E`, restrained gold accent `#B8923A`.
- Avoid: purple SaaS gradients, cream+terracotta, dark-mode neon, Inter/Roboto defaults, identical rounded cards with soft grey shadows everywhere.
- Type: Fraunces (display) + Plus Jakarta Sans (UI) via `google_fonts`.

## Interaction

- Step progress as a segmented rail, not a lonely LinearProgressIndicator alone.
- Bank picker: searchable full catalogue with short codes; feel like a real registry, not a demo of one bank.
- Motion: one AnimatedSwitcher between steps; press feedback on bank rows; respect reduced motion where possible.

## Quality bar

- Does the first screen still look like a Flutter template after removing the logo? If yes, redesign.
- Does every bank in the sandbox appear and behave consistently? If not, fix the adapter registry first.

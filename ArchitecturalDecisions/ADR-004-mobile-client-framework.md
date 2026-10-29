# ADR-004: Mobile Client Framework and Device Strategy
status: accepted
spec_version: 1

## Context
The target market is Ethiopia, where Android devices (often entry-level with limited RAM and processing power) predominate, alongside spotty network coverage. The client application must render custom typography in four regional languages (Amharic, Afaan Oromo, Tigrinya, English), manage camera streams for liveness, and maintain offline draft persistence.

## Options
- **Option 1: Flutter (Dart)**: Compiles to native ARM/x86 machine code, hardware-accelerated Skia/Impeller graphics pipeline, seamless localized font rendering, robust camera SDK, and native SQLite caching.
- **Option 2: React Native (TypeScript)**: Popular cross-platform framework; however, JavaScript bridge overhead can introduce frame drops during real-time camera face mesh tracking on low-end hardware.
- **Option 3: Pure Native Android (Kotlin)**: Optimal performance for Android; however, duplicates business logic, state machines, and dynamic form renderers when iOS support is introduced in later phases.

## Decision
Adopt **Flutter (Dart)** for the cross-platform mobile application, prioritizing Android compilation for the Phase 1 pilot.

## Rationale
Cites `research/prior_art.md` §Recommended Starting Posture ("Android-first client with multilingual support (Amharic, Afaan Oromo, Tigrinya, English), offline form draft storage, and low-bandwidth payload optimization") and `research/brainstorm.md` §User-Facing Requirements (Requirement 1: "Multilingual Localized Experience").

## Consequences
- Single codebase provides native 60fps rendering even on budget Android smartphones.
- High-quality text rendering of Ge'ez scripts (Ethiopic fonts) without clipping or font fallbacks.
- Local SQLite database provides seamless offline draft saving across user sessions.

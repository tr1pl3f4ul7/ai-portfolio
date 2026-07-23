# mobile/ — Flutter App

Reuses the **same backend** as the web one-pager, and adds a second on-device inference surface —
this time using each platform's built-in AI rather than a downloaded model.

The contrast with `web/` is the point: WebLLM downloads a quantised model to the browser;
`flutter_local_ai` calls an LLM the OS already ships. Same capability, opposite trade-off.

## Stack

| Concern | Choice |
|---|---|
| Framework | Flutter (Dart) |
| On-device AI | `flutter_local_ai` — Apple Foundation Models (iOS) / Gemini Nano via ML Kit GenAI (Android) |
| Crash/error | `sentry_flutter` |
| Analytics | `posthog_flutter` |
| Tests | `flutter test` — widget + unit |
| CI | `mobile-build.yml`, APK artefact on tag |

## Intended layout

```
mobile/
├── lib/
│   ├── main.dart
│   ├── api/            # backend client — mirrors backend/app/schemas.py
│   ├── screens/
│   └── ai/             # on-device summarisation wrapper
├── test/
├── android/
└── ios/
```

## Rules

- **The API client mirrors `backend/app/schemas.py`.** When a backend schema changes, this
  changes with it. Drift here produces runtime failures no test on either side will catch.
- **On-device AI availability is not guaranteed.** It depends on OS version and device hardware —
  older Androids have no Gemini Nano, older iPhones no Foundation Models. Check availability and
  present an honest disabled state. Never silently fall back to the network; that erases the
  distinction the app exists to demonstrate.
- **Widget-test the summariser's three states**: loading, result, error. Actual inference quality
  is verified by hand on a real device.
- **Never commit signing material.** `key.properties`, `*.jks`, `*.keystore` are gitignored —
  keep it that way.
- **The backend base URL is build configuration**, not a hardcoded string.
- Sentry and PostHog init belongs in one place at startup, guarded so tests don't emit real
  events.

## Commands

```bash
flutter pub get
flutter test
flutter run
flutter build apk --release
```

## Environment note

The Flutter SDK here is x64 running under emulation — this dev machine is Windows ARM64 and
Flutter ships no native ARM64 Windows build. Everything works; builds are just slower than you'd
expect. `flutter doctor` also warns about a missing Visual Studio C++ workload: that's only
needed for Flutter **Windows desktop** targets, which are out of scope. Ignore it.

/// Runtime configuration.
///
/// The backend origin is build configuration, never a literal scattered
/// through the source (mobile/CLAUDE.md). Set at build/run time with
/// `--dart-define`, mirroring web's `VITE_API_BASE_URL` /
/// `VITE_CONTACT_BASE_URL` (web/src/config.ts) — defaults to the production
/// origins so `flutter run` with no flags still reaches the live backend.
library;

/// Chat and content — the backend directly.
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'https://api.ljubenvassilev.com',
);

/// Contact — the edge Worker's own domain, not the backend directly, so its
/// internal forward to the real `/contact` can never re-trigger itself
/// (decision 48).
const String contactBaseUrl = String.fromEnvironment(
  'CONTACT_BASE_URL',
  defaultValue: 'https://contact.ljubenvassilev.com',
);

/// Longest a caller waits before a request gives up.
const Duration requestTimeout = Duration(seconds: 60);

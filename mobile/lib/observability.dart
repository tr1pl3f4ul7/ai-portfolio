/// Crash and error reporting.
///
/// Off unless a DSN is configured — off locally and in tests by default,
/// matching backend/app/observability.py and web/src/observability.ts.
library;

import 'package:sentry_flutter/sentry_flutter.dart';

/// Runs [appRunner] (which calls `runApp`) with Sentry initialised around it
/// if a DSN is configured, or plain if not. This is Sentry Flutter's own
/// recommended shape — it needs to wrap app startup to catch errors from the
/// very first frame, not just be called before it.
Future<void> initObservability(Future<void> Function() appRunner) async {
  const dsn = String.fromEnvironment('SENTRY_DSN');
  if (dsn.isEmpty) {
    await appRunner();
    return;
  }

  await SentryFlutter.init((options) {
    options.dsn = dsn;
    // Chat questions and contact details must never leave the device this
    // way — same reasoning as backend/app/observability.py and
    // web/src/observability.ts's scrubbing.
    options.sendDefaultPii = false;
    options.tracesSampleRate = 0.1;
  }, appRunner: appRunner);
}

/// A deliberate, fixed-message test error — see the debug-only button on the
/// Home screen. Carries no data, same reasoning as the backend's
/// `/debug/error` route: it's how Step 7.3's verification is done, confirming
/// a real error reaches Sentry.
void triggerTestCrash() {
  throw StateError('Deliberate test error for Sentry verification (Step 7.3).');
}

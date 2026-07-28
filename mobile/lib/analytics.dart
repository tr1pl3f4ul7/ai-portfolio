/// Product analytics — screen views plus the two explicit events named in
/// docs/PROJECT_PLAN.md's Step 7.3: chat used, summarizer used.
///
/// Off without a key, same reasoning as observability.dart. Behind an
/// interface, not the plugin directly, so widget tests substitute a
/// recording fake rather than hitting the real SDK.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:posthog_flutter/posthog_flutter.dart';

abstract class Analytics {
  void screen(String name);
  void track(String event, [Map<String, Object>? properties]);
}

class PostHogAnalytics implements Analytics {
  @override
  void screen(String name) {
    unawaited(Posthog().screen(screenName: name));
  }

  @override
  void track(String event, [Map<String, Object>? properties]) {
    unawaited(Posthog().capture(eventName: event, properties: properties));
  }
}

class NoOpAnalytics implements Analytics {
  @override
  void screen(String name) {}

  @override
  void track(String event, [Map<String, Object>? properties]) {}
}

/// Returns a no-op instance without a key (dev machine, CI), or a real one
/// wired to PostHog once `Posthog().setup()` completes.
Future<Analytics> initAnalytics() async {
  const key = String.fromEnvironment('POSTHOG_KEY');
  if (key.isEmpty) return NoOpAnalytics();

  final config = PostHogConfig(key)
    ..host = const String.fromEnvironment(
      'POSTHOG_HOST',
      defaultValue: 'https://us.i.posthog.com',
    )
    // Verbose [PostHog]-prefixed console logging — debug builds only, so it
    // never ships. This is what Step 7.3's verification greps for.
    ..debug = kDebugMode;
  await Posthog().setup(config);
  return PostHogAnalytics();
}

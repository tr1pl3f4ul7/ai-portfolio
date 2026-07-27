import 'dart:convert';

import 'package:ai_portfolio/ai/summarizer.dart';
import 'package:ai_portfolio/analytics.dart';
import 'package:ai_portfolio/api/client.dart';
import 'package:ai_portfolio/screens/app_shell.dart';
import 'package:flutter/material.dart';
import 'package:flutter_local_ai/flutter_local_ai.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _RecordingAnalytics implements Analytics {
  final List<String> screens = [];
  final List<String> events = [];

  @override
  void screen(String name) => screens.add(name);

  @override
  void track(String event, [Map<String, Object>? properties]) => events.add(event);
}

class _UnavailableSummarizer implements OnDeviceSummarizer {
  @override
  Future<LocalAiPlatformInfo> getPlatformInfo() async => const LocalAiPlatformInfo(
    backend: LocalAiBackend.unsupported,
    platform: 'test',
    apiName: 'test',
    supportsToolCalling: false,
    supportsModelDownload: false,
    supportsPlayStoreRedirect: false,
    isConfigured: false,
  );

  @override
  Future<bool> isAvailable() async => false;

  @override
  Future<String> availabilityReason() async => 'unavailable in tests';

  @override
  Future<ModelFeatureStatus> getModelStatus() async => ModelFeatureStatus.unknown;

  @override
  Stream<ModelDownloadStatus> downloadModel() => const Stream.empty();

  @override
  Future<bool> openAICorePlayStore() async => false;

  @override
  Future<String> summarize(String text) => Future.error(StateError('not used in this test'));
}

/// AppShell mounts every screen eagerly via IndexedStack, so every content
/// endpoint needs a response regardless of which tab the test cares about.
ApiClient _client() {
  return ApiClient(
    httpClient: MockClient((request) async {
      if (request.url.path.contains('/content/profile')) {
        return http.Response(
          jsonEncode({'name': 'ljuben vassilev', 'location': 'brisbane', 'tagline': 't'}),
          200,
        );
      }
      if (request.url.path.contains('/content/summarizer')) {
        return http.Response(
          jsonEncode({'label': 'l', 'heading': 'h', 'description': 'd', 'source_text': 's'}),
          200,
        );
      }
      if (request.url.path.contains('/content/ask')) {
        return http.Response(
          jsonEncode({'label': 'l', 'heading': 'h', 'description': 'd', 'suggestions': []}),
          200,
        );
      }
      if (request.url.path.contains('/content/contact')) {
        return http.Response(jsonEncode({'label': 'l', 'heading': 'h', 'description': 'd'}), 200);
      }
      if (request.url.path.contains('/content/projects')) {
        return http.Response(jsonEncode({'label': 'l', 'heading': 'h', 'items': []}), 200);
      }
      return http.Response('not found', 404);
    }),
  );
}

void main() {
  testWidgets('tracks a screen view for the initial tab on load', (tester) async {
    final analytics = _RecordingAnalytics();

    await tester.pumpWidget(
      MaterialApp(
        home: AppShell(
          apiClient: _client(),
          analytics: analytics,
          summarizer: _UnavailableSummarizer(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(analytics.screens, ['home']);
  });

  testWidgets('tracks a screen view every time the tab changes', (tester) async {
    final analytics = _RecordingAnalytics();

    await tester.pumpWidget(
      MaterialApp(
        home: AppShell(
          apiClient: _client(),
          analytics: analytics,
          summarizer: _UnavailableSummarizer(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // 'Projects' and 'Contact' each appear twice — once as a nav destination
    // label, once as a Home dashboard tile — so scope to the nav bar.
    Finder navLabel(String text) =>
        find.descendant(of: find.byType(NavigationBar), matching: find.text(text));

    await tester.tap(navLabel('Projects'));
    await tester.pumpAndSettle();
    await tester.tap(navLabel('Contact'));
    await tester.pumpAndSettle();

    expect(analytics.screens, ['home', 'projects', 'contact']);
  });
}

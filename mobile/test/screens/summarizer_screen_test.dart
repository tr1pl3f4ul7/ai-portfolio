import 'dart:async';
import 'dart:convert';

import 'package:ai_portfolio/ai/summarizer.dart';
import 'package:ai_portfolio/analytics.dart';
import 'package:ai_portfolio/api/client.dart';
import 'package:ai_portfolio/screens/summarizer_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_local_ai/flutter_local_ai.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _RecordingAnalytics implements Analytics {
  final List<String> events = [];

  @override
  void screen(String name) {}

  @override
  void track(String event, [Map<String, Object>? properties]) => events.add(event);
}

const _noDownloadInfo = LocalAiPlatformInfo(
  backend: LocalAiBackend.unsupported,
  platform: 'test',
  apiName: 'test',
  supportsToolCalling: false,
  supportsModelDownload: false,
  supportsPlayStoreRedirect: false,
  isConfigured: false,
);

class _FakeSummarizer implements OnDeviceSummarizer {
  final LocalAiPlatformInfo platformInfo;
  final bool available;
  final String reason;
  final ModelFeatureStatus modelStatus;
  final Object? summarizeError;
  final Completer<String>? pendingSummary;
  final StreamController<ModelDownloadStatus>? downloadController;
  bool playStoreOpened = false;
  String? lastPrompt;

  _FakeSummarizer({
    this.platformInfo = _noDownloadInfo,
    this.available = true,
    this.reason = 'unavailable',
    this.modelStatus = ModelFeatureStatus.unknown,
    this.summarizeError,
    this.pendingSummary,
    this.downloadController,
  });

  @override
  Future<LocalAiPlatformInfo> getPlatformInfo() async => platformInfo;

  @override
  Future<bool> isAvailable() async => available;

  @override
  Future<String> availabilityReason() async => reason;

  @override
  Future<ModelFeatureStatus> getModelStatus() async => modelStatus;

  @override
  Stream<ModelDownloadStatus> downloadModel() => downloadController!.stream;

  @override
  Future<bool> openAICorePlayStore() async {
    playStoreOpened = true;
    return true;
  }

  @override
  Future<String> summarize(String text) {
    lastPrompt = text;
    if (pendingSummary != null) return pendingSummary!.future;
    if (summarizeError != null) return Future.error(summarizeError!);
    return Future.value('');
  }
}

ApiClient _client() {
  return ApiClient(
    httpClient: MockClient(
      (request) async => http.Response(
        jsonEncode({
          'label': 'summarizer',
          'heading': 'a real summary, generated on your phone',
          'description': 'Condenses on-device.',
          'source_text': 'Source text to condense.',
        }),
        200,
      ),
    ),
  );
}

Widget _harness(OnDeviceSummarizer summarizer, {Analytics? analytics}) {
  return MaterialApp(
    home: Scaffold(
      body: SummarizerScreen(apiClient: _client(), summarizer: summarizer, analytics: analytics),
    ),
  );
}

void main() {
  testWidgets('shows an honest disabled state when the model is unavailable', (tester) async {
    final summarizer = _FakeSummarizer(available: false, reason: 'No on-device model on this device.');

    await tester.pumpWidget(_harness(summarizer));
    await tester.pumpAndSettle();

    expect(find.text('No on-device model on this device.'), findsOneWidget);
    expect(find.text('Summarize on-device'), findsNothing);
    expect(find.text('Open Play Store'), findsNothing);
  });

  testWidgets('offers to open the Play Store when the platform supports it', (tester) async {
    final summarizer = _FakeSummarizer(
      available: false,
      reason: 'Google AICore is missing or out of date.',
      platformInfo: const LocalAiPlatformInfo(
        backend: LocalAiBackend.androidMlKitGenAi,
        platform: 'android',
        apiName: 'ML Kit GenAI',
        supportsToolCalling: false,
        supportsModelDownload: true,
        supportsPlayStoreRedirect: true,
        isConfigured: false,
      ),
      modelStatus: ModelFeatureStatus.unavailable,
    );

    await tester.pumpWidget(_harness(summarizer));
    await tester.pumpAndSettle();

    expect(find.text('Google AICore is missing or out of date.'), findsOneWidget);
    await tester.tap(find.text('Open Play Store'));
    await tester.pump();

    expect(summarizer.playStoreOpened, isTrue);
  });

  testWidgets('shows a download prompt when the model is downloadable', (tester) async {
    final summarizer = _FakeSummarizer(
      available: false,
      platformInfo: const LocalAiPlatformInfo(
        backend: LocalAiBackend.androidMlKitGenAi,
        platform: 'android',
        apiName: 'ML Kit GenAI',
        supportsToolCalling: false,
        supportsModelDownload: true,
        supportsPlayStoreRedirect: false,
        isConfigured: true,
      ),
      modelStatus: ModelFeatureStatus.downloadable,
    );

    await tester.pumpWidget(_harness(summarizer));
    await tester.pumpAndSettle();

    expect(find.text('Download model'), findsOneWidget);
    expect(find.text('Summarize on-device'), findsNothing);
  });

  testWidgets('shows download progress, then the ready button once complete', (tester) async {
    final controller = StreamController<ModelDownloadStatus>();
    final summarizer = _FakeSummarizer(
      available: false,
      platformInfo: const LocalAiPlatformInfo(
        backend: LocalAiBackend.androidMlKitGenAi,
        platform: 'android',
        apiName: 'ML Kit GenAI',
        supportsToolCalling: false,
        supportsModelDownload: true,
        supportsPlayStoreRedirect: false,
        isConfigured: true,
      ),
      modelStatus: ModelFeatureStatus.downloadable,
      downloadController: controller,
    );

    await tester.pumpWidget(_harness(summarizer));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Download model'));
    await tester.pump();

    expect(find.text('Downloading the model…'), findsOneWidget);

    controller.add(
      const ModelDownloadStatus(
        type: ModelDownloadStatusType.progress,
        totalBytesDownloaded: 5 * 1024 * 1024,
      ),
    );
    await tester.pump();

    expect(find.textContaining('5.0 MB so far'), findsOneWidget);

    controller.add(const ModelDownloadStatus(type: ModelDownloadStatusType.completed));
    await tester.pumpAndSettle();

    expect(find.text('Summarize on-device'), findsOneWidget);
    await controller.close();
  });

  testWidgets('resumes observing a download already in progress on open', (tester) async {
    final controller = StreamController<ModelDownloadStatus>();
    final summarizer = _FakeSummarizer(
      available: false,
      platformInfo: const LocalAiPlatformInfo(
        backend: LocalAiBackend.androidMlKitGenAi,
        platform: 'android',
        apiName: 'ML Kit GenAI',
        supportsToolCalling: false,
        supportsModelDownload: true,
        supportsPlayStoreRedirect: false,
        isConfigured: true,
      ),
      modelStatus: ModelFeatureStatus.downloading,
      downloadController: controller,
    );

    // Not pumpAndSettle: the downloading state renders an indeterminate
    // spinner, which schedules a new frame forever and never "settles".
    await tester.pumpWidget(_harness(summarizer));
    await tester.pump();
    await tester.pump();

    expect(find.text('Downloading the model…'), findsOneWidget);
    expect(find.text('Download model'), findsNothing);
    await controller.close();
  });

  testWidgets('shows a loading state while summarizing, then the result', (tester) async {
    final pending = Completer<String>();
    final summarizer = _FakeSummarizer(pendingSummary: pending);

    await tester.pumpWidget(_harness(summarizer));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Summarize on-device'));
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(summarizer.lastPrompt, 'Source text to condense.');

    pending.complete('A concise, on-device summary.');
    await tester.pumpAndSettle();

    expect(find.text('A concise, on-device summary.'), findsOneWidget);
  });

  testWidgets('tracks "summarizer used" on success, not before', (tester) async {
    final analytics = _RecordingAnalytics();
    final summarizer = _FakeSummarizer(summarizeError: null);

    await tester.pumpWidget(_harness(summarizer, analytics: analytics));
    await tester.pumpAndSettle();

    expect(analytics.events, isEmpty);

    await tester.tap(find.text('Summarize on-device'));
    await tester.pumpAndSettle();

    expect(analytics.events, ['summarizer used']);
  });

  testWidgets('does not track "summarizer used" when summarizing fails', (tester) async {
    final analytics = _RecordingAnalytics();
    final summarizer = _FakeSummarizer(summarizeError: Exception('boom'));

    await tester.pumpWidget(_harness(summarizer, analytics: analytics));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Summarize on-device'));
    await tester.pumpAndSettle();

    expect(analytics.events, isEmpty);
  });

  testWidgets('shows a readable error and lets the visitor retry', (tester) async {
    final summarizer = _FakeSummarizer(summarizeError: Exception('boom'));

    await tester.pumpWidget(_harness(summarizer));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Summarize on-device'));
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong summarizing on-device.'), findsOneWidget);

    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();

    expect(find.text('Summarize on-device'), findsOneWidget);
  });

  testWidgets('never falls back to the network when unavailable', (tester) async {
    // The summarizer's summarize() must never be called if isAvailable() is
    // false — mobile/CLAUDE.md: never silently fall back to the network.
    final summarizer = _FakeSummarizer(available: false);

    await tester.pumpWidget(_harness(summarizer));
    await tester.pumpAndSettle();

    expect(summarizer.lastPrompt, isNull);
  });
}

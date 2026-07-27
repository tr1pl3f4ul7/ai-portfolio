import 'dart:async';
import 'dart:convert';

import 'package:ai_portfolio/ai/summarizer.dart';
import 'package:ai_portfolio/api/client.dart';
import 'package:ai_portfolio/screens/summarizer_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _FakeSummarizer implements OnDeviceSummarizer {
  final bool available;
  final String reason;
  final Object? error;
  Completer<String>? pending;
  String? lastPrompt;

  _FakeSummarizer({
    this.available = true,
    this.reason = 'unavailable',
    this.error,
    this.pending,
  });

  @override
  Future<bool> isAvailable() async => available;

  @override
  Future<String> availabilityReason() async => reason;

  @override
  Future<String> summarize(String text) {
    lastPrompt = text;
    if (pending != null) return pending!.future;
    if (error != null) return Future.error(error!);
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

void main() {
  testWidgets('shows an honest disabled state when the model is unavailable', (tester) async {
    final summarizer = _FakeSummarizer(available: false, reason: 'No on-device model on this device.');

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: SummarizerScreen(apiClient: _client(), summarizer: summarizer)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No on-device model on this device.'), findsOneWidget);
    expect(find.text('Summarize on-device'), findsNothing);
  });

  testWidgets('shows a loading state while summarizing, then the result', (tester) async {
    final pending = Completer<String>();
    final summarizer = _FakeSummarizer(pending: pending);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: SummarizerScreen(apiClient: _client(), summarizer: summarizer)),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Summarize on-device'));
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(summarizer.lastPrompt, 'Source text to condense.');

    pending.complete('A concise, on-device summary.');
    await tester.pumpAndSettle();

    expect(find.text('A concise, on-device summary.'), findsOneWidget);
  });

  testWidgets('shows a readable error and lets the visitor retry', (tester) async {
    final summarizer = _FakeSummarizer(error: Exception('boom'));

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: SummarizerScreen(apiClient: _client(), summarizer: summarizer)),
      ),
    );
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

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: SummarizerScreen(apiClient: _client(), summarizer: summarizer)),
      ),
    );
    await tester.pumpAndSettle();

    expect(summarizer.lastPrompt, isNull);
  });
}

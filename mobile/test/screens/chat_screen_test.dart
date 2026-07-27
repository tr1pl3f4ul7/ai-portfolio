import 'dart:convert';

import 'package:ai_portfolio/analytics.dart';
import 'package:ai_portfolio/api/client.dart';
import 'package:ai_portfolio/screens/chat_screen.dart';
import 'package:flutter/material.dart';
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

void main() {
  testWidgets('renders suggestion chips from fetched content', (tester) async {
    final client = ApiClient(
      httpClient: MockClient((request) async {
        if (request.url.path.contains('/content/ask')) {
          return http.Response(
            jsonEncode({
              'label': 'ask',
              'heading': 'two of those layers',
              'description': 'Retrieves then generates.',
              'suggestions': ["What's the hardest thing you've built?"],
            }),
            200,
          );
        }
        return http.Response('not found', 404);
      }),
    );

    await tester.pumpWidget(MaterialApp(home: Scaffold(body: ChatScreen(apiClient: client))));
    await tester.pumpAndSettle();

    expect(find.text("What's the hardest thing you've built?"), findsOneWidget);
  });

  testWidgets('tapping a suggestion sends it and shows the answer', (tester) async {
    final client = ApiClient(
      httpClient: MockClient((request) async {
        if (request.url.path.contains('/content/ask')) {
          return http.Response(
            jsonEncode({
              'label': 'ask',
              'heading': 'h',
              'description': 'd',
              'suggestions': ['Do you have security experience?'],
            }),
            200,
          );
        }
        return http.Response(
          jsonEncode({'answer': 'Yes.', 'sources': []}),
          200,
        );
      }),
    );

    await tester.pumpWidget(MaterialApp(home: Scaffold(body: ChatScreen(apiClient: client))));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Do you have security experience?'));
    await tester.pumpAndSettle();

    expect(find.text('Yes.'), findsOneWidget);
  });

  testWidgets('tracks "chat used" on a successful exchange, not before', (tester) async {
    final analytics = _RecordingAnalytics();
    final client = ApiClient(
      httpClient: MockClient((request) async {
        if (request.url.path.contains('/content/ask')) {
          return http.Response(
            jsonEncode({
              'label': 'ask',
              'heading': 'h',
              'description': 'd',
              'suggestions': ['Do you have security experience?'],
            }),
            200,
          );
        }
        return http.Response(jsonEncode({'answer': 'Yes.', 'sources': []}), 200);
      }),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ChatScreen(apiClient: client, analytics: analytics)),
      ),
    );
    await tester.pumpAndSettle();

    expect(analytics.events, isEmpty);

    await tester.tap(find.text('Do you have security experience?'));
    await tester.pumpAndSettle();

    expect(analytics.events, ['chat used']);
  });

  testWidgets('shows the daily-limit message on a 429', (tester) async {
    final client = ApiClient(
      httpClient: MockClient((request) async {
        if (request.url.path.contains('/content/ask')) {
          return http.Response(
            jsonEncode({
              'label': 'ask',
              'heading': 'h',
              'description': 'd',
              'suggestions': <String>[],
            }),
            200,
          );
        }
        return http.Response(jsonEncode({'detail': 'rate limited'}), 429);
      }),
    );

    await tester.pumpWidget(MaterialApp(home: Scaffold(body: ChatScreen(apiClient: client))));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'hi');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(find.textContaining('Daily limit'), findsOneWidget);
  });
}

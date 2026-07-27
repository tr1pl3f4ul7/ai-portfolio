import 'dart:convert';

import 'package:ai_portfolio/api/client.dart';
import 'package:ai_portfolio/screens/contact_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

ApiClient _client(Future<http.Response> Function(http.Request) onSubmit) {
  return ApiClient(
    httpClient: MockClient((request) async {
      if (request.url.path.contains('/content/contact')) {
        return http.Response(
          jsonEncode({'label': 'contact', 'heading': 'say hello', 'description': 'Goes to triage.'}),
          200,
        );
      }
      return onSubmit(request);
    }),
  );
}

void main() {
  testWidgets('rejects submission until required fields are filled', (tester) async {
    final client = _client(
      (request) async => http.Response(jsonEncode({'received': true, 'reference': 'x'}), 200),
    );

    await tester.pumpWidget(MaterialApp(home: Scaffold(body: ContactScreen(apiClient: client))));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Send'));
    await tester.pump();

    expect(find.text('Required'), findsWidgets);
  });

  testWidgets('submits the form and shows the reference on success', (tester) async {
    final client = _client(
      (request) async => http.Response(
        jsonEncode({'received': true, 'reference': 'abc123'}),
        200,
      ),
    );

    await tester.pumpWidget(MaterialApp(home: Scaffold(body: ContactScreen(apiClient: client))));
    await tester.pumpAndSettle();

    await tester.enterText(find.widgetWithText(TextFormField, 'Name'), 'Dana');
    await tester.enterText(find.widgetWithText(TextFormField, 'Email'), 'dana@example.com');
    await tester.enterText(find.widgetWithText(TextFormField, 'Message'), 'Hello.');
    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();

    expect(find.text('Message sent.'), findsOneWidget);
    expect(find.textContaining('abc123'), findsOneWidget);
  });

  testWidgets('shows a readable error and lets the visitor retry', (tester) async {
    final client = _client(
      (request) async => http.Response(jsonEncode({'detail': 'boom'}), 503),
    );

    await tester.pumpWidget(MaterialApp(home: Scaffold(body: ContactScreen(apiClient: client))));
    await tester.pumpAndSettle();

    await tester.enterText(find.widgetWithText(TextFormField, 'Name'), 'Dana');
    await tester.enterText(find.widgetWithText(TextFormField, 'Email'), 'dana@example.com');
    await tester.enterText(find.widgetWithText(TextFormField, 'Message'), 'Hello.');
    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();

    expect(find.text('boom'), findsOneWidget);
    expect(find.text('Send'), findsOneWidget);
  });
}

import 'dart:convert';

import 'package:ai_portfolio/api/client.dart';
import 'package:ai_portfolio/screens/summarizer_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('renders fetched copy and an honestly-disabled summarize button', (tester) async {
    final client = ApiClient(
      httpClient: MockClient(
        (request) async => http.Response(
          jsonEncode({
            'label': 'summarizer',
            'heading': 'a real summary, generated on your phone',
            'description': 'Condenses on-device.',
            'source_text': 'Placeholder source text.',
          }),
          200,
        ),
      ),
    );

    await tester.pumpWidget(MaterialApp(home: Scaffold(body: SummarizerScreen(apiClient: client))));
    await tester.pumpAndSettle();

    expect(find.text('a real summary, generated on your phone'), findsOneWidget);
    expect(find.text('Placeholder source text.'), findsOneWidget);

    final button = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(button.onPressed, isNull);
  });
}

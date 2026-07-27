import 'dart:convert';

import 'package:ai_portfolio/api/client.dart';
import 'package:ai_portfolio/screens/projects_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// `http.Response(String, ...)` picks its encoding from the `Content-Type`
/// header, defaulting to UTF-8 for `application/json` (matching what
/// FastAPI actually sends) but to Latin-1 with no header at all — which
/// throws on the en dash in "2022–2026" below. Set the header explicitly so
/// this fixture behaves like a real response.
http.Response _json(Object body) => http.Response(
  jsonEncode(body),
  200,
  headers: {'content-type': 'application/json'},
);

void main() {
  testWidgets('renders one card per project', (tester) async {
    final client = ApiClient(
      httpClient: MockClient(
        (request) async => _json({
          'label': 'selected work',
          'heading': 'things that had to not break',
          'items': [
            {
              'company': 'propertyme',
              'year': '2022–2026',
              'name': 'PropertyMe',
              'note': 'Flutter app for owners.',
            },
            {
              'company': 'gruntify',
              'year': '2021',
              'name': 'Gruntify',
              'note': 'Android GIS platform.',
            },
          ],
        }),
      ),
    );

    await tester.pumpWidget(MaterialApp(home: Scaffold(body: ProjectsScreen(apiClient: client))));
    await tester.pumpAndSettle();

    expect(find.text('things that had to not break'), findsOneWidget);
    expect(find.text('PropertyMe'), findsOneWidget);
    expect(find.text('Gruntify'), findsOneWidget);
    expect(find.textContaining('PROPERTYME'), findsOneWidget);
  });
}

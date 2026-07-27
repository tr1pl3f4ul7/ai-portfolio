import 'dart:convert';

import 'package:ai_portfolio/api/client.dart';
import 'package:ai_portfolio/screens/home_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

ApiClient _clientReturning(Map<String, dynamic> profile) {
  return ApiClient(
    httpClient: MockClient((request) async => http.Response(jsonEncode(profile), 200)),
  );
}

void main() {
  testWidgets('renders the fetched hero copy', (tester) async {
    final client = _clientReturning({
      'name': 'ljuben vassilev',
      'location': 'brisbane, australia',
      'tagline': 'Ten years of mobile.',
    });

    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: HomeScreen(apiClient: client, onNavigate: (_) {}))),
    );
    await tester.pumpAndSettle();

    expect(find.text('ljuben vassilev'), findsOneWidget);
    expect(find.text('Ten years of mobile.'), findsOneWidget);
  });

  testWidgets('tapping a dashboard tile navigates to that tab', (tester) async {
    final client = _clientReturning({
      'name': 'ljuben vassilev',
      'location': 'brisbane, australia',
      'tagline': 'Ten years of mobile.',
    });
    int? navigatedTo;

    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: HomeScreen(apiClient: client, onNavigate: (i) => navigatedTo = i))),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Projects'));
    await tester.pump();

    expect(navigatedTo, 2);
  });

  testWidgets('shows a readable message when the fetch fails', (tester) async {
    final client = ApiClient(
      httpClient: MockClient((request) async => http.Response('', 503)),
    );

    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: HomeScreen(apiClient: client, onNavigate: (_) {}))),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('unavailable'), findsOneWidget);
  });
}

/// Tests for the backend client.
///
/// `http.Client` is stubbed with `http.MockClient` throughout — no test in
/// this file touches the network. What matters here is the request shape
/// (the contract with backend/app/schemas.py, mirrored in web/test/api.test.ts)
/// and that every failure becomes a message a visitor can read.
library;

import 'dart:convert';

import 'package:ai_portfolio/api/client.dart';
import 'package:ai_portfolio/api/models.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Sets `Content-Type: application/json` so `http.Response` decodes as UTF-8
/// (its default without a header is Latin-1, matching production only by
/// accident) — see projects_screen_test.dart's `_json` for where this bit.
http.Response _json(Object body, {int status = 200, Map<String, String>? headers}) {
  return http.Response(
    jsonEncode(body),
    status,
    headers: {'content-type': 'application/json', ...?headers},
  );
}

void main() {
  group('askQuestion', () {
    test('posts the question as JSON to /chat', () async {
      late http.Request captured;
      final client = ApiClient(
        httpClient: MockClient((request) async {
          captured = request;
          return _json({'answer': 'Yes.', 'sources': []});
        }),
      );

      await client.askQuestion('Does he have security experience?');

      expect(captured.url.path, contains('/chat'));
      expect(captured.method, 'POST');
      expect(captured.headers['Content-Type'], 'application/json');
      expect(jsonDecode(captured.body), {'question': 'Does he have security experience?'});
    });

    test('returns the answer and its sources', () async {
      final client = ApiClient(
        httpClient: MockClient(
          (request) async => _json({
            'answer': 'He works at AI Talent.',
            'sources': [
              {'document': 'experience.md', 'section': 'Software Engineer at AI Talent'},
            ],
          }),
        ),
      );

      final response = await client.askQuestion('Who does he work for?');

      expect(response.answer, 'He works at AI Talent.');
      expect(response.sources, hasLength(1));
      expect(response.sources.first.document, 'experience.md');
    });
  });

  group('submitContact', () {
    test('posts every field to /contact', () async {
      late http.Request captured;
      final client = ApiClient(
        httpClient: MockClient((request) async {
          captured = request;
          return _json({'received': true, 'reference': 'abc123'});
        }),
      );

      await client.submitContact(
        const ContactRequest(name: 'Dana', email: 'dana@example.com', message: 'Hello.'),
      );

      expect(captured.url.path, contains('/contact'));
      expect(jsonDecode(captured.body), {
        'name': 'Dana',
        'email': 'dana@example.com',
        'message': 'Hello.',
      });
    });

    test('returns the reference', () async {
      final client = ApiClient(
        httpClient: MockClient(
          (request) async => _json({'received': true, 'reference': '2418ab6cf5e0'}),
        ),
      );

      final response = await client.submitContact(
        const ContactRequest(name: 'D', email: 'd@e.com', message: 'hi'),
      );

      expect(response.reference, '2418ab6cf5e0');
    });
  });

  group('content endpoints', () {
    test('fetches profile with GET, no body', () async {
      late http.Request captured;
      final client = ApiClient(
        httpClient: MockClient((request) async {
          captured = request;
          return _json({
            'name': 'ljuben vassilev',
            'location': 'brisbane, australia',
            'tagline': '...',
          });
        }),
      );

      final profile = await client.getProfile();

      expect(captured.url.path, contains('/content/profile'));
      expect(captured.method, 'GET');
      expect(profile.name, 'ljuben vassilev');
    });

    test('fetches summarizer content, including the mobile-only source text', () async {
      final client = ApiClient(
        httpClient: MockClient(
          (request) async => _json({
            'label': 'summarizer',
            'heading': 'h',
            'description': 'd',
            'source_text': 'condense this',
          }),
        ),
      );

      final content = await client.getSummarizerContent();

      expect(content.sourceText, 'condense this');
    });

    test('fetches ask content, including the suggestion chips', () async {
      final client = ApiClient(
        httpClient: MockClient(
          (request) async => _json({
            'label': 'ask',
            'heading': 'h',
            'description': 'd',
            'suggestions': ['Q1?', 'Q2?'],
          }),
        ),
      );

      final content = await client.getAskContent();

      expect(content.suggestions, ['Q1?', 'Q2?']);
    });

    test('fetches the project cards from /content/projects', () async {
      late http.Request captured;
      final client = ApiClient(
        httpClient: MockClient((request) async {
          captured = request;
          return _json({
            'label': 'selected work',
            'heading': 'h',
            'items': [
              {'company': 'acme', 'year': '2020', 'name': 'Widget', 'note': 'note'},
            ],
          });
        }),
      );

      final projects = await client.getProjects();

      expect(captured.url.path, contains('/content/projects'));
      expect(projects.items, hasLength(1));
    });
  });

  group('failures become readable messages', () {
    test('explains a daily limit rather than showing 429', () async {
      final client = ApiClient(
        httpClient: MockClient(
          (request) async => _json({'detail': 'per-ip limit reached'}, status: 429),
        ),
      );

      await expectLater(
        client.askQuestion('hi'),
        throwsA(
          isA<ApiException>()
              .having((e) => e.status, 'status', 429)
              .having((e) => e.message, 'message', contains('Daily limit')),
        ),
      );
    });

    test('carries Retry-After through so the UI could use it', () async {
      final client = ApiClient(
        httpClient: MockClient(
          (request) async => _json(
            {'detail': 'rate limited'},
            status: 429,
            headers: {'retry-after': '3600'},
          ),
        ),
      );

      await expectLater(
        client.askQuestion('hi'),
        throwsA(isA<ApiException>().having((e) => e.retryAfterSeconds, 'retryAfterSeconds', 3600)),
      );
    });

    test("surfaces the backend's own detail on 503, which says what is down", () async {
      final client = ApiClient(
        httpClient: MockClient(
          (request) async =>
              _json({'detail': 'vector store missing at /opt/.../vectors.db'}, status: 503),
        ),
      );

      await expectLater(
        client.askQuestion('hi'),
        throwsA(
          isA<ApiException>()
              .having((e) => e.status, 'status', 503)
              .having((e) => e.message, 'message', contains('vector store missing')),
        ),
      );
    });

    test('does not show raw field errors from a 422', () async {
      final client = ApiClient(
        httpClient: MockClient(
          (request) async => _json({
            'detail': [
              {'loc': ['body', 'question']},
            ],
          }, status: 422),
        ),
      );

      await expectLater(
        client.askQuestion(''),
        throwsA(
          isA<ApiException>()
              .having((e) => e.message, 'message', isNot(contains('loc')))
              .having((e) => e.message, 'message', contains('check the fields')),
        ),
      );
    });

    test('reports a network failure as a connection problem', () async {
      final client = ApiClient(
        httpClient: MockClient((request) async => throw const SocketExceptionStub()),
      );

      await expectLater(
        client.askQuestion('hi'),
        throwsA(
          isA<ApiException>()
              .having((e) => e.message, 'message', contains("Couldn't reach the server")),
        ),
      );
    });

    test('survives an error body that is not JSON', () async {
      final client = ApiClient(
        httpClient: MockClient(
          (request) async => http.Response('<html>502 Bad Gateway</html>', 502),
        ),
      );

      await expectLater(
        client.askQuestion('hi'),
        throwsA(isA<ApiException>().having((e) => e.status, 'status', 502)),
      );
    });
  });
}

/// Stand-in for the kind of low-level error `http` throws on a real
/// connection failure (a `SocketException` isn't constructible directly in
/// a plain Dart test without `dart:io` socket setup) — any thrown object
/// that isn't a `TimeoutException` exercises the same catch branch.
class SocketExceptionStub implements Exception {
  const SocketExceptionStub();
}

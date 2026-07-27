/// Backend client. Mirrors `web/src/api.ts`'s failure handling so a visitor
/// gets the same readable message regardless of which client they're on.
library;

import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;

import 'config.dart';
import 'models.dart';

/// Anything that stopped a request completing, carrying a message written
/// for a visitor to read rather than a status code to decode.
class ApiException implements Exception {
  final String message;
  final int? status;
  final int? retryAfterSeconds;

  const ApiException(this.message, {this.status, this.retryAfterSeconds});

  @override
  String toString() => message;
}

String _describeStatus(int status, String? detail) {
  switch (status) {
    case 422:
      // The backend validated and refused. Its detail is about field shape,
      // not something a visitor can act on, so say the useful thing instead.
      return "That didn't look right — check the fields and try again.";
    case 429:
      return 'Daily limit reached. This runs on a small budget — try again tomorrow.';
    case 503:
      // Honest rather than reassuring: something downstream is genuinely down.
      return detail ?? 'That service is temporarily unavailable.';
    default:
      return detail ?? 'Something went wrong ($status).';
  }
}

String? _readDetail(http.Response response) {
  try {
    final body = jsonDecode(response.body);
    if (body is Map<String, dynamic> && body['detail'] is String) {
      return body['detail'] as String;
    }
    return null;
  } catch (_) {
    return null;
  }
}

/// Talks to the backend and the edge Worker. One instance per app — see
/// `main.dart` — so tests can substitute an `http.Client` that never hits
/// the network.
class ApiClient {
  final http.Client _http;

  ApiClient({http.Client? httpClient}) : _http = httpClient ?? http.Client();

  Future<T> _get<T>(
    String baseUrl,
    String path,
    T Function(Map<String, dynamic>) fromJson,
  ) => _request(baseUrl, path, fromJson, (uri) => _http.get(uri));

  Future<T> _post<T>(
    String baseUrl,
    String path,
    Map<String, dynamic> body,
    T Function(Map<String, dynamic>) fromJson,
  ) => _request(
    baseUrl,
    path,
    fromJson,
    (uri) => _http.post(
      uri,
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    ),
  );

  Future<T> _request<T>(
    String baseUrl,
    String path,
    T Function(Map<String, dynamic>) fromJson,
    Future<http.Response> Function(Uri uri) send,
  ) async {
    final uri = Uri.parse('$baseUrl$path');
    http.Response response;
    try {
      response = await send(uri).timeout(requestTimeout);
    } catch (cause) {
      final timedOut = cause is TimeoutException;
      throw ApiException(
        timedOut
            ? 'That took too long. Try again.'
            : "Couldn't reach the server. Check your connection.",
      );
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final retryAfter = int.tryParse(
        response.headers['retry-after'] ?? '',
      );
      throw ApiException(
        _describeStatus(response.statusCode, _readDetail(response)),
        status: response.statusCode,
        retryAfterSeconds: (retryAfter != null && retryAfter > 0)
            ? retryAfter
            : null,
      );
    }

    return fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// Ask the RAG chatbot. Retrieval on the VM, generation at the Claude API.
  Future<ChatResponse> askQuestion(String question) => _post(
    apiBaseUrl,
    '/chat',
    {'question': question},
    ChatResponse.fromJson,
  );

  /// Submit the contact form. Goes to the edge Worker's own domain, not the
  /// backend directly — see `config.dart`.
  Future<ContactResponse> submitContact(ContactRequest submission) => _post(
    contactBaseUrl,
    '/contact',
    submission.toJson(),
    ContactResponse.fromJson,
  );

  /// Hero copy — web's hero and mobile's Home tab share this.
  Future<ProfileContent> getProfile() =>
      _get(apiBaseUrl, '/content/profile', ProfileContent.fromJson);

  /// Mobile's on-device summarizer section copy. Mobile-only.
  Future<SummarizerContent> getSummarizerContent() =>
      _get(apiBaseUrl, '/content/summarizer', SummarizerContent.fromJson);

  /// Chat section copy, shared by web and mobile.
  Future<AskContent> getAskContent() =>
      _get(apiBaseUrl, '/content/ask', AskContent.fromJson);

  /// Contact section copy, shared by web and mobile.
  Future<ContactContent> getContactContent() =>
      _get(apiBaseUrl, '/content/contact', SectionContent.fromJson);

  /// The project cards — mobile's Projects tab, shared with web's grid.
  Future<ProjectsContent> getProjects() =>
      _get(apiBaseUrl, '/content/projects', ProjectsContent.fromJson);

  void close() => _http.close();
}

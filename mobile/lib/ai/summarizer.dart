/// On-device summarization. Mirrors web/CLAUDE.md's project-finder rule for
/// this project's other on-device surface: never trust an API's mere
/// presence, check availability by actually trying it, and never silently
/// fall back to the network — that would erase the distinction this screen
/// exists to demonstrate (mobile/CLAUDE.md).
library;

import 'package:flutter_local_ai/flutter_local_ai.dart';

/// Thin wrapper over `flutter_local_ai` so screens depend on this interface,
/// not the plugin directly — widget tests substitute a fake implementation
/// rather than exercising a real platform channel.
abstract class OnDeviceSummarizer {
  Future<bool> isAvailable();
  Future<String> availabilityReason();
  Future<String> summarize(String text);
}

class FlutterLocalAiSummarizer implements OnDeviceSummarizer {
  final FlutterLocalAi _engine;
  bool _initialized = false;

  FlutterLocalAiSummarizer({FlutterLocalAi? engine})
    : _engine = engine ?? FlutterLocalAi();

  @override
  Future<bool> isAvailable() => _engine.isAvailable();

  @override
  Future<String> availabilityReason() => _engine.availabilityReason();

  @override
  Future<String> summarize(String text) async {
    if (!_initialized) {
      await _engine.initialize(
        instructions:
            'Summarize the given text in two or three plain sentences. '
            'Only use information present in the text.',
      );
      _initialized = true;
    }
    final response = await _engine.generateText(
      prompt: text,
      config: const GenerationConfig(maxTokens: 150),
    );
    return response.text;
  }
}

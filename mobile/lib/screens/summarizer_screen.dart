import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../theme/tokens.dart';
import 'async_content.dart';

/// On-device summarizer. Real inference (`flutter_local_ai`) is Step 7.2 —
/// this screen fetches its section copy and shows an honest disabled state
/// rather than a fake or silently network-backed result (mobile/CLAUDE.md:
/// never silently fall back to the network for an on-device feature).
class SummarizerScreen extends StatelessWidget {
  final ApiClient apiClient;

  const SummarizerScreen({super.key, required this.apiClient});

  @override
  Widget build(BuildContext context) {
    return AsyncContent<SummarizerContent>(
      fetch: apiClient.getSummarizerContent,
      builder: (context, content) => ListView(
        padding: const EdgeInsets.all(Tokens.space5),
        children: [
          Text(
            content.label.toUpperCase(),
            style: const TextStyle(
              color: Tokens.signal,
              fontSize: Tokens.sNeg1,
              letterSpacing: 1.5,
            ),
          ),
          const SizedBox(height: Tokens.space2),
          Text(
            content.heading,
            style: const TextStyle(
              color: Tokens.ink,
              fontSize: Tokens.s3,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: Tokens.space3),
          Text(
            content.description,
            style: const TextStyle(color: Tokens.inkDim, height: 1.4),
          ),
          const SizedBox(height: Tokens.space6),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(Tokens.space4),
              child: Text(
                content.sourceText,
                style: const TextStyle(color: Tokens.inkDim, height: 1.4),
              ),
            ),
          ),
          const SizedBox(height: Tokens.space5),
          FilledButton.icon(
            onPressed: null,
            icon: const Icon(Icons.auto_awesome_outlined),
            label: const Text('Summarize on-device — coming in Step 7.2'),
          ),
        ],
      ),
    );
  }
}

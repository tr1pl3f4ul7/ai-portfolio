import 'package:flutter/material.dart';

import '../ai/summarizer.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../theme/tokens.dart';
import 'async_content.dart';

/// On-device summarizer. Fetches its section copy from the backend, then
/// drives `flutter_local_ai` through three states — availability check,
/// summarizing, result/error — never falling back to a network call if the
/// on-device model isn't there (mobile/CLAUDE.md).
class SummarizerScreen extends StatelessWidget {
  final ApiClient apiClient;
  final OnDeviceSummarizer? summarizer;

  const SummarizerScreen({super.key, required this.apiClient, this.summarizer});

  @override
  Widget build(BuildContext context) {
    return AsyncContent<SummarizerContent>(
      fetch: apiClient.getSummarizerContent,
      builder: (context, content) => _SummarizerBody(
        content: content,
        summarizer: summarizer ?? FlutterLocalAiSummarizer(),
      ),
    );
  }
}

enum _Status { checkingAvailability, unavailable, ready, summarizing, result, error }

class _SummarizerBody extends StatefulWidget {
  final SummarizerContent content;
  final OnDeviceSummarizer summarizer;

  const _SummarizerBody({required this.content, required this.summarizer});

  @override
  State<_SummarizerBody> createState() => _SummarizerBodyState();
}

class _SummarizerBodyState extends State<_SummarizerBody> {
  _Status _status = _Status.checkingAvailability;
  String? _unavailableReason;
  String? _summary;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _checkAvailability();
  }

  Future<void> _checkAvailability() async {
    final available = await widget.summarizer.isAvailable();
    if (!mounted) return;
    if (!available) {
      final reason = await widget.summarizer.availabilityReason();
      if (!mounted) return;
      setState(() {
        _status = _Status.unavailable;
        _unavailableReason = reason;
      });
      return;
    }
    setState(() => _status = _Status.ready);
  }

  Future<void> _summarize() async {
    setState(() => _status = _Status.summarizing);
    try {
      final summary = await widget.summarizer.summarize(widget.content.sourceText);
      if (!mounted) return;
      setState(() {
        _status = _Status.result;
        _summary = summary;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _status = _Status.error;
        _errorMessage = 'Something went wrong summarizing on-device.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(Tokens.space5),
      children: [
        Text(
          widget.content.label.toUpperCase(),
          style: const TextStyle(
            color: Tokens.signal,
            fontSize: Tokens.sNeg1,
            letterSpacing: 1.5,
          ),
        ),
        const SizedBox(height: Tokens.space2),
        Text(
          widget.content.heading,
          style: const TextStyle(
            color: Tokens.ink,
            fontSize: Tokens.s3,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: Tokens.space3),
        Text(
          widget.content.description,
          style: const TextStyle(color: Tokens.inkDim, height: 1.4),
        ),
        const SizedBox(height: Tokens.space6),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(Tokens.space4),
            child: Text(
              widget.content.sourceText,
              style: const TextStyle(color: Tokens.inkDim, height: 1.4),
            ),
          ),
        ),
        const SizedBox(height: Tokens.space5),
        _buildStatusSection(),
      ],
    );
  }

  Widget _buildStatusSection() {
    switch (_status) {
      case _Status.checkingAvailability:
        return const Center(child: CircularProgressIndicator());

      case _Status.unavailable:
        return _Message(
          icon: Icons.info_outline,
          color: Tokens.inkDim,
          text: _unavailableReason ?? 'On-device summarization is not available on this device.',
        );

      case _Status.ready:
        return FilledButton.icon(
          onPressed: _summarize,
          icon: const Icon(Icons.auto_awesome_outlined),
          label: const Text('Summarize on-device'),
        );

      case _Status.summarizing:
        return const FilledButton(
          onPressed: null,
          child: SizedBox(
            width: 16,
            height: 16,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        );

      case _Status.result:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'SUMMARY',
              style: TextStyle(
                color: Tokens.signal,
                fontSize: Tokens.sNeg1,
                letterSpacing: 1.5,
              ),
            ),
            const SizedBox(height: Tokens.space2),
            Text(_summary ?? '', style: const TextStyle(color: Tokens.ink, height: 1.4)),
            const SizedBox(height: Tokens.space4),
            OutlinedButton(
              onPressed: () => setState(() => _status = _Status.ready),
              child: const Text('Summarize again'),
            ),
          ],
        );

      case _Status.error:
        return _Message(
          icon: Icons.error_outline,
          color: Tokens.danger,
          text: _errorMessage ?? 'Something went wrong.',
          action: OutlinedButton(
            onPressed: () => setState(() => _status = _Status.ready),
            child: const Text('Try again'),
          ),
        );
    }
  }
}

class _Message extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String text;
  final Widget? action;

  const _Message({required this.icon, required this.color, required this.text, this.action});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(width: Tokens.space2),
            Expanded(child: Text(text, style: TextStyle(color: color))),
          ],
        ),
        if (action != null) ...[const SizedBox(height: Tokens.space3), action!],
      ],
    );
  }
}

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_local_ai/flutter_local_ai.dart';

import '../ai/summarizer.dart';
import '../analytics.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../theme/tokens.dart';
import 'async_content.dart';

/// On-device summarizer. Fetches its section copy from the backend, then
/// drives `flutter_local_ai` through every real state a device can be in:
/// unsupported, supported-but-needs-a-download (Android's Gemini Nano),
/// downloading, and ready — never falling back to a network call at any
/// point (mobile/CLAUDE.md).
class SummarizerScreen extends StatelessWidget {
  final ApiClient apiClient;
  final OnDeviceSummarizer? summarizer;
  final Analytics? analytics;

  const SummarizerScreen({
    super.key,
    required this.apiClient,
    this.summarizer,
    this.analytics,
  });

  @override
  Widget build(BuildContext context) {
    return AsyncContent<SummarizerContent>(
      fetch: apiClient.getSummarizerContent,
      builder: (context, content) => _SummarizerBody(
        content: content,
        summarizer: summarizer ?? FlutterLocalAiSummarizer(),
        analytics: analytics ?? NoOpAnalytics(),
      ),
    );
  }
}

enum _Status {
  checkingAvailability,
  unavailable,
  downloadable,
  downloading,
  ready,
  summarizing,
  result,
  error,
}

class _SummarizerBody extends StatefulWidget {
  final SummarizerContent content;
  final OnDeviceSummarizer summarizer;
  final Analytics analytics;

  const _SummarizerBody({
    required this.content,
    required this.summarizer,
    required this.analytics,
  });

  @override
  State<_SummarizerBody> createState() => _SummarizerBodyState();
}

class _SummarizerBodyState extends State<_SummarizerBody> {
  _Status _status = _Status.checkingAvailability;
  LocalAiPlatformInfo? _platformInfo;
  String? _unavailableReason;
  int? _downloadedBytes;
  String? _summary;
  String? _errorMessage;
  StreamSubscription<ModelDownloadStatus>? _downloadSub;

  @override
  void initState() {
    super.initState();
    _checkAvailability();
  }

  @override
  void dispose() {
    _downloadSub?.cancel();
    super.dispose();
  }

  Future<void> _checkAvailability() async {
    final info = await widget.summarizer.getPlatformInfo();
    if (!mounted) return;
    _platformInfo = info;

    final available = await widget.summarizer.isAvailable();
    if (!mounted) return;
    if (available) {
      setState(() => _status = _Status.ready);
      return;
    }

    if (info.supportsModelDownload) {
      final modelStatus = await widget.summarizer.getModelStatus();
      if (!mounted) return;
      if (modelStatus == ModelFeatureStatus.downloadable) {
        setState(() => _status = _Status.downloadable);
        return;
      }
      if (modelStatus == ModelFeatureStatus.downloading) {
        _startDownload();
        return;
      }
    }

    final reason = await widget.summarizer.availabilityReason();
    if (!mounted) return;
    setState(() {
      _status = _Status.unavailable;
      _unavailableReason = reason;
    });
  }

  void _startDownload() {
    setState(() {
      _status = _Status.downloading;
      _downloadedBytes = null;
    });

    _downloadSub = widget.summarizer.downloadModel().listen(
      (status) {
        if (!mounted) return;
        switch (status.type) {
          case ModelDownloadStatusType.progress:
            setState(() => _downloadedBytes = status.totalBytesDownloaded);
          case ModelDownloadStatusType.completed:
            setState(() => _status = _Status.ready);
          case ModelDownloadStatusType.failed:
            setState(() {
              _status = _Status.unavailable;
              _unavailableReason = status.errorMessage ?? 'The model download failed.';
            });
          case ModelDownloadStatusType.started:
          case ModelDownloadStatusType.unknown:
            break;
        }
      },
      onError: (_) {
        if (!mounted) return;
        setState(() {
          _status = _Status.unavailable;
          _unavailableReason = 'The model download failed.';
        });
      },
    );
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
      widget.analytics.track('summarizer used');
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
          action: (_platformInfo?.supportsPlayStoreRedirect ?? false)
              ? OutlinedButton(
                  onPressed: () => widget.summarizer.openAICorePlayStore(),
                  child: const Text('Open Play Store'),
                )
              : null,
        );

      case _Status.downloadable:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'The on-device model needs a one-time download before it can run.',
              style: TextStyle(color: Tokens.inkDim, height: 1.4),
            ),
            const SizedBox(height: Tokens.space3),
            FilledButton.icon(
              onPressed: _startDownload,
              icon: const Icon(Icons.download_outlined),
              label: const Text('Download model'),
            ),
          ],
        );

      case _Status.downloading:
        return Row(
          children: [
            const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            const SizedBox(width: Tokens.space3),
            Expanded(
              child: Text(
                _downloadedBytes != null
                    ? 'Downloading the model — ${(_downloadedBytes! / (1024 * 1024)).toStringAsFixed(1)} MB so far…'
                    : 'Downloading the model…',
                style: const TextStyle(color: Tokens.inkDim),
              ),
            ),
          ],
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

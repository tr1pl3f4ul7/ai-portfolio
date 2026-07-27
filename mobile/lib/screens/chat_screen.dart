import 'package:flutter/material.dart';

import '../analytics.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../theme/tokens.dart';
import 'async_content.dart';

class ChatScreen extends StatelessWidget {
  final ApiClient apiClient;
  final Analytics? analytics;

  const ChatScreen({super.key, required this.apiClient, this.analytics});

  @override
  Widget build(BuildContext context) {
    return AsyncContent<AskContent>(
      fetch: apiClient.getAskContent,
      builder: (context, content) => _ChatBody(
        apiClient: apiClient,
        analytics: analytics ?? NoOpAnalytics(),
        content: content,
      ),
    );
  }
}

class _Exchange {
  final String question;
  final ChatResponse response;

  const _Exchange({required this.question, required this.response});
}

class _ChatBody extends StatefulWidget {
  final ApiClient apiClient;
  final Analytics analytics;
  final AskContent content;

  const _ChatBody({required this.apiClient, required this.analytics, required this.content});

  @override
  State<_ChatBody> createState() => _ChatBodyState();
}

class _ChatBodyState extends State<_ChatBody> {
  final _controller = TextEditingController();
  final List<_Exchange> _exchanges = [];
  bool _sending = false;
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _send([String? preset]) async {
    final question = (preset ?? _controller.text).trim();
    if (question.isEmpty || _sending) return;

    setState(() {
      _sending = true;
      _error = null;
    });
    _controller.clear();

    try {
      final response = await widget.apiClient.askQuestion(question);
      if (!mounted) return;
      setState(() => _exchanges.add(_Exchange(question: question, response: response)));
      widget.analytics.track('chat used');
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Something went wrong.');
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(Tokens.space5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            widget.content.heading,
            style: const TextStyle(
              color: Tokens.ink,
              fontSize: Tokens.s3,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: Tokens.space2),
          Text(
            widget.content.description,
            style: const TextStyle(color: Tokens.inkDim, height: 1.4),
          ),
          const SizedBox(height: Tokens.space4),
          Expanded(
            child: _exchanges.isEmpty
                ? _SuggestionList(
                    suggestions: widget.content.suggestions,
                    onPicked: _send,
                  )
                : ListView.builder(
                    itemCount: _exchanges.length,
                    itemBuilder: (context, index) =>
                        _ExchangeTile(exchange: _exchanges[index]),
                  ),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: Tokens.space3),
              child: Text(_error!, style: const TextStyle(color: Tokens.danger)),
            ),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _controller,
                  enabled: !_sending,
                  decoration: const InputDecoration(hintText: 'Ask about my work…'),
                  onSubmitted: (_) => _send(),
                ),
              ),
              const SizedBox(width: Tokens.space2),
              IconButton.filled(
                onPressed: _sending ? null : () => _send(),
                icon: _sending
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.send),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SuggestionList extends StatelessWidget {
  final List<String> suggestions;
  final ValueChanged<String> onPicked;

  const _SuggestionList({required this.suggestions, required this.onPicked});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: Tokens.space2,
      runSpacing: Tokens.space2,
      children: suggestions
          .map(
            (s) => ActionChip(
              label: Text(s),
              onPressed: () => onPicked(s),
            ),
          )
          .toList(),
    );
  }
}

class _ExchangeTile extends StatelessWidget {
  final _Exchange exchange;

  const _ExchangeTile({required this.exchange});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: Tokens.space4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            exchange.question,
            style: const TextStyle(color: Tokens.signal, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: Tokens.space2),
          Text(exchange.response.answer, style: const TextStyle(color: Tokens.ink, height: 1.4)),
          if (exchange.response.sources.isNotEmpty) ...[
            const SizedBox(height: Tokens.space2),
            ...exchange.response.sources.map(
              (s) => Text(
                '${s.document} · ${s.section}',
                style: const TextStyle(color: Tokens.inkFaint, fontSize: Tokens.sNeg1),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

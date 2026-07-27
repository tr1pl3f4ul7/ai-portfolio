import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme/tokens.dart';

/// Fetches once on mount and renders loading / error / data — every screen
/// in this app starts with a `GET /content/*` call, so this is the one place
/// that decides what "still loading" and "the fetch failed" look like.
class AsyncContent<T> extends StatefulWidget {
  final Future<T> Function() fetch;
  final Widget Function(BuildContext context, T data) builder;

  const AsyncContent({super.key, required this.fetch, required this.builder});

  @override
  State<AsyncContent<T>> createState() => _AsyncContentState<T>();
}

class _AsyncContentState<T> extends State<AsyncContent<T>> {
  late Future<T> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.fetch();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<T>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          final error = snapshot.error;
          final message = error is ApiException
              ? error.message
              : 'Content failed to load. Try again.';
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(Tokens.space5),
              child: Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Tokens.inkDim),
              ),
            ),
          );
        }
        return widget.builder(context, snapshot.data as T);
      },
    );
  }
}

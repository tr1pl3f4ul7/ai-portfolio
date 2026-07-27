import 'package:flutter/material.dart';

import '../ai/summarizer.dart';
import '../analytics.dart';
import '../api/client.dart';
import 'chat_screen.dart';
import 'contact_screen.dart';
import 'home_screen.dart';
import 'projects_screen.dart';
import 'summarizer_screen.dart';

const _screenNames = ['home', 'summarizer', 'projects', 'chat', 'contact'];

/// Bottom-navigation shell across the app's five screens (decision 58: the
/// full dashboard scope, not a lean summarizer-only app).
class AppShell extends StatefulWidget {
  final ApiClient apiClient;
  final Analytics analytics;
  final OnDeviceSummarizer? summarizer;

  const AppShell({
    super.key,
    required this.apiClient,
    required this.analytics,
    this.summarizer,
  });

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _index = 0;

  @override
  void initState() {
    super.initState();
    widget.analytics.screen(_screenNames[_index]);
  }

  void _goTo(int index) {
    setState(() => _index = index);
    widget.analytics.screen(_screenNames[index]);
  }

  @override
  Widget build(BuildContext context) {
    final screens = [
      HomeScreen(apiClient: widget.apiClient, onNavigate: _goTo),
      SummarizerScreen(
        apiClient: widget.apiClient,
        analytics: widget.analytics,
        summarizer: widget.summarizer,
      ),
      ProjectsScreen(apiClient: widget.apiClient),
      ChatScreen(apiClient: widget.apiClient, analytics: widget.analytics),
      ContactScreen(apiClient: widget.apiClient),
    ];

    return Scaffold(
      body: SafeArea(child: IndexedStack(index: _index, children: screens)),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: _goTo,
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Home'),
          NavigationDestination(
            icon: Icon(Icons.auto_awesome_outlined),
            label: 'Summarizer',
          ),
          NavigationDestination(
            icon: Icon(Icons.work_outline),
            label: 'Projects',
          ),
          NavigationDestination(
            icon: Icon(Icons.chat_bubble_outline),
            label: 'Ask',
          ),
          NavigationDestination(
            icon: Icon(Icons.mail_outline),
            label: 'Contact',
          ),
        ],
      ),
    );
  }
}

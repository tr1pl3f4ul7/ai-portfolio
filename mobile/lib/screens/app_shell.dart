import 'package:flutter/material.dart';

import '../api/client.dart';
import 'chat_screen.dart';
import 'contact_screen.dart';
import 'home_screen.dart';
import 'projects_screen.dart';
import 'summarizer_screen.dart';

/// Bottom-navigation shell across the app's five screens (decision 58: the
/// full dashboard scope, not a lean summarizer-only app).
class AppShell extends StatefulWidget {
  final ApiClient apiClient;

  const AppShell({super.key, required this.apiClient});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _index = 0;

  void _goTo(int index) => setState(() => _index = index);

  @override
  Widget build(BuildContext context) {
    final screens = [
      HomeScreen(apiClient: widget.apiClient, onNavigate: _goTo),
      SummarizerScreen(apiClient: widget.apiClient),
      ProjectsScreen(apiClient: widget.apiClient),
      ChatScreen(apiClient: widget.apiClient),
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

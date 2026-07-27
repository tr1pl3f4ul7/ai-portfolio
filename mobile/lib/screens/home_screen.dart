import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../theme/tokens.dart';
import 'async_content.dart';

/// The dashboard: hero copy plus buttons to the four other tabs (decision 58).
class HomeScreen extends StatelessWidget {
  final ApiClient apiClient;
  final ValueChanged<int> onNavigate;

  const HomeScreen({
    super.key,
    required this.apiClient,
    required this.onNavigate,
  });

  @override
  Widget build(BuildContext context) {
    return AsyncContent<ProfileContent>(
      fetch: apiClient.getProfile,
      builder: (context, profile) => ListView(
        padding: const EdgeInsets.all(Tokens.space5),
        children: [
          Text(
            profile.location.toUpperCase(),
            style: const TextStyle(
              color: Tokens.signal,
              fontSize: Tokens.sNeg1,
              letterSpacing: 1.5,
            ),
          ),
          const SizedBox(height: Tokens.space2),
          Text(
            profile.name,
            style: const TextStyle(
              color: Tokens.ink,
              fontSize: Tokens.s4,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: Tokens.space4),
          Text(
            profile.tagline,
            style: const TextStyle(color: Tokens.inkDim, fontSize: Tokens.s1, height: 1.4),
          ),
          const SizedBox(height: Tokens.space7),
          _DashboardTile(
            icon: Icons.auto_awesome_outlined,
            title: 'Summarizer',
            subtitle: 'A real summary, generated on your phone',
            color: Tokens.layerBrowser,
            onTap: () => onNavigate(1),
          ),
          _DashboardTile(
            icon: Icons.work_outline,
            title: 'Projects',
            subtitle: 'Things that had to not break',
            color: Tokens.layerEdge,
            onTap: () => onNavigate(2),
          ),
          _DashboardTile(
            icon: Icons.chat_bubble_outline,
            title: 'Ask',
            subtitle: "Retrieval plus Claude, grounded in Ljuben's work",
            color: Tokens.layerServer,
            onTap: () => onNavigate(3),
          ),
          _DashboardTile(
            icon: Icons.mail_outline,
            title: 'Contact',
            subtitle: 'Say hello',
            color: Tokens.layerCloud,
            onTap: () => onNavigate(4),
          ),
        ],
      ),
    );
  }
}

class _DashboardTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;
  final VoidCallback onTap;

  const _DashboardTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: Tokens.space3),
      child: ListTile(
        leading: Icon(icon, color: color),
        title: Text(title, style: const TextStyle(color: Tokens.ink)),
        subtitle: Text(subtitle, style: const TextStyle(color: Tokens.inkDim)),
        trailing: const Icon(Icons.chevron_right, color: Tokens.inkFaint),
        onTap: onTap,
      ),
    );
  }
}

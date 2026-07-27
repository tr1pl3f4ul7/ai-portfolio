import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../theme/tokens.dart';
import 'async_content.dart';

class ProjectsScreen extends StatelessWidget {
  final ApiClient apiClient;

  const ProjectsScreen({super.key, required this.apiClient});

  @override
  Widget build(BuildContext context) {
    return AsyncContent<ProjectsContent>(
      fetch: apiClient.getProjects,
      builder: (context, content) => ListView.builder(
        padding: const EdgeInsets.all(Tokens.space5),
        itemCount: content.items.length + 1,
        itemBuilder: (context, index) {
          if (index == 0) {
            return Padding(
              padding: const EdgeInsets.only(bottom: Tokens.space4),
              child: Text(
                content.heading,
                style: const TextStyle(
                  color: Tokens.ink,
                  fontSize: Tokens.s3,
                  fontWeight: FontWeight.w600,
                ),
              ),
            );
          }
          return _ProjectCard(item: content.items[index - 1]);
        },
      ),
    );
  }
}

class _ProjectCard extends StatelessWidget {
  final ProjectItem item;

  const _ProjectCard({required this.item});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: Tokens.space3),
      child: Padding(
        padding: const EdgeInsets.all(Tokens.space4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${item.company} · ${item.year}'.toUpperCase(),
              style: const TextStyle(color: Tokens.inkFaint, fontSize: Tokens.sNeg1),
            ),
            const SizedBox(height: Tokens.space1),
            Text(
              item.name,
              style: const TextStyle(
                color: Tokens.ink,
                fontSize: Tokens.s1,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: Tokens.space2),
            Text(item.note, style: const TextStyle(color: Tokens.inkDim, height: 1.4)),
          ],
        ),
      ),
    );
  }
}

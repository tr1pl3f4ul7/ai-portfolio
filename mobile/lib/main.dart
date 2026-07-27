import 'package:flutter/material.dart';

import 'api/client.dart';
import 'screens/app_shell.dart';
import 'theme/tokens.dart';

void main() {
  runApp(const AiPortfolioApp());
}

class AiPortfolioApp extends StatelessWidget {
  const AiPortfolioApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: "Ljuben Vassilev — mobile engineer, AI systems",
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: Tokens.ground,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Tokens.signal,
          brightness: Brightness.dark,
          surface: Tokens.surface,
          error: Tokens.danger,
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Tokens.ground,
          foregroundColor: Tokens.ink,
          elevation: 0,
        ),
        cardTheme: CardThemeData(
          color: Tokens.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(Tokens.sharp),
            side: const BorderSide(color: Tokens.line),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: Tokens.surfaceAlt,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(Tokens.sharp),
            borderSide: const BorderSide(color: Tokens.line),
          ),
        ),
        textTheme: const TextTheme(
          bodyMedium: TextStyle(color: Tokens.ink),
        ),
      ),
      home: AppShell(apiClient: ApiClient()),
    );
  }
}

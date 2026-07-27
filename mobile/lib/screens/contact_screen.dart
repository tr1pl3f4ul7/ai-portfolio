import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../theme/tokens.dart';
import 'async_content.dart';

class ContactScreen extends StatelessWidget {
  final ApiClient apiClient;

  const ContactScreen({super.key, required this.apiClient});

  @override
  Widget build(BuildContext context) {
    return AsyncContent<ContactContent>(
      fetch: apiClient.getContactContent,
      builder: (context, content) =>
          _ContactForm(apiClient: apiClient, content: content),
    );
  }
}

class _ContactForm extends StatefulWidget {
  final ApiClient apiClient;
  final ContactContent content;

  const _ContactForm({required this.apiClient, required this.content});

  @override
  State<_ContactForm> createState() => _ContactFormState();
}

class _ContactFormState extends State<_ContactForm> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _messageController = TextEditingController();

  bool _sending = false;
  String? _error;
  String? _reference;

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _messageController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_sending || !(_formKey.currentState?.validate() ?? false)) return;

    setState(() {
      _sending = true;
      _error = null;
    });

    try {
      final response = await widget.apiClient.submitContact(
        ContactRequest(
          name: _nameController.text.trim(),
          email: _emailController.text.trim(),
          message: _messageController.text.trim(),
        ),
      );
      if (!mounted) return;
      setState(() => _reference = response.reference);
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
    if (_reference != null) {
      return Padding(
        padding: const EdgeInsets.all(Tokens.space5),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.check_circle_outline, color: Tokens.ok, size: 40),
            const SizedBox(height: Tokens.space3),
            const Text(
              'Message sent.',
              style: TextStyle(
                color: Tokens.ink,
                fontSize: Tokens.s2,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: Tokens.space2),
            Text('Reference: $_reference', style: const TextStyle(color: Tokens.inkDim)),
          ],
        ),
      );
    }

    return Form(
      key: _formKey,
      child: ListView(
        padding: const EdgeInsets.all(Tokens.space5),
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
          const SizedBox(height: Tokens.space5),
          TextFormField(
            controller: _nameController,
            enabled: !_sending,
            decoration: const InputDecoration(labelText: 'Name'),
            validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
          ),
          const SizedBox(height: Tokens.space3),
          TextFormField(
            controller: _emailController,
            enabled: !_sending,
            keyboardType: TextInputType.emailAddress,
            decoration: const InputDecoration(labelText: 'Email'),
            validator: (v) => (v == null || !v.contains('@')) ? 'Enter a valid email' : null,
          ),
          const SizedBox(height: Tokens.space3),
          TextFormField(
            controller: _messageController,
            enabled: !_sending,
            maxLines: 5,
            decoration: const InputDecoration(labelText: 'Message'),
            validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
          ),
          const SizedBox(height: Tokens.space4),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: Tokens.space3),
              child: Text(_error!, style: const TextStyle(color: Tokens.danger)),
            ),
          FilledButton(
            onPressed: _sending ? null : _submit,
            child: _sending
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Send'),
          ),
        ],
      ),
    );
  }
}

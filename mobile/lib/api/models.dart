/// Contract types. Mirrors `backend/app/schemas.py` — change one, change all
/// three clients (see the `api-contract` skill).
library;

class Source {
  final String document;
  final String section;

  const Source({required this.document, required this.section});

  factory Source.fromJson(Map<String, dynamic> json) => Source(
    document: json['document'] as String,
    section: json['section'] as String,
  );
}

class ChatResponse {
  final String answer;
  final List<Source> sources;

  const ChatResponse({required this.answer, required this.sources});

  factory ChatResponse.fromJson(Map<String, dynamic> json) => ChatResponse(
    answer: json['answer'] as String,
    sources: (json['sources'] as List<dynamic>)
        .map((e) => Source.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

class ContactRequest {
  final String name;
  final String email;
  final String message;

  const ContactRequest({
    required this.name,
    required this.email,
    required this.message,
  });

  Map<String, dynamic> toJson() => {
    'name': name,
    'email': email,
    'message': message,
  };
}

class ContactResponse {
  final bool received;
  final String reference;

  const ContactResponse({required this.received, required this.reference});

  factory ContactResponse.fromJson(Map<String, dynamic> json) =>
      ContactResponse(
        received: json['received'] as bool,
        reference: json['reference'] as String,
      );
}

// --- Content (mirror backend/app/content.py + schemas.py) ------------------
//
// Portfolio copy, fetched rather than hardcoded — decision 57: one edit on
// the backend reaches web and mobile without an app-store resubmission.

class ProfileContent {
  final String name;
  final String location;
  final String tagline;

  const ProfileContent({
    required this.name,
    required this.location,
    required this.tagline,
  });

  factory ProfileContent.fromJson(Map<String, dynamic> json) =>
      ProfileContent(
        name: json['name'] as String,
        location: json['location'] as String,
        tagline: json['tagline'] as String,
      );
}

class SectionContent {
  final String label;
  final String heading;
  final String description;

  const SectionContent({
    required this.label,
    required this.heading,
    required this.description,
  });

  factory SectionContent.fromJson(Map<String, dynamic> json) =>
      SectionContent(
        label: json['label'] as String,
        heading: json['heading'] as String,
        description: json['description'] as String,
      );
}

/// Mobile's on-device summarizer section copy, plus the source text it
/// condenses. Mobile-only — the direct counterpart to web's `browser`.
class SummarizerContent extends SectionContent {
  final String sourceText;

  const SummarizerContent({
    required super.label,
    required super.heading,
    required super.description,
    required this.sourceText,
  });

  factory SummarizerContent.fromJson(Map<String, dynamic> json) =>
      SummarizerContent(
        label: json['label'] as String,
        heading: json['heading'] as String,
        description: json['description'] as String,
        sourceText: json['source_text'] as String,
      );
}

/// Chat section copy, shared by web and mobile.
class AskContent extends SectionContent {
  final List<String> suggestions;

  const AskContent({
    required super.label,
    required super.heading,
    required super.description,
    required this.suggestions,
  });

  factory AskContent.fromJson(Map<String, dynamic> json) => AskContent(
    label: json['label'] as String,
    heading: json['heading'] as String,
    description: json['description'] as String,
    suggestions: (json['suggestions'] as List<dynamic>).cast<String>(),
  );
}

/// Contact section copy, shared by web and mobile.
typedef ContactContent = SectionContent;

class ProjectItem {
  final String company;
  final String year;
  final String name;
  final String note;

  const ProjectItem({
    required this.company,
    required this.year,
    required this.name,
    required this.note,
  });

  factory ProjectItem.fromJson(Map<String, dynamic> json) => ProjectItem(
    company: json['company'] as String,
    year: json['year'] as String,
    name: json['name'] as String,
    note: json['note'] as String,
  );
}

class ProjectsContent {
  final String label;
  final String heading;
  final List<ProjectItem> items;

  const ProjectsContent({
    required this.label,
    required this.heading,
    required this.items,
  });

  factory ProjectsContent.fromJson(Map<String, dynamic> json) =>
      ProjectsContent(
        label: json['label'] as String,
        heading: json['heading'] as String,
        items: (json['items'] as List<dynamic>)
            .map((e) => ProjectItem.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

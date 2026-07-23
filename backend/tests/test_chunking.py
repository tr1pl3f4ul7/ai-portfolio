"""Tests for markdown chunking.

Pure logic, no embeddings and no sqlite-vec, so these run on any platform.
"""

from app.chunking import chunk_markdown

SAMPLE = """# Employment history

Some preamble that belongs to no section.

## Software Engineer at AI Talent (April 2026 - present)

Works in Flutter and Dart.

## Android Developer at Gruntify (April 2020 - January 2022)

Contract role, hybrid, in Australia.
"""


def test_splits_on_h2_headings():
    chunks = chunk_markdown("experience.md", SAMPLE)
    assert len(chunks) == 2


def test_preamble_is_not_its_own_chunk():
    """Text before the first ## is context, not an answer to any question."""
    chunks = chunk_markdown("experience.md", SAMPLE)
    assert not any("belongs to no section" in c.body for c in chunks)


def test_chunk_records_document_title():
    chunks = chunk_markdown("experience.md", SAMPLE)
    assert all(c.document_title == "Employment history" for c in chunks)


def test_embedded_text_is_prefixed_with_the_subject():
    """Sections are retrieved alone, so each must say whose experience it is.

    The subject, not the document title — prefixing 'Frequently asked
    questions' onto every FAQ chunk made them match any question-shaped query.
    """
    chunks = chunk_markdown("experience.md", SAMPLE, subject="Ljuben Vassilev")
    assert chunks[0].text.startswith("Ljuben Vassilev — Software Engineer at AI Talent")
    assert "Employment history" not in chunks[0].text


def test_subject_defaults_to_document_title():
    chunks = chunk_markdown("experience.md", SAMPLE)
    assert chunks[0].text.startswith("Employment history — ")


def test_heading_and_body_are_separated():
    chunks = chunk_markdown("experience.md", SAMPLE)
    assert chunks[1].heading == "Android Developer at Gruntify (April 2020 - January 2022)"
    assert chunks[1].body == "Contract role, hybrid, in Australia."


def test_source_is_recorded():
    chunks = chunk_markdown("experience.md", SAMPLE)
    assert all(c.source == "experience.md" for c in chunks)


def test_empty_sections_are_dropped():
    """A heading with no content is noise in the index."""
    chunks = chunk_markdown("x.md", "# Title\n\n## Empty\n\n## Real\n\nHas content.\n")
    assert [c.heading for c in chunks] == ["Real"]


def test_document_with_no_h2_yields_nothing():
    assert chunk_markdown("x.md", "# Title\n\nJust prose, no sections.\n") == []


def test_falls_back_to_filename_when_no_h1():
    chunks = chunk_markdown("notitle.md", "## Section\n\nBody text.\n")
    assert chunks[0].document_title == "notitle.md"

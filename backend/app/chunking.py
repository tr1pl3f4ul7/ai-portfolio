"""Split the markdown corpus into retrievable chunks.

Chunking is on `##` headings: one section becomes one chunk. The corpus in
`data/` is written that way deliberately, so a section is a self-contained
answer to one question.

Deliberately free of any dependency on embeddings, sqlite or the filesystem
layout, so it can be tested quickly on any platform.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_H1 = re.compile(r"^#\s+(.*)$", re.MULTILINE)
_H2_SPLIT = re.compile(r"^##\s+", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit of the corpus."""

    source: str
    """File the chunk came from, e.g. 'experience.md'."""

    heading: str
    """The `##` heading text."""

    body: str
    """Section content, excluding the heading."""

    @property
    def text(self) -> str:
        """The text actually embedded.

        Prefixed with the SUBJECT, not the document title. Sections are
        retrieved in isolation, so a chunk headed 'Gruntify' needs to say whose
        project it was — but prefixing the document title was measurably worse.
        Every faq.md chunk then began 'Frequently asked questions — ', which
        matched any question-shaped query regardless of topic: a FAQ entry
        ranked first for 8 of 12 evaluation queries. With a subject prefix that
        drops to 4 of 12 and the hit rate improves. See
        backend/test/compare_chunk_prefix.py.
        """
        return f"{self.subject} — {self.heading}\n\n{self.body}".strip()

    document_title: str = ""
    subject: str = ""


def chunk_markdown(source: str, content: str, subject: str = "") -> list[Chunk]:
    """Split one markdown document into chunks, one per `##` section.

    Text before the first `##` (the title and any preamble) is not emitted as
    its own chunk; the title is recorded on each chunk as metadata.

    `subject` is what each chunk is prefixed with when embedded — the person or
    entity the corpus is about. Passed in rather than hardcoded so this module
    stays free of corpus-specific knowledge.
    """
    title_match = _H1.search(content)
    title = title_match.group(1).strip() if title_match else source

    parts = _H2_SPLIT.split(content)
    if len(parts) < 2:
        return []

    chunks: list[Chunk] = []
    for part in parts[1:]:
        lines = part.split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if not heading or not body:
            # A heading with no content retrieves as noise.
            continue
        chunks.append(
            Chunk(
                source=source,
                heading=heading,
                body=body,
                document_title=title,
                subject=subject or title,
            )
        )
    return chunks

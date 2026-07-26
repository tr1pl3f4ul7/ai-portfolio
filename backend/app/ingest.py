"""Build the vector store from the markdown corpus.

    python -m app.ingest

Safe to re-run: the index is rebuilt from scratch every time, so editing the
corpus and running this again is the whole content-update workflow.

Runs on the VM at deploy time. The embedding model is needed there anyway to
embed incoming queries, so ingestion costs no extra dependency.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.chunking import Chunk, chunk_markdown
from app.config import CORPUS_SUBJECT, DATA_DIR, DB_PATH


def load_chunks(data_dir: Path) -> list[Chunk]:
    """Read and chunk every markdown file in the corpus, in a stable order."""
    chunks: list[Chunk] = []
    for path in sorted(data_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        chunks.extend(chunk_markdown(path.name, content, subject=CORPUS_SUBJECT))
    return chunks


def ingest(data_dir: Path = DATA_DIR, db_path: Path = DB_PATH) -> int:
    """Chunk, embed and store the corpus. Returns the number of chunks stored."""
    from app import store
    from app.embeddings import embed_texts

    chunks = load_chunks(data_dir)
    if not chunks:
        raise SystemExit(f"No chunks found in {data_dir} — is the corpus present?")

    print(f"chunked {len(chunks)} sections from {len({c.source for c in chunks})} files")

    embeddings = embed_texts([c.text for c in chunks])
    print(f"embedded {len(embeddings)} chunks")

    conn = store.connect(db_path)
    try:
        store.init_schema(conn)
        stored = store.replace_all(
            conn,
            [(c.source, c.heading, c.text) for c in chunks],
            embeddings,
        )
    finally:
        conn.close()

    print(f"stored {stored} chunks in {db_path}")
    return stored


def main() -> int:
    ingest()
    return 0


if __name__ == "__main__":
    sys.exit(main())

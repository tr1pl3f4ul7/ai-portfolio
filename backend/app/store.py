"""SQLite-vec vector store.

Embedded rather than a separate service: no extra process to run, monitor or
pay for, and nothing else competing for the VM's 12 GB.

Note this requires the sqlite-vec loadable extension, which publishes no
Windows ARM64 wheel. On the dev machine these code paths run inside a Linux
container; see backend/test/. The VM (Linux aarch64) and CI both have wheels.
"""

from __future__ import annotations

import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path

from app.config import EMBEDDING_DIMENSIONS


@dataclass(frozen=True)
class SearchResult:
    source: str
    heading: str
    text: str
    distance: float


def _serialise(vector: list[float]) -> bytes:
    """Pack a float vector into the compact binary format sqlite-vec expects."""
    return struct.pack(f"{len(vector)}f", *vector)


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the store with the sqlite-vec extension loaded."""
    import sqlite_vec

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the chunk table and its vector index if absent."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id       INTEGER PRIMARY KEY,
            source   TEXT NOT NULL,
            heading  TEXT NOT NULL,
            text     TEXT NOT NULL
        )
        """
    )
    conn.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(
            embedding float[{EMBEDDING_DIMENSIONS}]
        )
        """
    )
    conn.commit()


def replace_all(
    conn: sqlite3.Connection,
    chunks: list[tuple[str, str, str]],
    embeddings: list[list[float]],
) -> int:
    """Replace the entire index.

    A full rebuild rather than an incremental update. At this corpus size the
    rebuild is cheap, and it makes stale chunks structurally impossible —
    deleting a section from the corpus cannot leave an orphaned vector behind
    that the chatbot would go on citing.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(f"{len(chunks)} chunks but {len(embeddings)} embeddings")

    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM chunk_vectors")

    for rowid, ((source, heading, text), vector) in enumerate(zip(chunks, embeddings), start=1):
        conn.execute(
            "INSERT INTO chunks (id, source, heading, text) VALUES (?, ?, ?, ?)",
            (rowid, source, heading, text),
        )
        conn.execute(
            "INSERT INTO chunk_vectors (rowid, embedding) VALUES (?, ?)",
            (rowid, _serialise(vector)),
        )

    conn.commit()
    return len(chunks)


def search(conn: sqlite3.Connection, query_vector: list[float], k: int) -> list[SearchResult]:
    """Return the k nearest chunks to the query vector."""
    rows = conn.execute(
        """
        SELECT c.source, c.heading, c.text, v.distance
        FROM chunk_vectors v
        JOIN chunks c ON c.id = v.rowid
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (_serialise(query_vector), k),
    ).fetchall()
    return [SearchResult(source=r[0], heading=r[1], text=r[2], distance=r[3]) for r in rows]


def count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

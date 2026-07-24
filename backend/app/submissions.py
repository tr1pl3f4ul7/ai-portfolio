"""Durable store for contact-form submissions.

Plain sqlite3, no extension — so unlike the vector store this runs natively
everywhere, including the Windows dev machine.

Its own database file, never `vectors.db`: decision 27 has ingestion rebuild the
vector store from scratch on every deploy, and a stranger's message is the last
thing that should live inside a disposable build artefact.

The store is the source of truth. A submission is written here **before** the
Claude call and before the notification, so neither the model being down nor
Resend having a bad morning can lose somebody's message.

Contains personal data — a real name, a real email, whatever they chose to
write. The file stays on the VM, is gitignored, and none of it is ever printed.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import SUBMISSIONS_DB_PATH
from app.schemas import ContactRequest, TriageResult


@dataclass(frozen=True)
class StoredSubmission:
    reference: str
    received_at: str
    name: str
    email: str
    message: str
    category: str | None
    priority: str | None
    summary: str | None
    draft_reply: str | None
    company: str | None
    role: str | None
    notified: bool


def _connect(db_path: Path | None) -> sqlite3.Connection:
    """Open the store, creating the file and schema if this is the first write.

    A connection per call rather than one shared for the process: FastAPI runs
    sync handlers in a thread pool and a sqlite3 connection is not safe to share
    across threads. At a handful of submissions a day the cost is irrelevant.
    """
    path = db_path or SUBMISSIONS_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS submissions (
            reference    TEXT PRIMARY KEY,
            received_at  TEXT NOT NULL,
            name         TEXT NOT NULL,
            email        TEXT NOT NULL,
            message      TEXT NOT NULL,
            category     TEXT,
            priority     TEXT,
            summary      TEXT,
            draft_reply  TEXT,
            company      TEXT,
            role         TEXT,
            notified     INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    return conn


def record(submission: ContactRequest, db_path: Path | None = None) -> str:
    """Persist a raw submission and return its reference.

    Called before anything that can fail. The triage columns stay null until
    (and unless) `record_triage` fills them in.
    """
    reference = uuid4().hex[:12]
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO submissions (reference, received_at, name, email, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                reference,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                submission.name,
                str(submission.email),
                submission.message,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return reference


def record_triage(reference: str, result: TriageResult, db_path: Path | None = None) -> None:
    """Attach a triage result to an already-stored submission."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            UPDATE submissions
               SET category = ?, priority = ?, summary = ?,
                   draft_reply = ?, company = ?, role = ?
             WHERE reference = ?
            """,
            (
                result.category,
                result.priority,
                result.summary,
                result.draft_reply,
                result.company,
                result.role,
                reference,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def mark_notified(reference: str, db_path: Path | None = None) -> None:
    """Flag that LJ has been told about this one.

    Anything still sitting at notified = 0 is a message that reached the store
    but never reached him — the query to run when the contact form goes quiet.
    """
    conn = _connect(db_path)
    try:
        conn.execute("UPDATE submissions SET notified = 1 WHERE reference = ?", (reference,))
        conn.commit()
    finally:
        conn.close()


def fetch(reference: str, db_path: Path | None = None) -> StoredSubmission | None:
    """Read one submission back. Used by tests and by hand on the VM."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM submissions WHERE reference = ?", (reference,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    return StoredSubmission(
        reference=row["reference"],
        received_at=row["received_at"],
        name=row["name"],
        email=row["email"],
        message=row["message"],
        category=row["category"],
        priority=row["priority"],
        summary=row["summary"],
        draft_reply=row["draft_reply"],
        company=row["company"],
        role=row["role"],
        notified=bool(row["notified"]),
    )

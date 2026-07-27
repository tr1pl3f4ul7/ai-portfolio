"""Portfolio content — the single source both web and mobile read from.

Lives as committed JSON in data/content/, the same pattern data/*.md already
uses for the RAG corpus: edit the file, commit, push. A backend deploy
carries the change to both clients — no web rebuild, no app-store
resubmission for mobile. Loaded once at import, matching config.py's own
"read once" convention; content only changes via a redeploy anyway, which
restarts this process regardless.
"""

from __future__ import annotations

import json

from app.config import BACKEND_ROOT
from app.schemas import (
    AskContent,
    BrowserContent,
    ContactContent,
    ProfileContent,
    ProjectsContent,
    SummarizerContent,
)

CONTENT_DIR = BACKEND_ROOT / "data" / "content"


def _load(filename: str) -> dict:
    return json.loads((CONTENT_DIR / filename).read_text(encoding="utf-8"))


PROFILE = ProfileContent(**_load("profile.json"))
BROWSER = BrowserContent(**_load("browser.json"))
SUMMARIZER = SummarizerContent(**_load("summarizer.json"))
ASK = AskContent(**_load("ask.json"))
CONTACT = ContactContent(**_load("contact.json"))
PROJECTS = ProjectsContent(**_load("projects.json"))

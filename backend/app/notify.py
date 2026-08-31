"""Notify LJ that a contact submission arrived, via Resend.

HTTPS to api.resend.com, not SMTP. Oracle Cloud blocks outbound 25/465/587 by
default on new tenancies, so a mail library would need a support ticket before
it ever delivered anything. See decision 33.

`urllib.request` rather than a HTTP client library: this is one POST, a few
times a day, and the standard library already does it. Nothing here justifies a
dependency the VM would have to carry.

Notification is best-effort by design. The submission is already durable in the
store by the time this runs, so a failure here is worth logging and worth
retrying by hand — it is not worth failing the visitor's request over.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.config import (
    CONTACT_NOTIFY_FROM,
    CONTACT_NOTIFY_TO,
    CORPUS_SUBJECT,
    RESEND_API_KEY,
)
from app.schemas import ContactRequest, TriageResult

RESEND_ENDPOINT = "https://api.resend.com/emails"

# api.resend.com is behind Cloudflare, whose bot rules reject urllib's default
# `Python-urllib/x.y` User-Agent with a 403 (Cloudflare error 1010) before the
# request ever reaches Resend. Identifying ourselves as a normal named client
# is not evasion — it is what any HTTP library sends — and it is the difference
# between the notification arriving and silently 403-ing.
USER_AGENT = "ai-portfolio-backend/0.2 (+https://ljubenvassilev.com)"


class NotificationFailed(Exception):
    """The notification did not go out. The submission is still stored."""


def build_subject(submission: ContactRequest, result: TriageResult | None) -> str:
    if result is None:
        return f"[portfolio] contact from {submission.name} (triage unavailable)"
    return f"[portfolio] {result.priority} · {result.category} — {submission.name}"


def build_body(reference: str, submission: ContactRequest, result: TriageResult | None) -> str:
    """Plain text, ordered so the first screen answers 'do I need to act on this'.

    The draft reply is labelled unmistakably. It was written by a model that
    just read a stranger's text, and it goes out under LJ's name if he sends it
    — so it must never look like something already sent.
    """
    lines = [f"From: {submission.name} <{submission.email}>"]

    if result is None:
        lines.append("")
        lines.append("Triage did not run for this one — the message is below, unprocessed.")
    else:
        lines.append(f"Category: {result.category}    Priority: {result.priority}")
        if result.company or result.role:
            named = " · ".join(filter(None, [result.company, result.role]))
            lines.append(f"Mentioned: {named}")
        lines.append("")
        lines.append(result.summary)

    lines += ["", "-- their message " + "-" * 44, "", submission.message]

    if result is not None:
        lines += [
            "",
            "-- DRAFT REPLY, not sent " + "-" * 35,
            "",
            result.draft_reply,
            "",
            "Drafted by the model from the message above. Read it before you send it.",
        ]

    lines += ["", "-" * 60, f"reference {reference}"]
    return "\n".join(lines)


def _build_request(payload: dict) -> urllib.request.Request:
    """Construct the Resend POST, User-Agent included.

    Split out from `_post` so the headers are testable without a live call — the
    User-Agent in particular, since its absence is exactly what broke delivery.
    """
    return urllib.request.Request(
        RESEND_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )


def _post(payload: dict, timeout: float = 15.0) -> None:
    """POST to Resend. Raises NotificationFailed on anything other than success."""
    request = _build_request(payload)
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return
    except urllib.error.HTTPError as exc:
        # Resend's error body describes the problem (bad key, unverified sender)
        # and contains nothing secret, so it is worth keeping for the log.
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise NotificationFailed(f"Resend returned {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NotificationFailed(f"could not reach Resend: {exc}") from exc


def send(reference: str, submission: ContactRequest, result: TriageResult | None) -> None:
    """Email LJ about one submission."""
    if not RESEND_API_KEY:
        raise NotificationFailed("RESEND_API_KEY is not set")
    if not CONTACT_NOTIFY_TO:
        raise NotificationFailed("CONTACT_NOTIFY_TO is not set")

    _post(
        {
            "from": f"{CORPUS_SUBJECT} portfolio <{CONTACT_NOTIFY_FROM}>",
            "to": [CONTACT_NOTIFY_TO],
            # So a reply from LJ's mail client goes to the sender, not to Resend.
            "reply_to": str(submission.email),
            "subject": build_subject(submission, result),
            "text": build_body(reference, submission, result),
        }
    )

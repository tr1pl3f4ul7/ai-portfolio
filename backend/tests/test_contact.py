"""Tests for POST /contact — storage, notification, and what survives failure.

The theme running through most of these: a visitor's message must not be lost.
Claude can be down, Resend can be down, triage can refuse — the submission is
still on disk and the sender still gets a 200. The only fatal failure is being
unable to store it at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main, notify, submissions, triage
from app.config import MAX_MESSAGE_CHARS, MAX_NAME_CHARS
from app.ratelimit import DailyRateLimiter
from app.schemas import ContactRequest, TriageResult
from tests.conftest import FakeParsedMessage

client = TestClient(main.app)

PAYLOAD = {
    "name": "Dana Okafor",
    "email": "dana@example.com",
    "message": "We're hiring a senior Flutter engineer at Northwind.",
}

RESULT = TriageResult(
    category="job_opportunity",
    priority="high",
    summary="Northwind is hiring a senior Flutter engineer.",
    draft_reply="Thanks for getting in touch — I'll follow up shortly.",
    company="Northwind",
    role="Senior Flutter Engineer",
)


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    """Point the submissions store at a throwaway file for every test."""
    db_path = tmp_path / "submissions.db"
    monkeypatch.setattr(submissions, "SUBMISSIONS_DB_PATH", db_path)
    return db_path


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    monkeypatch.setattr(main, "contact_limiter", DailyRateLimiter(5, 50))


@pytest.fixture
def triaged(monkeypatch):
    """Make triage succeed, fail, or be skipped, without touching the API."""

    def install(result=RESULT):
        if isinstance(result, Exception):
            monkeypatch.setattr(triage, "triage", lambda submission: (_ for _ in ()).throw(result))
        else:
            monkeypatch.setattr(triage, "triage", lambda submission: result)

    return install


# --- The happy path ---------------------------------------------------------


def test_contact_accepts_a_submission(triaged, fake_resend):
    triaged()
    fake_resend()

    response = client.post("/contact", json=PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["reference"]


def test_the_sender_never_sees_the_triage(triaged, fake_resend):
    """Telling someone they were filed as low-priority spam would be a bad day."""
    triaged(
        TriageResult(
            category="spam",
            priority="low",
            summary="Bulk SEO pitch.",
            draft_reply="No thank you.",
        )
    )
    fake_resend()

    body = client.post("/contact", json=PAYLOAD).json()

    assert set(body) == {"received", "reference"}
    for leak in ["spam", "low", "Bulk SEO", "No thank you"]:
        assert leak not in response_text(body)


def response_text(body: dict) -> str:
    return " ".join(str(v) for v in body.values())


def test_the_submission_is_stored_with_its_triage(store, triaged, fake_resend):
    triaged()
    fake_resend()

    reference = client.post("/contact", json=PAYLOAD).json()["reference"]

    stored = submissions.fetch(reference, db_path=store)
    assert stored is not None
    assert stored.name == "Dana Okafor"
    assert stored.email == "dana@example.com"
    assert stored.message == PAYLOAD["message"]
    assert stored.category == "job_opportunity"
    assert stored.priority == "high"
    assert stored.company == "Northwind"
    assert stored.notified is True


def test_the_notification_carries_the_summary_and_the_draft(triaged, fake_resend):
    triaged()
    sent = fake_resend()

    client.post("/contact", json=PAYLOAD)

    assert len(sent) == 1
    email = sent[0]
    assert "Northwind is hiring" in email["text"]
    assert "I'll follow up shortly" in email["text"]
    assert PAYLOAD["message"] in email["text"]


def test_the_draft_is_labelled_as_a_draft(triaged, fake_resend):
    """It was written by a model reading a stranger's text. Never let it look sent."""
    triaged()
    sent = fake_resend()

    client.post("/contact", json=PAYLOAD)

    assert "DRAFT REPLY, not sent" in sent[0]["text"]
    assert "Read it before you send it." in sent[0]["text"]


def test_the_subject_leads_with_priority_and_category(triaged, fake_resend):
    triaged()
    sent = fake_resend()

    client.post("/contact", json=PAYLOAD)

    assert sent[0]["subject"] == "[portfolio] high · job_opportunity — Dana Okafor"


def test_reply_to_is_the_sender(triaged, fake_resend):
    """So hitting reply in LJ's mail client reaches the person, not Resend."""
    triaged()
    sent = fake_resend()

    client.post("/contact", json=PAYLOAD)

    assert sent[0]["reply_to"] == "dana@example.com"


# --- Nothing downstream may lose a message ----------------------------------


def test_a_triage_failure_still_stores_and_still_notifies(store, triaged, fake_resend):
    triaged(triage.TriageUnavailable("the Claude API returned 529"))
    sent = fake_resend()

    response = client.post("/contact", json=PAYLOAD)
    reference = response.json()["reference"]

    assert response.status_code == 200
    stored = submissions.fetch(reference, db_path=store)
    assert stored.message == PAYLOAD["message"]
    assert stored.category is None
    assert len(sent) == 1
    assert PAYLOAD["message"] in sent[0]["text"]
    assert "triage unavailable" in sent[0]["subject"]


def test_a_triage_failure_says_so_in_the_email(triaged, fake_resend):
    triaged(triage.TriageUnavailable("boom"))
    sent = fake_resend()

    client.post("/contact", json=PAYLOAD)

    assert "Triage did not run" in sent[0]["text"]
    assert "DRAFT REPLY" not in sent[0]["text"]


def test_a_notification_failure_still_returns_200(store, triaged, fake_resend):
    """The message is already durable. Do not make the sender type it again."""
    triaged()
    fake_resend(fail_with=notify.NotificationFailed("Resend returned 403"))

    response = client.post("/contact", json=PAYLOAD)
    reference = response.json()["reference"]

    assert response.status_code == 200
    assert submissions.fetch(reference, db_path=store).message == PAYLOAD["message"]


def test_an_unnotified_submission_is_flagged_as_such(store, triaged, fake_resend):
    """notified = 0 is the query to run when the contact form goes quiet."""
    triaged()
    fake_resend(fail_with=notify.NotificationFailed("Resend returned 403"))

    reference = client.post("/contact", json=PAYLOAD).json()["reference"]

    assert submissions.fetch(reference, db_path=store).notified is False


def test_a_storage_failure_is_the_one_fatal_error(monkeypatch, triaged, fake_resend):
    """Nothing is holding the message at this point. A 200 would be a lie."""
    triaged()
    fake_resend()

    def boom(submission, db_path=None):
        raise OSError("disk full")

    monkeypatch.setattr(submissions, "record", boom)

    response = client.post("/contact", json=PAYLOAD)

    assert response.status_code == 503
    assert response.json()["detail"] == "could not store the submission"


def test_nothing_is_emailed_when_storage_fails(monkeypatch, triaged, fake_resend):
    triaged()
    sent = fake_resend()
    monkeypatch.setattr(
        submissions, "record", lambda submission, db_path=None: (_ for _ in ()).throw(OSError())
    )

    client.post("/contact", json=PAYLOAD)

    assert sent == []


# --- Validation -------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "email": "d@example.com", "message": "hi"},
        {"name": "Dana", "email": "d@example.com", "message": ""},
        {"name": "Dana", "email": "not-an-email", "message": "hi"},
        {"name": "Dana", "email": "", "message": "hi"},
        {"name": "Dana", "message": "hi"},
        {"email": "d@example.com", "message": "hi"},
        {"name": "Dana", "email": "d@example.com"},
        {},
    ],
)
def test_malformed_submissions_are_rejected(payload):
    assert client.post("/contact", json=payload).status_code == 422


def test_an_oversized_message_is_rejected():
    payload = dict(PAYLOAD, message="a" * (MAX_MESSAGE_CHARS + 1))
    assert client.post("/contact", json=payload).status_code == 422


def test_an_oversized_name_is_rejected():
    payload = dict(PAYLOAD, name="a" * (MAX_NAME_CHARS + 1))
    assert client.post("/contact", json=payload).status_code == 422


def test_a_rejected_submission_costs_nothing(fake_claude, fake_resend):
    """No model call, no email, no row."""
    fake = fake_claude(FakeParsedMessage(parsed_output=RESULT))
    sent = fake_resend()

    client.post("/contact", json={})

    assert fake.messages.calls == []
    assert sent == []


def test_contact_rejects_get():
    assert client.get("/contact").status_code == 405


# --- Rate limiting ----------------------------------------------------------


def test_contact_is_rate_limited_per_ip(monkeypatch, triaged, fake_resend):
    monkeypatch.setattr(main, "contact_limiter", DailyRateLimiter(per_ip_limit=2, total_limit=50))
    triaged()
    fake_resend()

    headers = {"X-Real-IP": "203.0.113.7"}
    assert client.post("/contact", json=PAYLOAD, headers=headers).status_code == 200
    assert client.post("/contact", json=PAYLOAD, headers=headers).status_code == 200

    response = client.post("/contact", json=PAYLOAD, headers=headers)
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_contact_and_chat_have_separate_budgets(monkeypatch, triaged, fake_resend):
    """Chat traffic must not be able to exhaust LJ's ability to receive mail."""
    monkeypatch.setattr(main, "limiter", DailyRateLimiter(per_ip_limit=0, total_limit=0))
    monkeypatch.setattr(main, "contact_limiter", DailyRateLimiter(per_ip_limit=5, total_limit=50))
    triaged()
    fake_resend()

    assert client.post("/chat", json={"question": "hi"}).status_code == 429
    assert client.post("/contact", json=PAYLOAD).status_code == 200


def test_a_rate_limited_submission_is_not_stored(store, monkeypatch, triaged, fake_resend):
    monkeypatch.setattr(main, "contact_limiter", DailyRateLimiter(per_ip_limit=0, total_limit=50))
    triaged()
    sent = fake_resend()

    assert client.post("/contact", json=PAYLOAD).status_code == 429
    assert sent == []


# --- The store on its own ---------------------------------------------------


def test_references_are_unique(store):
    submission = ContactRequest(**PAYLOAD)
    references = {submissions.record(submission, db_path=store) for _ in range(50)}
    assert len(references) == 50


def test_fetch_returns_none_for_an_unknown_reference(store):
    assert submissions.fetch("does-not-exist", db_path=store) is None


def test_a_stored_submission_starts_unnotified_and_untriaged(store):
    reference = submissions.record(ContactRequest(**PAYLOAD), db_path=store)
    stored = submissions.fetch(reference, db_path=store)

    assert stored.notified is False
    assert stored.category is None
    assert stored.summary is None
    assert stored.draft_reply is None


def test_the_store_survives_reopening(store):
    """It is a file on disk, not process state — a restart must not lose it."""
    reference = submissions.record(ContactRequest(**PAYLOAD), db_path=store)
    submissions.record_triage(reference, RESULT, db_path=store)
    submissions.mark_notified(reference, db_path=store)

    stored = submissions.fetch(reference, db_path=store)
    assert stored.summary == RESULT.summary
    assert stored.notified is True


def test_received_at_is_recorded_in_utc(store):
    reference = submissions.record(ContactRequest(**PAYLOAD), db_path=store)
    assert submissions.fetch(reference, db_path=store).received_at.endswith("+00:00")

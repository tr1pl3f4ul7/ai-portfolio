"""Tests for GET /resume.

A static PDF read, same shape as /content/*: no side effects, no rate limit,
just confirm the file is served with the right type and as a download.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import ALLOWED_ORIGINS, RESUME_PDF_PATH
from app.main import app

client = TestClient(app)


def test_resume_returns_200():
    response = client.get("/resume")
    assert response.status_code == 200


def test_resume_is_a_pdf():
    response = client.get("/resume")
    assert response.headers["content-type"] == "application/pdf"


def test_resume_is_served_as_a_download_with_a_real_name():
    response = client.get("/resume")
    assert 'filename="Ljuben-Vassilev-Resume.pdf"' in response.headers["content-disposition"]


def test_resume_body_matches_the_file_on_disk():
    response = client.get("/resume")
    assert response.content == RESUME_PDF_PATH.read_bytes()


def test_resume_is_reachable_from_the_allowed_web_origin():
    response = client.get("/resume", headers={"Origin": ALLOWED_ORIGINS[0]})
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGINS[0]

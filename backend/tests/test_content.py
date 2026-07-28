"""Tests for the /content/* endpoints.

Portfolio copy — the single source web reads from (see app/content.py).
These endpoints are static reads with no side effects, so there's no rate
limiting and no mocking needed: just confirm each one returns the real,
loaded content in its expected shape.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import content, main
from app.config import ALLOWED_ORIGINS

client = TestClient(main.app)


def test_profile_returns_the_hero_copy():
    response = client.get("/content/profile")

    assert response.status_code == 200
    assert response.json() == {
        "name": content.PROFILE.name,
        "location": content.PROFILE.location,
        "tagline": content.PROFILE.tagline,
    }


def test_browser_has_the_section_shape():
    response = client.get("/content/browser")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"label", "heading", "description"}


def test_ask_carries_suggestions():
    response = client.get("/content/ask")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"label", "heading", "description", "suggestions"}
    assert len(body["suggestions"]) > 0


def test_contact_has_the_section_shape():
    response = client.get("/content/contact")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"label", "heading", "description"}


def test_projects_lists_every_real_project():
    response = client.get("/content/projects")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"label", "heading", "items"}
    assert len(body["items"]) == len(content.PROJECTS.items)
    assert {"company", "year", "name", "note"} <= set(body["items"][0])


def test_content_endpoints_are_reachable_from_the_allowed_web_origin():
    """A regression guard for the exact gap decision 56 found: a passing
    preflight is not enough, the real GET response needs the CORS header too."""
    response = client.get("/content/profile", headers={"Origin": ALLOWED_ORIGINS[0]})

    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGINS[0]

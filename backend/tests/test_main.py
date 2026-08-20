from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app

SOUND_FILES = [
    "betting-1.mp3",
    "betting-2.mp3",
    "betting-3.mp3",
    "cards.mp3",
    "crowd-gasp.mp3",
    "folding.mp3",
]

AVATAR_FILES = [
    "claude.png",
    "gpt.png",
    "deepseek.png",
    "gemini.png",
    "grok.png",
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("filename", SOUND_FILES)
def test_sound_effect_files_are_served(client: TestClient, filename: str) -> None:
    resp = client.get(f"/sounds/{filename}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert len(resp.content) > 0


def test_unknown_sound_file_is_404(client: TestClient) -> None:
    resp = client.get("/sounds/does-not-exist.mp3")
    assert resp.status_code == 404


@pytest.mark.parametrize("filename", AVATAR_FILES)
def test_avatar_files_are_served(client: TestClient, filename: str) -> None:
    resp = client.get(f"/images/{filename}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert len(resp.content) > 0


def test_unknown_avatar_file_is_404(client: TestClient) -> None:
    resp = client.get("/images/does-not-exist.png")
    assert resp.status_code == 404

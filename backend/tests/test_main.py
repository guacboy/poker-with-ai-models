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
    "check.mp3",
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


def test_new_tournament_defaults_to_a_real_non_debug_session(client: TestClient) -> None:
    resp = client.post("/tournament/new", json={"human_name": "Dylan"})
    assert resp.status_code == 200
    assert resp.json()["is_debug"] is False


def test_new_tournament_with_debug_flag_creates_a_debug_session(client: TestClient) -> None:
    resp = client.post("/tournament/new", json={"human_name": "Dylan", "debug": True})
    assert resp.status_code == 200
    assert resp.json()["is_debug"] is True


def test_debug_endpoints_reject_a_real_tournament(client: TestClient) -> None:
    tid = client.post("/tournament/new", json={"human_name": "Dylan"}).json()["tournament_id"]

    resp = client.post(f"/tournament/{tid}/debug/forced_action", json={"mode": "fold"})
    assert resp.status_code == 403

    resp = client.post(f"/tournament/{tid}/debug/always_show_hands", json={"enabled": True})
    assert resp.status_code == 403

    resp = client.post(f"/tournament/{tid}/debug/force_dialogue", json={"enabled": True})
    assert resp.status_code == 403

    resp = client.post(f"/tournament/{tid}/debug/end_round")
    assert resp.status_code == 403


def test_debug_endpoints_work_on_a_debug_tournament(client: TestClient) -> None:
    tid = client.post("/tournament/new", json={"human_name": "Dylan", "debug": True}).json()["tournament_id"]

    resp = client.post(f"/tournament/{tid}/debug/forced_action", json={"mode": "all_in"})
    assert resp.status_code == 200

    resp = client.post(f"/tournament/{tid}/debug/forced_action", json={"mode": "not-a-real-mode"})
    assert resp.status_code == 400

    resp = client.post(f"/tournament/{tid}/debug/always_show_hands", json={"enabled": True})
    assert resp.status_code == 200

    resp = client.post(f"/tournament/{tid}/debug/force_dialogue", json={"enabled": True})
    assert resp.status_code == 200

    resp = client.post(f"/tournament/{tid}/debug/end_round")
    assert resp.status_code == 200

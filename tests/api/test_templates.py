"""Catalog endpoint tests (PR 4).

GET /api/templates / /api/voices / /api/caption-styles are public,
no auth needed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_templates_returns_phase1_four(client: TestClient):
    res = client.get("/api/templates")
    assert res.status_code == 200
    body = res.json()
    ids = sorted(t["template_id"] for t in body)
    assert ids == ["ai_story", "auto_captions", "reddit_story", "voiceover"]


def test_each_template_has_input_schema(client: TestClient):
    res = client.get("/api/templates")
    body = res.json()
    for t in body:
        schema = t.get("input_schema")
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        assert "properties" in schema
        # Required fields are template-specific but always non-empty for P1.
        assert "required" in schema
        assert len(schema["required"]) >= 1


def test_plan_preview_flag_set_correctly(client: TestClient):
    res = client.get("/api/templates")
    by_id = {t["template_id"]: t for t in res.json()}
    assert by_id["ai_story"]["has_plan_preview"] is True
    assert by_id["reddit_story"]["has_plan_preview"] is True
    assert by_id["voiceover"]["has_plan_preview"] is False
    assert by_id["auto_captions"]["has_plan_preview"] is False


def test_voices_returns_curated_list(client: TestClient):
    res = client.get("/api/voices")
    assert res.status_code == 200
    body = res.json()
    assert len(body) >= 4
    # Default voice is flagged.
    defaults = [v for v in body if v.get("is_default")]
    assert len(defaults) == 1
    assert defaults[0]["id"] == "en-US-AriaNeural"


def test_caption_styles_match_engine(client: TestClient):
    from xvideo.prompt_native import CAPTION_STYLES

    res = client.get("/api/caption-styles")
    assert res.status_code == 200
    body = res.json()
    ids = [s["id"] for s in body]
    assert ids == list(CAPTION_STYLES)
    # Each entry maps each known format to bool.
    for s in body:
        assert set(s["default_for_format"].keys()) == {
            "shorts_clean", "tiktok_fast", "reels_aesthetic",
        }

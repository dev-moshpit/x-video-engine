"""Director tests — public API contract."""

from __future__ import annotations

import pytest

from xvideo.prompt_native import (
    available_themes,
    detect_theme,
    generate_variations,
    generate_video_plan,
)
from xvideo.prompt_native.scoring import plan_meets_thresholds, score_plan


def test_generate_video_plan_returns_list():
    """Spec signature: returns ``list[VideoPlan]`` even for variations=1."""
    plans = generate_video_plan("discipline", variations=1)
    assert isinstance(plans, list)
    assert len(plans) == 1
    plans3 = generate_video_plan("discipline", variations=3)
    assert isinstance(plans3, list)
    assert len(plans3) == 3


def test_generate_video_plan_invalid_variations():
    with pytest.raises(ValueError):
        generate_video_plan("discipline", variations=0)


def test_generate_variations_alias():
    a = generate_variations("discipline", n=2, seed=42)
    b = generate_video_plan("discipline", variations=2, seed=42)
    # Both APIs should produce identical plans.
    assert [p.title for p in a] == [p.title for p in b]


def test_generate_video_plan_handles_messy_prompt():
    """Sanitizer should accept whitespace / control chars without crashing."""
    plans = generate_video_plan("  Make    a  motivational \t  video  \n\n",
                                   variations=1, seed=1)
    assert plans[0].user_prompt.strip() == plans[0].user_prompt


def test_format_drives_duration_window():
    p_short = generate_video_plan("discipline", variations=1, seed=1,
                                      platform="tiktok_fast")[0]
    p_reels = generate_video_plan("discipline", variations=1, seed=1,
                                      platform="reels_aesthetic")[0]
    # tiktok_fast default is 15s; reels_aesthetic 18s
    assert p_short.duration_target == 15.0
    assert p_reels.duration_target == 18.0
    assert p_short.format_name == "tiktok_fast"
    assert p_reels.format_name == "reels_aesthetic"


def test_explicit_duration_override():
    p = generate_video_plan("discipline", variations=1, seed=1,
                                duration=12.0)[0]
    assert p.duration_target == 12.0


def test_style_preference_is_layered():
    """Style cue should be applied — neon_arcade visual style for 'neon'."""
    p = generate_video_plan("loop", variations=1, seed=1,
                                style="neon")[0]
    assert p.visual_style == "neon_arcade" or p.color_palette == "neon"


def test_available_themes_listed():
    themes = available_themes()
    assert "motivation" in themes
    assert "mystery" in themes
    assert "ai_tech" in themes
    assert "product" in themes
    assert "ambient" in themes
    assert len(themes) >= 5


def test_detect_theme_routes_keywords():
    assert detect_theme("Make a motivational video about discipline") == "motivation"
    assert detect_theme("AI is replacing boring work") == "ai_tech"
    assert detect_theme("an unsolved cold case mystery") == "mystery"
    assert detect_theme("luxury watch product launch") == "product"


def test_score_and_filter_does_not_crash():
    """Smoke test the scoring path with regenerate enabled."""
    plans = generate_video_plan("discipline", variations=2,
                                   seed=42, score_and_filter=True)
    assert len(plans) == 2
    for p in plans:
        s = score_plan(p)
        # We don't assert pass — the scorer is heuristic. We just want
        # the path to run cleanly and produce a numeric score.
        assert 0 <= s.total <= 100

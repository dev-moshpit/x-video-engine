"""Scoring tests — heuristic plan QA + thresholds."""

from __future__ import annotations

from dataclasses import replace

from xvideo.prompt_native import (
    DEFAULT_THRESHOLDS,
    generate_video_plan,
    plan_meets_thresholds,
    score_plan,
)


def test_score_plan_returns_all_dimensions():
    plan = generate_video_plan("discipline", variations=1, seed=42)[0]
    score = score_plan(plan)
    for dim in (
        "hook_strength", "visual_uniqueness", "scene_variety",
        "emotional_clarity", "caption_punch", "prompt_relevance",
        "platform_fit", "coherence", "cta_fit", "safety",
    ):
        v = getattr(score, dim)
        assert 0.0 <= v <= 10.0, f"{dim} out of range: {v}"
    assert 0.0 <= score.total <= 100.0


def test_score_plan_typical_director_output_passes_threshold():
    """Plans coming straight out of the director should typically pass.

    The thresholds were chosen against a sample of director output. If
    this regresses, either the director's output got worse or the
    thresholds drifted — both worth investigating.
    """
    plan = generate_video_plan("discipline", variations=1, seed=42)[0]
    score = score_plan(plan)
    assert plan_meets_thresholds(score), (
        f"Director output below threshold: {score.to_dict()}"
    )


def test_plan_meets_thresholds_uses_defaults():
    plan = generate_video_plan("discipline", variations=1, seed=42)[0]
    score = score_plan(plan)
    # With stricter thresholds we should fail; with permissive we should pass.
    permissive = {"min_total": 0.0, "min_hook_strength": 0.0,
                  "min_scene_variety": 0.0}
    strict = {"min_total": 999.0, "min_hook_strength": 99.0,
              "min_scene_variety": 99.0}
    assert plan_meets_thresholds(score, permissive)
    assert not plan_meets_thresholds(score, strict)


def test_default_thresholds_match_spec():
    # Spec: total >= 70, hook >= 7, scene_variety >= 7
    assert DEFAULT_THRESHOLDS["min_total"] == 70.0
    assert DEFAULT_THRESHOLDS["min_hook_strength"] == 7.0
    assert DEFAULT_THRESHOLDS["min_scene_variety"] == 7.0


def test_score_to_dict_includes_total():
    plan = generate_video_plan("discipline", variations=1, seed=42)[0]
    d = score_plan(plan).to_dict()
    assert "total" in d
    assert d["total"] == score_plan(plan).total


def test_empty_hook_destroys_hook_score():
    """A plan with an empty hook should score 0 on hook_strength."""
    plan = generate_video_plan("discipline", variations=1, seed=42)[0]
    plan_bad = replace(plan, hook="")
    s = score_plan(plan_bad)
    assert s.hook_strength == 0.0
    assert not plan_meets_thresholds(s)


def test_safety_penalises_text_tokens_in_visual_prompt():
    """Visual prompts that ask for captions/watermarks should get docked."""
    plan = generate_video_plan("discipline", variations=1, seed=42)[0]
    # Inject a banned token into one scene's prompt
    bad_scene = replace(
        plan.scenes[0],
        visual_prompt=plan.scenes[0].visual_prompt + ", with subtitles burned in",
    )
    bad_plan = replace(plan, scenes=[bad_scene] + list(plan.scenes[1:]))
    s = score_plan(bad_plan)
    assert s.safety < 10.0

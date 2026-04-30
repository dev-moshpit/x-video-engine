"""Variation tests — same prompt → different videos every call (without
seed); same seed → reproducible."""

from __future__ import annotations

import pytest

from xvideo.prompt_native import generate_video_plan
from xvideo.prompt_native.variation_engine import (
    create_variation_id,
    generate_variation_seed,
    mutate_concept,
    mutate_script_angle,
    mutate_visual_world,
)


def test_no_seed_produces_different_plans_across_calls():
    """Two consecutive calls with no seed must yield different concept_seeds.

    This is the core spec promise: NEW PROMPT = NEW VIDEO EVERY TIME.
    """
    a = generate_video_plan("discipline grind", variations=1)[0]
    b = generate_video_plan("discipline grind", variations=1)[0]
    assert a.seed != b.seed, "no-seed calls must produce fresh seeds"


def test_no_seed_5_variations_are_distinct():
    """variations=5 produces 5 distinct seeds (and typically 5 distinct
    concepts) in a single call."""
    plans = generate_video_plan("discipline", variations=5)
    seeds = [p.seed for p in plans]
    assert len(seeds) == 5
    assert len(set(seeds)) == 5, f"expected 5 distinct seeds, got {seeds}"


def test_fixed_seed_is_reproducible():
    """Same seed must reproduce the same plan exactly (title, hook, scenes)."""
    a = generate_video_plan("discipline", variations=1, seed=12345)[0]
    b = generate_video_plan("discipline", variations=1, seed=12345)[0]
    assert a.title == b.title
    assert a.hook == b.hook
    assert a.concept == b.concept
    assert a.cta == b.cta
    assert [s.scene_id for s in a.scenes] == [s.scene_id for s in b.scenes]
    assert [s.visual_prompt for s in a.scenes] == [s.visual_prompt for s in b.scenes]


def test_fixed_seed_5_variations_are_reproducible():
    a = generate_video_plan("discipline", variations=5, seed=42)
    b = generate_video_plan("discipline", variations=5, seed=42)
    for pa, pb in zip(a, b):
        assert pa.title == pb.title and pa.hook == pb.hook
        assert pa.seed == pb.seed
        assert pa.variation_id == pb.variation_id


def test_different_prompts_diverge():
    a = generate_video_plan("Make a motivational video", variations=1, seed=7)[0]
    b = generate_video_plan("Make an AI explainer", variations=1, seed=7)[0]
    assert a.prompt_hash != b.prompt_hash
    # Themes should differ for prompts in clearly different domains
    assert a.theme != b.theme


def test_generate_variation_seed_is_pinned_when_user_seed_passed():
    """generate_variation_seed with a user_seed is deterministic; without it,
    it changes."""
    a = generate_variation_seed("discipline", user_seed=99, variation_id=0)
    b = generate_variation_seed("discipline", user_seed=99, variation_id=0)
    assert a == b
    c = generate_variation_seed("discipline", user_seed=None, variation_id=0)
    d = generate_variation_seed("discipline", user_seed=None, variation_id=0)
    assert c != d  # entropy floor


def test_create_variation_id_is_stable():
    a = create_variation_id("abc", 42)
    b = create_variation_id("abc", 42)
    assert a == b
    c = create_variation_id("abc", 43)
    assert a != c


def test_mutate_concept_changes_plan():
    plan = generate_video_plan("discipline", variations=1, seed=42)[0]
    mutated = mutate_concept(plan)
    # Same prompt + same theme but different seed → different concept body
    assert mutated.user_prompt == plan.user_prompt
    assert mutated.seed != plan.seed
    # The concept text usually differs, though not guaranteed; assert at
    # least one of the major creative axes moved.
    diffs = (
        mutated.concept != plan.concept,
        mutated.hook != plan.hook,
        [s.subject for s in mutated.scenes] != [s.subject for s in plan.scenes],
    )
    assert any(diffs), "mutate_concept should change at least one axis"


def test_mutate_visual_world_and_script_angle_run_clean():
    plan = generate_video_plan("discipline", variations=1, seed=42)[0]
    a = mutate_visual_world(plan)
    b = mutate_script_angle(plan)
    assert a.user_prompt == plan.user_prompt
    assert b.user_prompt == plan.user_prompt
    assert a.seed != plan.seed
    assert b.seed != plan.seed

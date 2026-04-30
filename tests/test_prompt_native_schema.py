"""Schema tests — VideoPlan / Scene / RenderJob shape + projection."""

from __future__ import annotations

import json

import pytest

from xvideo.prompt_native import (
    RenderJob,
    Scene,
    VideoPlan,
    generate_video_plan,
    plan_to_render_jobs,
)


def test_videoplan_has_required_fields():
    """A generated VideoPlan exposes every field the spec lists."""
    plan = generate_video_plan("Make a motivational video about discipline",
                                  variations=1, seed=42)[0]

    # Provenance / identity
    assert plan.user_prompt
    assert plan.prompt_hash
    assert isinstance(plan.variation_id, int)
    assert plan.seed > 0
    assert plan.generation_mode == "prompt_native"

    # Concept side
    assert plan.title
    assert plan.concept
    assert plan.hook
    assert plan.cta
    assert plan.audience
    assert plan.emotional_angle

    # Visual side
    assert plan.visual_style
    assert plan.color_palette
    assert plan.pacing in ("calm", "medium", "energetic")
    assert plan.voice_tone
    assert plan.caption_style
    assert plan.aspect_ratio in ("9:16", "16:9", "1:1")

    # Structure
    assert isinstance(plan.scenes, list)
    assert 3 <= len(plan.scenes) <= 8
    assert isinstance(plan.voiceover_lines, list)
    assert plan.voiceover_lines
    assert plan.negative_prompt


def test_scene_has_required_fields():
    plan = generate_video_plan("discipline", variations=1, seed=1)[0]
    for s in plan.scenes:
        assert isinstance(s, Scene)
        assert s.scene_id
        assert s.duration > 0
        assert s.visual_prompt
        assert s.subject
        assert s.environment
        assert s.camera_motion
        assert s.transition
        # Captions / narrations may be empty strings but must exist as fields
        assert hasattr(s, "narration_line")
        assert hasattr(s, "on_screen_caption")


def test_videoplan_round_trips_to_dict_and_back():
    plan = generate_video_plan("ai history mystery", variations=1, seed=7)[0]
    d = plan.to_dict()
    # Must be json-serializable
    blob = json.dumps(d, default=str)
    reread = json.loads(blob)
    assert reread["title"] == plan.title
    assert reread["seed"] == plan.seed
    assert len(reread["scenes"]) == len(plan.scenes)
    # Every scene should round-trip
    for d_scene, scene in zip(reread["scenes"], plan.scenes):
        assert d_scene["scene_id"] == scene.scene_id
        assert d_scene["visual_prompt"] == scene.visual_prompt


def test_plan_to_render_jobs_projection(tmp_path):
    plan = generate_video_plan("discipline", variations=1, seed=99)[0]
    jobs = plan_to_render_jobs(plan, tmp_path / "clips")

    assert len(jobs) == len(plan.scenes)
    for i, (j, scene) in enumerate(zip(jobs, plan.scenes)):
        assert isinstance(j, RenderJob)
        assert j.scene_id == scene.scene_id
        # Render seed = plan seed + scene index (deterministic + reproducible)
        assert j.seed == plan.seed + i
        assert j.prompt == scene.visual_prompt
        assert j.negative_prompt == plan.negative_prompt
        assert j.duration_seconds == scene.duration
        assert j.camera_motion == scene.camera_motion
        # 9:16 default → 576×1024
        assert j.width == 576
        assert j.height == 1024
        assert j.output_path.endswith(f"{scene.scene_id}_v{plan.variation_id}.mp4")


def test_render_job_round_trips_to_dict():
    plan = generate_video_plan("discipline", variations=1, seed=99)[0]
    jobs = plan_to_render_jobs(plan, "/tmp/x")
    blob = json.dumps([j.to_dict() for j in jobs])
    rt = json.loads(blob)
    assert len(rt) == len(jobs)
    for orig, recon in zip(jobs, rt):
        assert recon["scene_id"] == orig.scene_id
        assert recon["seed"] == orig.seed


def test_no_scene_visual_prompt_contains_text_instructions():
    """Spec: no scene prompt should instruct the image model to render text."""
    plan = generate_video_plan("Make a motivational video", variations=1, seed=11)[0]
    banned = (
        "subtitle", "subtitles", "caption", "captions", "watermark", "logo",
        "title card", "lower third", "on-screen text", "typography",
    )
    for s in plan.scenes:
        body = s.visual_prompt.lower()
        for tok in banned:
            assert tok not in body, (
                f"scene {s.scene_id} visual prompt contains banned token "
                f"{tok!r}: {s.visual_prompt}"
            )


def test_aspect_ratio_overrides_render_size():
    plan = generate_video_plan(
        "ai facts", variations=1, seed=2, aspect_ratio="16:9",
    )[0]
    jobs = plan_to_render_jobs(plan, "/tmp/x")
    assert jobs[0].width == 1024 and jobs[0].height == 576

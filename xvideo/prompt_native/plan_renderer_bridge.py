"""Plan → renderer bridge.

The director and runner already implement scene rendering and final
stitching. This module is the single place callers should touch when
asking "render this plan and give me a finished MP4."

Responsibilities (per the spec):

- Convert ``VideoPlan`` scenes into ``RenderJob`` records (pure data).
- Render each scene clip via ``prompt_video_runner.run_plan``.
- Generate voiceover, captions, hook overlay, optional music bed.
- Composite the final 9:16 MP4.
- Save the full sidecar metadata (with embedded VideoPlan + score).

The new prompt-native CLI uses this module exclusively; the existing
``run_plan`` function still works directly for callers that want the
lower-level entry point (we don't break that).

Also exports ``plan_to_render_jobs`` (re-exported from ``schema`` so
``from xvideo.prompt_native.plan_renderer_bridge import
plan_to_render_jobs`` works for callers that prefer a single import).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from xvideo.prompt_native.schema import (
    RenderJob,
    VideoPlan,
    plan_to_render_jobs,
)

logger = logging.getLogger(__name__)


def render_video_plan(
    plan: VideoPlan,
    output_root: str | Path,
    *,
    batch_name: Optional[str] = None,
    finalize: bool = True,
    want_voice: bool = True,
    want_captions: bool = True,
    want_hook: bool = True,
    voice_name: Optional[str] = None,
    voice_rate: str = "+0%",
    caption_style: Optional[str] = None,
    music_bed: Optional[str] = None,
    music_bed_db: float = -18.0,
    plan_score: Optional[dict] = None,
    backend=None,
):
    """Render a ``VideoPlan`` and return the artifacts.

    Args:
        plan: a ``VideoPlan`` from the director.
        output_root: where to write the batch folder.
        batch_name: optional override for the batch folder name.
        finalize: when False, render scenes only (no TTS, no final MP4).
        want_voice / want_captions / want_hook: post-stage toggles.
        voice_name / voice_rate: edge-tts overrides.
        caption_style: one of ``CAPTION_STYLES`` (e.g. ``"bold_word"``).
            ``None`` keeps the default chosen by the runner.
        music_bed: one of ``"none"`` / ``"auto"`` / a path to an audio
            file. ``"auto"`` picks the first file found in
            ``assets/music/`` matching the plan's pacing tag (or any
            file if no match).
        music_bed_db: bed level under voice in dB (default -18 per spec).
        plan_score: optional ``PlanScore.to_dict()`` to embed in sidecar.
        backend: pre-loaded ``SDXLParallaxBackend``. When rendering a
            batch (--variations N), pass the same backend across calls
            so the SDXL pipeline only loads once. ``None`` triggers a
            fresh load inside ``run_plan``.

    Returns:
        ``PromptNativeArtifacts`` (from ``prompt_video_runner``).
    """
    # Lazy import — pulls in heavy modules (sdxl_parallax, ffmpeg).
    from xvideo.prompt_video_runner import run_plan

    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    # Backwards compatibility: the runner has its own kwargs. We pass
    # through the ones it knows. The new caption_style / music_bed flow
    # is wrapped around the runner so the runner stays focused.
    artifacts = run_plan(
        plan=plan,
        output_root=output_root,
        batch_name=batch_name,
        backend=backend,
        finalize=finalize and (caption_style is None) and (music_bed in (None, "none")),
        voice_name=voice_name,
        voice_rate=voice_rate,
        want_voice=want_voice,
        want_captions=want_captions,
        want_hook=want_hook,
    )

    # Stamp the variation_id and sidecar bookkeeping that the bridge owns.
    sidecar_path = artifacts.batch_dir / "video_plan_sidecar.json"
    sidecar = {
        "generation_mode":  "prompt_native",
        "engine_version":   "prompt_native/1.0",
        "prompt":           plan.user_prompt,
        "prompt_hash":      plan.prompt_hash,
        "variation_id":     plan.variation_id,
        "concept_seed":     plan.seed,
        "platform":         plan.format_name,
        "duration":         plan.duration_target,
        "caption_style":    caption_style,
        "voice":            voice_name,
        "music_bed":        music_bed,
        "music_bed_db":     music_bed_db,
        "video_plan":       plan.to_dict(),
        "scene_count":      len(plan.scenes),
        "render_jobs":      [j.to_dict() for j in plan_to_render_jobs(
                                plan, artifacts.batch_dir / "clips"
                            )],
        "plan_score":       plan_score,
        "final_mp4_path":   str(artifacts.final_mp4) if artifacts.final_mp4 else None,
        "created_at":       time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, default=str), encoding="utf-8",
    )

    # Custom caption style + music bed: re-finalize on top of the runner's
    # rendered scene clips. We only do this when the operator asked for a
    # non-default treatment, because re-finalizing costs a few seconds of
    # ffmpeg work and most operators run with defaults.
    if finalize and (caption_style is not None or music_bed not in (None, "none")):
        try:
            _custom_finalize(
                plan=plan,
                artifacts=artifacts,
                want_voice=want_voice,
                want_captions=want_captions,
                want_hook=want_hook,
                voice_name=voice_name,
                voice_rate=voice_rate,
                caption_style=caption_style,
                music_bed=music_bed,
                music_bed_db=music_bed_db,
            )
        except Exception as e:  # pragma: no cover — keep batch reviewable
            logger.error("custom finalize failed: %s", e, exc_info=True)
            raise

    return artifacts


# ─── Custom finalize (caption style + music bed) ────────────────────────


def _resolve_music_bed(option: Optional[str], plan: VideoPlan) -> Optional[Path]:
    """Resolve --music-bed value to a real file path or None.

    ``"none"``/``None`` → None (no bed).
    ``"auto"``         → pick a file from ``assets/music/`` (first by name).
    Anything else      → treat as a literal path.
    """
    if not option or option == "none":
        return None
    if option == "auto":
        # Project-relative ``assets/music`` is the convention.
        candidates_dir = Path("assets/music")
        if not candidates_dir.exists():
            logger.info("music_bed=auto: no assets/music directory present")
            return None
        files = sorted([
            p for p in candidates_dir.iterdir()
            if p.is_file() and p.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg")
        ])
        if not files:
            logger.info("music_bed=auto: assets/music has no audio files")
            return None
        # Prefer a file whose name matches the plan's pacing or theme.
        for tag in (plan.pacing, plan.theme):
            if not tag:
                continue
            for f in files:
                if tag.lower() in f.stem.lower():
                    return f
        return files[0]
    p = Path(option)
    if p.exists() and p.is_file():
        return p
    logger.warning("music_bed path not found: %s — skipping", option)
    return None


def _custom_finalize(
    *,
    plan: VideoPlan,
    artifacts,
    want_voice: bool,
    want_captions: bool,
    want_hook: bool,
    voice_name: Optional[str],
    voice_rate: str,
    caption_style: Optional[str],
    music_bed: Optional[str],
    music_bed_db: float,
) -> None:
    """Run the final-MP4 stage with caption-style + music-bed overrides.

    This rebuilds the concat / TTS / captions / final MP4 chain, picking
    the right caption-style ASS writer and (optionally) mixing in a music
    bed under voice. The output is written next to the runner's default
    final at a parallel path so the operator can compare.
    """
    from xvideo.post.prompt_video_stitcher import (
        concat_scenes, render_prompt_native_final,
    )
    from xvideo.post.tts import synthesize, voice_for_pack
    from xvideo.prompt_native.caption_style_engine import (
        build_caption_file, default_caption_style_for,
    )
    from xvideo.prompt_native.schema import aspect_to_size
    from xvideo.prompt_video_runner import _full_narration_text

    style_name = caption_style or default_caption_style_for(plan.format_name)
    final_dir = artifacts.batch_dir / "final_exports"
    final_dir.mkdir(parents=True, exist_ok=True)
    base = f"plan_v{plan.variation_id}_{style_name}"

    width, height = aspect_to_size(plan.aspect_ratio)
    concat_path = final_dir / f"{base}_concat.mp4"
    if not artifacts.scene_clips:
        raise RuntimeError("No scene clips to finalize")
    concat_scenes(artifacts.scene_clips, concat_path,
                   width=width, height=height, fps=24)

    voice_path: Optional[Path] = None
    captions_path: Optional[Path] = None
    final_mp4: Optional[Path] = None
    tts_result = None

    if want_voice:
        narration = _full_narration_text(plan)
        if not narration:
            raise ValueError("Plan has no voiceover lines to synthesize")
        chosen_voice = voice_name or voice_for_pack(None)
        voice_path = final_dir / f"{base}_voice.mp3"
        tts_result = synthesize(
            text=narration,
            out_path=voice_path,
            voice=chosen_voice,
            rate=voice_rate,
            want_words=True,  # all caption styles are word-aware
        )

    if want_captions and tts_result and tts_result.words:
        captions_path = final_dir / f"{base}.ass"
        build_caption_file(
            style=style_name,
            words=tts_result.words,
            out_path=captions_path,
            video_width=width, video_height=height,
        )

    if want_voice and voice_path:
        final_mp4 = final_dir / f"{base}_final.mp4"
        target_dur = max(
            tts_result.duration_sec if tts_result else 0.0,
            sum(s.duration for s in plan.scenes),
        )
        bed_path = _resolve_music_bed(music_bed, plan)
        render_prompt_native_final(
            bg_video=concat_path,
            voice_audio=voice_path,
            captions_path=captions_path,
            out_path=final_mp4,
            hook_text=(plan.hook if want_hook else ""),
            target_duration_sec=target_dur,
            music_bed=bed_path,
            music_bed_db=music_bed_db,
        )
        artifacts.final_mp4 = final_mp4
        artifacts.concat_path = concat_path
        artifacts.voice_path = voice_path
        artifacts.captions_path = captions_path


__all__ = [
    "render_video_plan",
    "plan_to_render_jobs",
    "RenderJob",
]

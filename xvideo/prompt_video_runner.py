"""Prompt-native runner: VideoPlan → background scene clips → final MP4.

This is the executor for `prompt_video_director`. It owns the moving
parts the director deliberately stays out of:

    - SDXL-Turbo + parallax (background still + Ken-Burns animation)
    - per-scene sidecar JSON (provenance + reproducibility)
    - manifest.csv compatible with the existing batches dashboard
    - selection.json that auto-stars every scene
    - final stitch: concat scenes, generate one TTS track for the full
      narration, build word-level ASS captions aligned to the TTS
      sentence timeline, overlay the hook, output one MP4

It does NOT replace `xvideo/batch.py`. The pack workflow still uses the
BatchRunner. This runner is a thin, single-purpose path because a
prompt-native plan is a *single* video composed of *N* scenes, not a
batch of N independent variant clips.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from xvideo.prompt_video_director import (
    Scene,
    VideoPlan,
    camera_motion_to_motion_profile,
)

logger = logging.getLogger(__name__)


# ─── Motion profiles ────────────────────────────────────────────────────
# Mirror the operator-facing knobs from configs/shorts_batch.yaml. We
# inline them here so this module stays importable without yaml at parse
# time (the CLI loads the yaml when it has the env to render).

_MOTION_PROFILES = {
    "calm":      {"zoom_range": (1.00, 1.15), "pan_fraction": 0.08, "anim_mode": "ken_burns"},
    "medium":    {"zoom_range": (1.00, 1.25), "pan_fraction": 0.15, "anim_mode": "ken_burns"},
    "energetic": {"zoom_range": (1.00, 1.35), "pan_fraction": 0.22, "anim_mode": "ken_burns"},
}


# ─── Output layout ──────────────────────────────────────────────────────

@dataclass
class PromptNativeArtifacts:
    """File paths produced by `run_plan`."""
    batch_dir: Path
    plan_path: Path
    manifest_path: Path
    scene_clips: list[Path] = field(default_factory=list)
    scene_sidecars: list[Path] = field(default_factory=list)
    concat_path: Optional[Path] = None
    voice_path: Optional[Path] = None
    captions_path: Optional[Path] = None
    final_mp4: Optional[Path] = None


# ─── Scene rendering ────────────────────────────────────────────────────

def _aspect_to_size(aspect: str) -> tuple[int, int]:
    if aspect == "9:16":
        return (576, 1024)
    if aspect == "16:9":
        return (1024, 576)
    return (768, 768)


def _primary_platform(plan: VideoPlan) -> str:
    return {
        "shorts_clean":     "shorts",
        "tiktok_fast":      "tiktok",
        "reels_aesthetic":  "reels",
    }.get(plan.format_name, "shorts")


def _build_publish_block(plan: VideoPlan, scene: Scene, scene_idx: int) -> dict:
    """Synthesize the same `publish` shape that pack mode produces.

    Lets the existing render_final_video.py per-clip finalizer keep working
    on prompt-native scenes if anyone wants to run it that way (it'll
    treat each scene as its own short). The prompt-native finalizer below
    bypasses this and uses the plan's full narration directly.
    """
    primary = _primary_platform(plan)

    base_hashtags = ["#shorts", "#shortvideo", "#lowpoly", "#ai"]
    if plan.theme:
        base_hashtags.append(f"#{plan.theme}")

    caption_lines = [scene.narration_line]
    if scene_idx == len(plan.scenes) - 1 and plan.cta and plan.cta not in caption_lines:
        caption_lines.append(plan.cta)

    return {
        "title":   plan.title,
        "caption": "\n".join(caption_lines),
        "cta":     plan.cta,
        "hashtags": base_hashtags,
        "platforms": {
            primary: {
                "title":   plan.title,
                "caption": "\n".join(caption_lines),
            },
        },
    }


def _render_scene(
    backend,
    plan: VideoPlan,
    scene: Scene,
    scene_idx: int,
    output_dir: Path,
    fps: int = 24,
) -> tuple[Path, Path]:
    """Render one scene to a background clip + sidecar. Returns (clip, sidecar)."""
    from sdxl_parallax.parallax import animate_still, write_video  # local import — heavy

    motion_profile_name = camera_motion_to_motion_profile(scene.camera_motion)
    profile = _MOTION_PROFILES[motion_profile_name]

    out_size = _aspect_to_size(plan.aspect_ratio)
    clip_id = f"{scene.scene_id}_v{plan.variation_id}"
    clip_path = output_dir / f"{clip_id}.mp4"
    sidecar_path = output_dir / f"{clip_id}.meta.json"

    if clip_path.exists() and sidecar_path.exists() and clip_path.stat().st_size > 20_000:
        logger.info("[%s] skip (already rendered)", clip_id)
        return clip_path, sidecar_path

    t_img = time.time()
    image = backend.generate_image(
        prompt=scene.visual_prompt,
        negative_prompt=plan.negative_prompt,
        seed=plan.seed + scene_idx,
        steps=2,
        guidance=0.0,
    )
    image_gen_sec = time.time() - t_img

    frames = animate_still(
        image,
        mode=profile["anim_mode"],
        duration_sec=scene.duration,
        fps=fps,
        out_size=out_size,
        zoom_range=tuple(profile["zoom_range"]),
        pan_fraction=profile["pan_fraction"],
    )
    write_video(frames, str(clip_path), fps=fps)

    # Save keyframe PNG for the gallery
    try:
        import cv2
        from PIL import Image
        Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).save(
            output_dir / f"{clip_id}.png"
        )
    except Exception:
        pass

    sidecar = {
        "spec_id":           clip_id,
        "scene_id":          scene.scene_id,
        "variation_id":      plan.variation_id,
        "concept_seed":      plan.seed,
        "prompt_hash":       plan.prompt_hash,
        "generation_mode":   "prompt_native",
        "user_prompt":       plan.user_prompt,
        "theme":             plan.theme,
        "preset_name":       plan.visual_style,
        "compiled_prompt":   scene.visual_prompt,
        "compiled_negative": plan.negative_prompt,
        "duration_sec":      scene.duration,
        "fps":               fps,
        "resolution":        f"{out_size[0]}x{out_size[1]}",
        "aspect_ratio":      plan.aspect_ratio,
        "real_backend":      f"sdxl-turbo+parallax ({getattr(backend, 'model_id', 'unknown')})",
        "motion":            motion_profile_name,
        "camera_motion":     scene.camera_motion,
        "subject":           scene.subject,
        "environment":       scene.environment,
        "mood":              scene.mood,
        "narration_line":    scene.narration_line,
        "on_screen_caption": scene.on_screen_caption,
        "transition":        scene.transition,
        "image_gen_sec":     round(image_gen_sec, 2),
        "video_plan_title":  plan.title,
        "video_plan_concept": plan.concept,
        "video_plan_hook":   plan.hook,
        "publish":           _build_publish_block(plan, scene, scene_idx),
        "format":            {
            "name":             plan.format_name,
            "primary_platform": _primary_platform(plan),
        },
    }
    sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    return clip_path, sidecar_path


# ─── Manifest ───────────────────────────────────────────────────────────

def _write_manifest(plan: VideoPlan, scenes: list[Scene],
                    clip_paths: list[Path], manifest_path: Path) -> None:
    """Manifest.csv compatible with the Batches dashboard reader."""
    fields = [
        "job_id", "row_id", "subject", "preset", "motion", "seed",
        "duration_sec", "aspect_ratio", "format", "status", "attempts",
        "image_gen_sec", "total_sec", "output_path",
        "title", "caption", "hashtags", "error",
    ]
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for scene, clip in zip(scenes, clip_paths):
            motion_name = camera_motion_to_motion_profile(scene.camera_motion)
            w.writerow([
                clip.stem,
                f"v{plan.variation_id}",
                scene.subject,
                plan.visual_style,
                motion_name,
                plan.seed,
                f"{scene.duration:.2f}",
                plan.aspect_ratio,
                plan.format_name,
                "completed",
                1,
                "0.00",
                f"{scene.duration:.2f}",
                str(clip),
                plan.title[:200],
                scene.narration_line[:500],
                "",
                "",
            ])


def _write_selection(batch_dir: Path, scenes: list[Scene], clip_paths: list[Path]) -> None:
    """Auto-star every scene so anyone hitting the Batches → Final Exports
    page sees the prompt-native batch as ready-to-finalize."""
    sel = {
        "starred": [c.stem for c in clip_paths],
        "rejected": [],
        "batch_name": batch_dir.name,
        "generation_mode": "prompt_native",
    }
    (batch_dir / "selection.json").write_text(
        json.dumps(sel, indent=2), encoding="utf-8"
    )


def _write_stats(batch_dir: Path, plan: VideoPlan, total_sec: float) -> None:
    n = len(plan.scenes)
    stats = {
        "batch_name": batch_dir.name,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_jobs": n,
        "completed": n,
        "failed": 0,
        "skipped_resumed": 0,
        "total_wall_sec": round(total_sec, 2),
        "avg_total_sec": round(total_sec / max(1, n), 2),
        "clips_per_minute": round((n / max(total_sec, 1e-6)) * 60, 2),
        "generation_mode": "prompt_native",
        "video_plan_title": plan.title,
        "theme": plan.theme,
    }
    (batch_dir / "stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf-8"
    )


# ─── Final stitch ───────────────────────────────────────────────────────

def _full_narration_text(plan: VideoPlan) -> str:
    """Build the TTS input from the plan's voiceover lines.

    One line per sentence so edge-tts emits one SentenceBoundary per line.
    That's how the word-caption estimator anchors per-word timing.
    """
    lines = [ln.strip() for ln in plan.voiceover_lines if ln and ln.strip()]
    deduped: list[str] = []
    for ln in lines:
        if not deduped or deduped[-1].lower() != ln.lower():
            # Ensure each line ends in sentence-final punctuation so edge-tts
            # cleanly closes each sentence boundary.
            if not re.search(r"[.!?]$", ln):
                ln = ln + "."
            deduped.append(ln)
    return "\n".join(deduped)


def _finalize_plan(
    plan: VideoPlan,
    scene_clips: list[Path],
    batch_dir: Path,
    voice_name: str | None,
    voice_rate: str,
    want_voice: bool,
    want_captions: bool,
    want_hook: bool,
) -> tuple[Path | None, Path | None, Path | None, Path | None]:
    """Produce the single final MP4 from the rendered scenes.

    Returns (concat_path, voice_path, captions_path, final_mp4) — any of
    which may be None if the corresponding flag is off.
    """
    from xvideo.post.prompt_video_stitcher import (
        concat_scenes, render_prompt_native_final,
    )
    from xvideo.post.tts import synthesize, voice_for_pack
    from xvideo.post.word_captions import build_ass

    final_dir = batch_dir / "final_exports"
    final_dir.mkdir(parents=True, exist_ok=True)
    base = f"plan_v{plan.variation_id}"

    # 1. Concat scenes
    w, h = _aspect_to_size(plan.aspect_ratio)
    concat_path = final_dir / f"{base}_concat.mp4"
    concat_scenes(scene_clips, concat_path, width=w, height=h, fps=24)

    voice_path: Path | None = None
    captions_path: Path | None = None
    final_mp4: Path | None = None
    tts_result = None

    # 2. TTS
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
            want_words=(plan.caption_style == "word"),
        )

    # 3. Captions (word-level ASS)
    if want_captions and tts_result and tts_result.words:
        captions_path = final_dir / f"{base}_word.ass"
        build_ass(
            words=tts_result.words,
            out_path=captions_path,
            video_width=w, video_height=h,
        )

    # 4. Final mux
    if want_voice and voice_path:
        final_mp4 = final_dir / f"{base}_final.mp4"
        target_dur = max(
            tts_result.duration_sec if tts_result else 0.0,
            sum(s.duration for s in plan.scenes),
        )
        render_prompt_native_final(
            bg_video=concat_path,
            voice_audio=voice_path,
            captions_path=captions_path,
            out_path=final_mp4,
            hook_text=(plan.hook if want_hook else ""),
            target_duration_sec=target_dur,
        )

        # Provenance
        meta = {
            "video_plan":       plan.to_dict(),
            "concept_seed":     plan.seed,
            "prompt_hash":      plan.prompt_hash,
            "variation_id":     plan.variation_id,
            "generation_mode":  "prompt_native",
            "scene_clips":      [str(p) for p in scene_clips],
            "concat_path":      str(concat_path),
            "voice_path":       str(voice_path) if voice_path else "",
            "captions_path":    str(captions_path) if captions_path else "",
            "final_clip":       str(final_mp4),
            "voice": {
                "engine":       tts_result.engine if tts_result else None,
                "voice_name":   tts_result.voice if tts_result else None,
                "duration_sec": tts_result.duration_sec if tts_result else None,
            } if tts_result else None,
            "rendered_at":      time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        (final_dir / f"{base}_final_metadata.json").write_text(
            json.dumps(meta, indent=2, default=str), encoding="utf-8"
        )

    return concat_path, voice_path, captions_path, final_mp4


# ─── Entry point ────────────────────────────────────────────────────────

def _ensure_backend(backend):
    if backend is not None:
        return backend
    # Lazy import — only loaded when actually rendering
    from sdxl_parallax.backend import SDXLParallaxBackend
    b = SDXLParallaxBackend()
    b.load()
    return b


def run_plan(
    plan: VideoPlan,
    output_root: Path,
    batch_name: Optional[str] = None,
    backend=None,
    finalize: bool = True,
    voice_name: str | None = None,
    voice_rate: str = "+0%",
    want_voice: bool = True,
    want_captions: bool = True,
    want_hook: bool = True,
) -> PromptNativeArtifacts:
    """Render every scene in a VideoPlan and (optionally) stitch the final MP4.

    Args:
        plan: VideoPlan from `prompt_video_director.generate_video_plan`.
        output_root: base dir for batches (e.g. `cache/batches`).
        batch_name: folder name. Defaults to `prompt_<hash>_v<variation>_<ts>`.
        backend: pre-loaded SDXLParallaxBackend, or None to lazy-load one.
        finalize: when False, only renders scenes and writes the manifest;
            useful when the caller wants to inspect plan + clips before
            paying for the TTS round-trip.

    Returns:
        PromptNativeArtifacts with all written paths.
    """
    output_root = Path(output_root)
    if batch_name is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        batch_name = f"prompt_{plan.prompt_hash[:8]}_v{plan.variation_id}_{ts}"
    batch_dir = output_root / batch_name
    clips_dir = batch_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    # Persist the full plan immediately so a crash mid-render still leaves
    # a recoverable record of the creative direction.
    plan_path = batch_dir / "video_plan.json"
    plan_path.write_text(json.dumps(plan.to_dict(), indent=2, default=str),
                          encoding="utf-8")

    artifacts = PromptNativeArtifacts(
        batch_dir=batch_dir,
        plan_path=plan_path,
        manifest_path=batch_dir / "manifest.csv",
    )

    backend = _ensure_backend(backend)
    t0 = time.time()
    for i, scene in enumerate(plan.scenes):
        logger.info("[%s] scene %d/%d  preset=%s motion=%s",
                     batch_name, i + 1, len(plan.scenes),
                     plan.visual_style, camera_motion_to_motion_profile(scene.camera_motion))
        clip, sidecar = _render_scene(backend, plan, scene, i, clips_dir)
        artifacts.scene_clips.append(clip)
        artifacts.scene_sidecars.append(sidecar)

    total_sec = time.time() - t0
    _write_manifest(plan, plan.scenes, artifacts.scene_clips, artifacts.manifest_path)
    _write_selection(batch_dir, plan.scenes, artifacts.scene_clips)
    _write_stats(batch_dir, plan, total_sec)

    if finalize:
        try:
            concat, voice, caps, final = _finalize_plan(
                plan, artifacts.scene_clips, batch_dir,
                voice_name=voice_name, voice_rate=voice_rate,
                want_voice=want_voice, want_captions=want_captions,
                want_hook=want_hook,
            )
            artifacts.concat_path = concat
            artifacts.voice_path = voice
            artifacts.captions_path = caps
            artifacts.final_mp4 = final
        except Exception as e:
            logger.error("Finalize failed: %s", e, exc_info=True)
            raise

    return artifacts

"""Shared helpers for the post-stack adapters.

The voiceover and auto_captions adapters share most of their pipeline
(TTS → word captions → solid bg → ffmpeg compose). Both call into
``render_script_with_solid_bg`` here so we don't duplicate the wiring.

The plan-driven adapters (ai_story, reddit_story) do NOT use this —
they go through ``xvideo.prompt_native.plan_renderer_bridge.render_video_plan``
which owns its own concat / TTS / captions / mux pipeline.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

import imageio_ffmpeg

from xvideo.post.prompt_video_stitcher import render_prompt_native_final
from xvideo.post.tts import synthesize, voice_for_pack
from xvideo.post.word_captions import build_ass
from xvideo.prompt_native.schema import aspect_to_size


logger = logging.getLogger(__name__)


def make_solid_color_background(
    *,
    color: str,
    duration_sec: float,
    size: tuple[int, int],
    out_path: Path,
    fps: int = 24,
) -> Path:
    """Render a solid-color mp4 of the given size+duration via ffmpeg lavfi.

    Used as the visual background for Voiceover and Auto-Captions when the
    operator hasn't supplied an uploaded clip. ``color`` is a hex string
    like ``#0b0b0f`` — we strip the leading ``#`` for ffmpeg's ``color``
    source filter.
    """
    width, height = size
    if color.startswith("#"):
        color = color[1:]

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x{color}:s={width}x{height}:d={duration_sec:.2f}:r={fps}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    logger.info("solid_bg: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg solid-bg failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-2000:]}"
        )
    if not out_path.exists() or out_path.stat().st_size < 1_000:
        raise RuntimeError(f"solid-bg produced empty/tiny output: {out_path}")
    return out_path


def render_script_with_solid_bg(
    *,
    script: str,
    voice_name: Optional[str],
    aspect: str,
    background_color: str,
    work_dir: Path,
    base: str = "final",
) -> Path:
    """End-to-end: script → TTS → word captions → solid bg → final MP4.

    Shared by the Voiceover and Auto-Captions adapters. Returns the path
    to the final MP4 written under ``work_dir``.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    width, height = aspect_to_size(aspect)

    # 1. TTS — edge-tts with word-event timing for the ASS captions.
    voice_path = work_dir / f"{base}_voice.mp3"
    chosen_voice = voice_name or voice_for_pack(None)
    tts = synthesize(
        text=script,
        out_path=voice_path,
        voice=chosen_voice,
        want_words=True,
    )
    if not tts.words:
        raise RuntimeError("TTS produced no word events — captions impossible")

    # 2. Captions — word-level ASS file.
    captions_path = work_dir / f"{base}_captions.ass"
    build_ass(
        words=tts.words,
        out_path=captions_path,
        video_width=width,
        video_height=height,
    )

    # 3. Solid-color background mp4 for the duration of the voice track.
    bg_path = work_dir / f"{base}_bg.mp4"
    make_solid_color_background(
        color=background_color,
        duration_sec=tts.duration_sec,
        size=(width, height),
        out_path=bg_path,
    )

    # 4. Compose — uses the same final-mux helper the prompt-native path uses.
    final_path = work_dir / f"{base}.mp4"
    render_prompt_native_final(
        bg_video=bg_path,
        voice_audio=voice_path,
        captions_path=captions_path,
        out_path=final_path,
        hook_text="",
        target_duration_sec=tts.duration_sec,
    )
    return final_path

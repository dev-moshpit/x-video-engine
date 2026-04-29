"""Render a static PNG overlay over a TTS-driven background, then mux.

Phase 2 templates ``would_you_rather``, ``twitter``, ``top_five``, and
``roblox_rant`` all share the same final pipeline:

  1. Render UI panels to PNG via Pillow.
  2. Build a frame timeline (one or more PNGs with per-beat durations).
  3. Encode that to an mp4 (the "background").
  4. Run TTS on a script + word-level captions.
  5. Mux via the existing ``render_prompt_native_final``.

This module wraps step 3-5 so each new adapter only writes the script
+ frame timeline and calls :func:`render_overlay_with_voice`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from xvideo.post.tts import synthesize, voice_for_pack
from xvideo.post.prompt_video_stitcher import render_prompt_native_final

from apps.worker.render_adapters._captions import write_caption_file
from apps.worker.render_adapters._common import (
    blend_video_overlay,
    make_media_background,
)
from apps.worker.render_adapters._image_seq import (
    Frame,
    encode_frame_sequence,
    stretch_frames_to_duration,
    total_duration,
)


logger = logging.getLogger(__name__)


def render_overlay_with_voice(
    *,
    frames: list[Frame],
    script: str,
    voice_name: Optional[str],
    caption_style: Optional[str],
    size: tuple[int, int],
    work_dir: Path,
    base: str,
    speech_rate: str = "+0%",
    background_url: Optional[str] = None,
    overlay_opacity: float = 0.94,
) -> Path:
    """Encode ``frames`` → mp4, synth TTS for ``script``, mux into final.

    ``base`` is the filename stem ("twitter", "top_five", …) used for
    intermediate artifact paths so several adapters can write into the
    same work_dir without colliding.
    """
    work_dir.mkdir(parents=True, exist_ok=True)

    # Synthesize TTS first so we can stretch the visual timeline to cover
    # the narration. Without this, narration that runs longer than the
    # natural panel pacing leaves the final mp4 with audio playing over a
    # frozen / cut visual track (caught in QA — top_five 9s frames vs
    # 22.4s narration).
    voice_path = work_dir / f"{base}_voice.mp3"
    chosen_voice = voice_name or voice_for_pack(None)
    tts = synthesize(
        text=script,
        out_path=voice_path,
        voice=chosen_voice,
        rate=speech_rate,
        want_words=True,
    )

    visual_target = tts.duration_sec + 0.4
    frames = stretch_frames_to_duration(frames, visual_target)

    overlay_video = encode_frame_sequence(
        frames=frames,
        out_path=work_dir / f"{base}_bg.mp4",
        size=size,
    )

    captions_path: Optional[Path] = None
    if tts.words and caption_style is not None:
        captions_path = write_caption_file(
            words=tts.words,
            out_path=work_dir / f"{base}_captions.ass",
            style=caption_style,
            size=size,
        )

    target_duration = max(visual_target, total_duration(frames))
    bg_video = overlay_video
    media_bg = make_media_background(
        background_url=background_url,
        duration_sec=target_duration,
        size=size,
        work_dir=work_dir,
        base=base,
    )
    if media_bg is not None:
        bg_video = blend_video_overlay(
            background_video=media_bg,
            overlay_video=overlay_video,
            out_path=work_dir / f"{base}_composited_bg.mp4",
            duration_sec=target_duration,
            opacity=overlay_opacity,
        )

    final_path = work_dir / f"{base}.mp4"
    render_prompt_native_final(
        bg_video=bg_video,
        voice_audio=voice_path,
        captions_path=captions_path,
        out_path=final_path,
        hook_text="",
        target_duration_sec=tts.duration_sec,
    )
    return final_path

"""Roblox Rant adapter.

Fast-paced rant over a (preferably) gameplay background. If
``background_url`` resolves to a local mp4 we use it as the bg video;
otherwise we fall back to a solid-color panel. TTS rate is bumped via
the schema's ``speech_rate`` (default ``+15%``) and captions default
to ``impact_uppercase`` for max readability at speed.
"""

from __future__ import annotations

from pathlib import Path

from xvideo.prompt_native.schema import aspect_to_size

from apps.worker.render_adapters._common import render_script_with_solid_bg
from apps.worker.render_adapters._video_input import resolve_video_input
from apps.worker.template_inputs import RobloxRantInput

import logging
import subprocess

import imageio_ffmpeg

from xvideo.post.tts import synthesize, voice_for_pack
from xvideo.post.word_captions import build_ass
from xvideo.post.prompt_video_stitcher import render_prompt_native_final


logger = logging.getLogger(__name__)


def _scaled_bg(
    src: Path, size: tuple[int, int], out_path: Path, target_dur: float,
) -> Path:
    """Scale + center-crop ``src`` to ``size`` and trim/loop to ``target_dur``.

    Loops with ``-stream_loop -1`` so a short gameplay snippet covers a
    long rant without an obvious cut.
    """
    width, height = size
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-stream_loop", "-1",
        "-i", str(src),
        "-vf",
        (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        ),
        "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-t", f"{target_dur:.2f}",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"roblox_rant bg-scale failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-1500:]}"
        )
    return out_path


def render(input: RobloxRantInput, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    size = aspect_to_size(input.aspect)

    bg_upload = resolve_video_input(input.background_url, work_dir)

    # No background video uploaded — same path as voiceover/auto_captions.
    if bg_upload is None:
        return render_script_with_solid_bg(
            script=input.script,
            voice_name=input.voice_name,
            aspect=input.aspect,
            background_color=input.background_color,
            work_dir=work_dir,
            base="roblox_rant",
        )

    # Voiced + uploaded-bg path.
    voice_path = work_dir / "roblox_rant_voice.mp3"
    chosen_voice = input.voice_name or voice_for_pack(None)
    tts = synthesize(
        text=input.script,
        out_path=voice_path,
        voice=chosen_voice,
        rate=input.speech_rate,
        want_words=True,
    )

    captions_path: Path | None = None
    if tts.words:
        captions_path = work_dir / "roblox_rant_captions.ass"
        build_ass(
            words=tts.words,
            out_path=captions_path,
            video_width=size[0],
            video_height=size[1],
        )

    bg_path = _scaled_bg(
        bg_upload,
        size=size,
        out_path=work_dir / "roblox_rant_bg.mp4",
        target_dur=tts.duration_sec + 0.4,
    )

    final_path = work_dir / "roblox_rant.mp4"
    render_prompt_native_final(
        bg_video=bg_path,
        voice_audio=voice_path,
        captions_path=captions_path,
        out_path=final_path,
        hook_text="",
        target_duration_sec=tts.duration_sec,
    )
    return final_path

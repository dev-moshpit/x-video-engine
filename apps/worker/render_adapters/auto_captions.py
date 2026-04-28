"""Auto-Captions Video adapter.

Phase 1 was script-only — TTS the script, build word captions, mux over
a solid-color background. Phase 2 adds an upload path: when
``audio_url`` or ``video_url`` is set on the input, the worker
downloads the media, runs faster-whisper transcription, and burns the
resulting word-timed captions over the original audio. The script is
ignored on the upload path.

Decision matrix:

    audio_url  video_url  →  audio source            captions source
    ─────────────────────    ─────────────────────   ─────────────────
    set        unset       →  audio download         whisper(audio)
    unset      set         →  extracted from video   whisper(video)
    set        set         →  audio download         whisper(audio)
                              (video is unused — operator can drop one)
    unset      unset       →  edge-tts(script)       syllable-est(script)

Background:
  - script path          → solid color (existing post stack)
  - upload path          → user's video if video_url, else solid color
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import imageio_ffmpeg

from xvideo.post.prompt_video_stitcher import render_prompt_native_final
from xvideo.post.word_captions import build_ass
from xvideo.prompt_native.schema import aspect_to_size

from apps.worker.render_adapters._common import render_script_with_solid_bg
from apps.worker.render_adapters._video_input import (
    resolve_media_input,
    resolve_video_input,
)
from apps.worker.template_inputs import AutoCaptionsInput


logger = logging.getLogger(__name__)


def _scaled_video_bg(
    src: Path, size: tuple[int, int], out_path: Path, target_dur: float,
) -> Path:
    """Scale + center-crop ``src`` to ``size`` and trim to ``target_dur``.

    Mirrors the helper in roblox_rant — kept here as a private copy so
    the two adapters stay independent (changes here shouldn't ripple).
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
            f"auto_captions bg-scale failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-1500:]}"
        )
    return out_path


def _make_solid_bg(
    color: str, size: tuple[int, int], duration: float, out_path: Path,
) -> Path:
    width, height = size
    if color.startswith("#"):
        color = color[1:]
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x{color}:s={width}x{height}:d={duration:.2f}:r=24",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"solid-bg failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-1500:]}"
        )
    return out_path


def _try_whisper_path(
    input: AutoCaptionsInput, work_dir: Path,
) -> Path | None:
    """Run the upload-+-Whisper path. Returns None if no upload is usable
    or faster-whisper isn't installed — caller falls back to TTS path.
    """
    audio_src = resolve_media_input(input.audio_url, work_dir)
    video_src = resolve_video_input(input.video_url, work_dir)
    media = audio_src or video_src
    if media is None:
        return None

    # Lazy import — keeps faster-whisper out of the script-only path.
    from apps.worker.render_adapters._whisper import (
        WhisperUnavailable,
        transcribe_to_words,
    )

    try:
        audio_wav, duration, words = transcribe_to_words(
            media=media,
            language=input.language,
            work_dir=work_dir,
        )
    except WhisperUnavailable as exc:
        logger.warning(
            "auto_captions: faster-whisper unavailable, falling back to "
            "script TTS path: %s", exc,
        )
        return None
    except Exception as exc:
        logger.warning(
            "auto_captions: whisper transcription failed (%s), falling "
            "back to script TTS path", exc,
        )
        return None

    if not words or duration <= 0.0:
        logger.warning(
            "auto_captions: whisper returned no words; falling back to "
            "script TTS path",
        )
        return None

    size = aspect_to_size(input.aspect)
    captions_path = work_dir / "auto_captions_captions.ass"
    build_ass(
        words=words,
        out_path=captions_path,
        video_width=size[0],
        video_height=size[1],
    )

    # Background: user's video if they uploaded one (re-cropped to aspect),
    # else a solid color matching their pick.
    if video_src is not None:
        bg_path = _scaled_video_bg(
            video_src, size,
            out_path=work_dir / "auto_captions_bg.mp4",
            target_dur=duration + 0.4,
        )
    else:
        bg_path = _make_solid_bg(
            input.background_color, size, duration + 0.4,
            out_path=work_dir / "auto_captions_bg.mp4",
        )

    final_path = work_dir / "auto_captions.mp4"
    render_prompt_native_final(
        bg_video=bg_path,
        voice_audio=audio_wav,
        captions_path=captions_path,
        out_path=final_path,
        hook_text="",
        target_duration_sec=duration,
    )
    return final_path


def render(input: AutoCaptionsInput, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    upload_result = _try_whisper_path(input, work_dir)
    if upload_result is not None:
        return upload_result

    return render_script_with_solid_bg(
        script=input.script,
        voice_name=input.voice_name,
        aspect=input.aspect,
        background_color=input.background_color,
        work_dir=work_dir,
        base="auto_captions",
    )

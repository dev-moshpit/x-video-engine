"""Shared helpers for post-stack worker adapters."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

import imageio_ffmpeg

from xvideo.post.prompt_video_stitcher import render_prompt_native_final
from xvideo.post.tts import synthesize, voice_for_pack
from xvideo.prompt_native.schema import aspect_to_size

from apps.worker.render_adapters._captions import write_caption_file
from apps.worker.render_adapters._video_input import (
    resolve_image_input,
    resolve_video_input,
)


logger = logging.getLogger(__name__)


def make_solid_color_background(
    *,
    color: str,
    duration_sec: float,
    size: tuple[int, int],
    out_path: Path,
    fps: int = 24,
) -> Path:
    """Render a solid-color mp4 of the given size and duration."""
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


def make_video_background(
    *,
    src: Path,
    duration_sec: float,
    size: tuple[int, int],
    out_path: Path,
    fps: int = 24,
) -> Path:
    """Scale, center-crop, loop, and trim a video background."""
    width, height = size
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-stream_loop", "-1",
        "-i", str(src),
        "-vf",
        (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},setsar=1"
        ),
        "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-t", f"{duration_sec:.2f}",
        str(out_path),
    ]
    logger.info("video_bg: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg video-bg failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-2000:]}"
        )
    if not out_path.exists() or out_path.stat().st_size < 1_000:
        raise RuntimeError(f"video-bg produced empty/tiny output: {out_path}")
    return out_path


def make_image_background(
    *,
    src: Path,
    duration_sec: float,
    size: tuple[int, int],
    out_path: Path,
    fps: int = 24,
) -> Path:
    """Scale and center-crop a still image into a video background."""
    width, height = size
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-loop", "1",
        "-i", str(src),
        "-vf",
        (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},setsar=1"
        ),
        "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-t", f"{duration_sec:.2f}",
        str(out_path),
    ]
    logger.info("image_bg: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg image-bg failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-2000:]}"
        )
    if not out_path.exists() or out_path.stat().st_size < 1_000:
        raise RuntimeError(f"image-bg produced empty/tiny output: {out_path}")
    return out_path


def make_media_background(
    *,
    background_url: Optional[str],
    duration_sec: float,
    size: tuple[int, int],
    work_dir: Path,
    base: str,
) -> Optional[Path]:
    """Resolve a video/image URL and render it as a normalized background.

    Returns ``None`` when the URL is empty or cannot be resolved, letting
    callers keep their existing solid/frame-sequence fallback.
    """
    bg_video = resolve_video_input(background_url, work_dir)
    bg_image = None if bg_video is not None else resolve_image_input(background_url, work_dir)
    if bg_video is None and bg_image is None:
        return None

    out_path = work_dir / f"{base}_media_bg.mp4"
    if bg_video is not None:
        try:
            return make_video_background(
                src=bg_video,
                duration_sec=duration_sec,
                size=size,
                out_path=out_path,
            )
        except RuntimeError as exc:
            logger.warning("video background failed, trying image path: %s", exc)
            bg_image = resolve_image_input(background_url, work_dir)
            if bg_image is None:
                return None
    assert bg_image is not None
    return make_image_background(
        src=bg_image,
        duration_sec=duration_sec,
        size=size,
        out_path=out_path,
    )


def blend_video_overlay(
    *,
    background_video: Path,
    overlay_video: Path,
    out_path: Path,
    duration_sec: float,
    opacity: float = 0.94,
    fps: int = 24,
) -> Path:
    """Composite a full-frame template video over a moving/still background."""
    opacity = min(max(opacity, 0.0), 1.0)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-i", str(background_video),
        "-i", str(overlay_video),
        "-filter_complex",
        (
            "[0:v]setpts=PTS-STARTPTS[bg];"
            f"[1:v]setpts=PTS-STARTPTS,format=rgba,"
            f"colorchannelmixer=aa={opacity:.3f}[ov];"
            f"[bg][ov]overlay=0:0:format=auto,fps={fps},setsar=1[v]"
        ),
        "-map", "[v]",
        "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-t", f"{duration_sec:.2f}",
        str(out_path),
    ]
    logger.info("blend_overlay: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg blend-overlay failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-2000:]}"
        )
    if not out_path.exists() or out_path.stat().st_size < 1_000:
        raise RuntimeError(f"blend-overlay produced empty/tiny output: {out_path}")
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
    """Backward-compatible wrapper for solid-background renders."""
    return render_script_with_background(
        script=script,
        voice_name=voice_name,
        aspect=aspect,
        background_color=background_color,
        background_url=None,
        caption_style="bold_word",
        work_dir=work_dir,
        base=base,
    )


def render_script_with_background(
    *,
    script: str,
    voice_name: Optional[str],
    aspect: str,
    background_color: str,
    background_url: Optional[str],
    caption_style: Optional[str],
    work_dir: Path,
    base: str = "final",
    speech_rate: str = "+0%",
    default_caption_style: str = "bold_word",
) -> Path:
    """Render a script over uploaded video/image or a solid fallback."""
    work_dir.mkdir(parents=True, exist_ok=True)
    size = aspect_to_size(aspect)

    voice_path = work_dir / f"{base}_voice.mp3"
    chosen_voice = voice_name or voice_for_pack(None)
    tts = synthesize(
        text=script,
        out_path=voice_path,
        voice=chosen_voice,
        rate=speech_rate,
        want_words=True,
    )
    if not tts.words:
        raise RuntimeError("TTS produced no word events; captions impossible")

    captions_path = write_caption_file(
        words=tts.words,
        out_path=work_dir / f"{base}_captions.ass",
        style=caption_style,
        size=size,
        default_style=default_caption_style,
    )

    bg_path = work_dir / f"{base}_bg.mp4"
    bg_video = resolve_video_input(background_url, work_dir)
    bg_image = None if bg_video is not None else resolve_image_input(background_url, work_dir)
    if bg_video is not None:
        make_video_background(
            src=bg_video,
            duration_sec=tts.duration_sec + 0.4,
            size=size,
            out_path=bg_path,
        )
    elif bg_image is not None:
        make_image_background(
            src=bg_image,
            duration_sec=tts.duration_sec + 0.4,
            size=size,
            out_path=bg_path,
        )
    else:
        make_solid_color_background(
            color=background_color,
            duration_sec=tts.duration_sec + 0.4,
            size=size,
            out_path=bg_path,
        )

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

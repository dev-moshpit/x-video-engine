"""Prompt-native final-MP4 stitcher.

Different from `xvideo/post/ffmpeg_render.py` (which produces ONE final MP4
from ONE background clip). This module takes a list of scene clips (one
per Scene in a VideoPlan), concatenates them into a single timeline, then
adds the same voiceover + word-captions + hook overlay treatment.

Pipeline:
    [scene_01.mp4, scene_02.mp4, ...]  →  concat (re-encoded, vertical safe)
    full narration string              →  TTS MP3 + sentence boundaries
    (sentences, plan.voiceover_lines)  →  word-level ASS captions
    plan.hook                          →  drawtext overlay (first ~2.5s)
                                       ↓
                            single final MP4 (H.264/AAC)

Re-encoding during concat keeps audio/video parameters consistent across
heterogeneous source clips — the alternative (concat demuxer + stream
copy) breaks if any scene was rendered with slightly different timebase
or pix_fmt.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Iterable

import imageio_ffmpeg

from xvideo.post.ffmpeg_render import (
    DEFAULT_SUBTITLE_STYLE,
    RenderOptions,
    _escape_for_filter,
    _hook_drawtext,
    _subtitles_filter,
    probe_duration,
)

logger = logging.getLogger(__name__)


def _ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def concat_scenes(scene_clips: list[Path], out_path: Path,
                   width: int = 576, height: int = 1024, fps: int = 24) -> Path:
    """Concatenate scene clips into one mp4 at the given resolution.

    Uses the concat filter (re-encode) so heterogenous inputs compose
    cleanly. Output is silent (we mux voice in the final pass).
    """
    if not scene_clips:
        raise ValueError("scene_clips is empty")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    inputs: list[str] = []
    for clip in scene_clips:
        inputs += ["-i", str(clip)]

    # Build filter graph: scale + setsar each input, then concat.
    parts = []
    for i in range(len(scene_clips)):
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={fps}[v{i}]"
        )
    concat_inputs = "".join(f"[v{i}]" for i in range(len(scene_clips)))
    parts.append(f"{concat_inputs}concat=n={len(scene_clips)}:v=1:a=0[vout]")
    fc = ";".join(parts)

    cmd = [_ffmpeg_exe(), "-hide_banner", "-y", *inputs,
           "-filter_complex", fc,
           "-map", "[vout]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p",
           "-an",
           str(out_path)]
    logger.info("concat_scenes: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg concat failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-2000:]}"
        )
    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError(f"concat produced empty/invalid output: {out_path}")
    return out_path


def render_prompt_native_final(
    bg_video: Path,
    voice_audio: Path,
    captions_path: Path | None,
    out_path: Path,
    hook_text: str = "",
    target_duration_sec: float | None = None,
    music_bed: Path | None = None,
    music_bed_db: float = -18.0,
) -> Path:
    """Mux concatenated bg video + TTS voice + (optional) ASS/SRT captions
    + (optional) drawtext hook overlay into a single final MP4.

    Optional ``music_bed`` is mixed under the voice at ``music_bed_db`` dB
    (default -18 per the prompt-native spec). The bed is faded in/out
    (~0.4s) and looped to fit the target duration so short loops still
    cover the whole video.

    Reuses the same filter helpers as the per-clip finalizer in
    ffmpeg_render.py for consistent visual style.
    """
    bg_video = Path(bg_video)
    voice_audio = Path(voice_audio)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    opts = RenderOptions(
        hook_text=hook_text,
        target_duration_sec=target_duration_sec,
    )
    hook_file: Path | None = None
    if opts.hook_text.strip():
        hook_file = out_path.with_suffix(".hook.txt")
        hook_file.write_text(opts.hook_text.strip(), encoding="utf-8")

    chain: list[str] = []
    if captions_path is not None:
        chain.append(_subtitles_filter(captions_path, opts.subtitle_style))
    if hook_file is not None:
        chain.append(_hook_drawtext(opts, hook_file))
    if not chain:
        chain.append("null")
    vf = ",".join(chain)

    cmd = [_ffmpeg_exe(), "-hide_banner", "-y",
           "-i", str(bg_video),
           "-i", str(voice_audio)]

    has_bed = music_bed is not None and Path(music_bed).exists()
    if has_bed:
        # ``-stream_loop -1`` repeats the bed; the filter graph below
        # trims to target_duration_sec so it doesn't run on forever.
        cmd += ["-stream_loop", "-1", "-i", str(music_bed)]

    if has_bed:
        # Build an audio filter graph that ducks the bed under voice.
        # We use volume= rather than sidechaincompress because (a) it
        # avoids an extra ffmpeg dep on libebur128 in some builds and
        # (b) the bed is already supposed to be quiet — operators set
        # the dB level explicitly. Voice is passed through with apad.
        gain_db = float(music_bed_db)
        af = (
            f"[1:a]apad,aresample=async=1[voice];"
            f"[2:a]volume={gain_db}dB,afade=t=in:st=0:d=0.4,"
            f"afade=t=out:st={max(0.5, (target_duration_sec or 30) - 0.4):.2f}"
            f":d=0.4[bed];"
            f"[voice][bed]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
        cmd += ["-filter_complex", af,
                 "-vf", vf,
                 "-map", "0:v:0", "-map", "[aout]"]
    else:
        cmd += ["-vf", vf,
                 "-af", "apad",
                 "-map", "0:v:0", "-map", "1:a:0"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k"]
    if target_duration_sec is not None:
        cmd += ["-t", f"{target_duration_sec:.2f}"]
    else:
        cmd += ["-shortest"]
    cmd.append(str(out_path))

    logger.info("prompt_native_final: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg final failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-2000:]}"
        )
    if hook_file is not None and hook_file.exists():
        try:
            hook_file.unlink()
        except Exception:
            pass
    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError(f"final produced empty/invalid output: {out_path}")
    return out_path

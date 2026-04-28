"""Split Video adapter — main clip + filler underneath/alongside.

Layout:
  - ``vertical`` (default): main on top half, filler on bottom half
    (TikTok "Subway Surfers" style).
  - ``horizontal``: main on left half, filler on right half.

Both clips are scaled + center-cropped to fit their half. Audio comes
from TTS over the user-supplied script (the uploads are muted so the
narration is clean). When neither upload resolves we fall back to the
voiceover happy path with a solid-color background — guarantees a
final mp4 exists even with broken URLs.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import imageio_ffmpeg

from xvideo.post.tts import synthesize, voice_for_pack
from xvideo.post.word_captions import build_ass
from xvideo.post.prompt_video_stitcher import render_prompt_native_final
from xvideo.prompt_native.schema import aspect_to_size

from apps.worker.render_adapters._common import render_script_with_solid_bg
from apps.worker.render_adapters._video_input import resolve_video_input
from apps.worker.template_inputs import SplitVideoInput


logger = logging.getLogger(__name__)


def _split_compose(
    *,
    main: Path,
    filler: Path | None,
    layout: str,
    size: tuple[int, int],
    duration: float,
    background_color: str,
    out_path: Path,
) -> Path:
    """Compose main + filler into a single split mp4 of the given size.

    If ``filler`` is None the bottom/right half is filled with the
    operator's chosen ``background_color``.
    """
    width, height = size
    if layout == "horizontal":
        half_w, half_h = width // 2, height
    else:
        half_w, half_h = width, height // 2

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    # Build the filtergraph based on whether filler is present.
    if filler is not None:
        cmd = [
            ffmpeg, "-hide_banner", "-y",
            "-stream_loop", "-1", "-i", str(main),
            "-stream_loop", "-1", "-i", str(filler),
        ]
        scale_main = (
            f"[0:v]scale={half_w}:{half_h}:force_original_aspect_ratio=increase,"
            f"crop={half_w}:{half_h}[m]"
        )
        scale_fill = (
            f"[1:v]scale={half_w}:{half_h}:force_original_aspect_ratio=increase,"
            f"crop={half_w}:{half_h}[f]"
        )
        stack = "hstack=inputs=2" if layout == "horizontal" else "vstack=inputs=2"
        fg = f"{scale_main};{scale_fill};[m][f]{stack}[out]"
        cmd += ["-filter_complex", fg,
                "-map", "[out]"]
    else:
        bg_hex = background_color.lstrip("#")
        cmd = [
            ffmpeg, "-hide_banner", "-y",
            "-stream_loop", "-1", "-i", str(main),
            "-f", "lavfi",
            "-i", f"color=c=0x{bg_hex}:s={half_w}x{half_h}:d={duration:.2f}",
        ]
        scale_main = (
            f"[0:v]scale={half_w}:{half_h}:force_original_aspect_ratio=increase,"
            f"crop={half_w}:{half_h}[m]"
        )
        stack = "hstack=inputs=2" if layout == "horizontal" else "vstack=inputs=2"
        fg = f"{scale_main};[m][1:v]{stack}[out]"
        cmd += ["-filter_complex", fg,
                "-map", "[out]"]

    cmd += [
        "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-t", f"{duration:.2f}",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"split compose failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-1500:]}"
        )
    return out_path


def render(input: SplitVideoInput, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    size = aspect_to_size(input.aspect)

    main = resolve_video_input(input.main_url, work_dir)
    filler = resolve_video_input(input.filler_url, work_dir)

    # No usable main upload — fall back to plain voiceover-style render.
    if main is None:
        return render_script_with_solid_bg(
            script=input.script,
            voice_name=input.voice_name,
            aspect=input.aspect,
            background_color=input.background_color,
            work_dir=work_dir,
            base="split_video",
        )

    # Voiced + composited path.
    voice_path = work_dir / "split_video_voice.mp3"
    chosen_voice = input.voice_name or voice_for_pack(None)
    tts = synthesize(
        text=input.script,
        out_path=voice_path,
        voice=chosen_voice,
        want_words=True,
    )
    target_dur = max(tts.duration_sec + 0.4, input.duration)

    bg_path = _split_compose(
        main=main, filler=filler,
        layout=input.layout,
        size=size,
        duration=target_dur,
        background_color=input.background_color,
        out_path=work_dir / "split_video_bg.mp4",
    )

    captions_path: Path | None = None
    if tts.words and input.caption_style is not None:
        captions_path = work_dir / "split_video_captions.ass"
        build_ass(
            words=tts.words,
            out_path=captions_path,
            video_width=size[0],
            video_height=size[1],
        )

    final_path = work_dir / "split_video.mp4"
    render_prompt_native_final(
        bg_video=bg_path,
        voice_audio=voice_path,
        captions_path=captions_path,
        out_path=final_path,
        hook_text="",
        target_duration_sec=tts.duration_sec,
    )
    return final_path

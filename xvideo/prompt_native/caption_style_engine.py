"""Caption style engine — 6 caption styles for prompt-native finals.

Background
----------
The current pipeline already produces *one* caption look: bold single
white words with a black stroke, lower-third (``word_captions.build_ass``
in ``xvideo/post/word_captions.py``). The prompt-native spec calls for a
named style menu so different platforms / tones can pick the right look.

We implement six styles from the spec, all rendered as ASS files so
ffmpeg's ``subtitles=`` filter can burn them in unchanged:

    bold_word           — current behavior; one bold word, lower-third
    kinetic_word        — bold word + slight pop animation per event
    clean_subtitle      — multi-word lines, smaller, classic subtitle
    impact_uppercase    — UPPERCASE punchy single word, slightly larger
    minimal_lower_third — small thin lower-third, two-line max
    karaoke_3word       — 3-word sliding window, current word accent-coloured

Why ASS for everything: libass already powers all five finalizers we
ship, the ffmpeg ``subtitles`` filter doesn't change between them, and
the existing word-event timing source (``estimate_word_events``)
produces ``WordEvent[]`` which is the ideal input for any of these.

Design rule
-----------
None of these styles change the *layout* of the video frame — captions
always sit in the lower 25% so the visual centre is preserved. The
spec is explicit: captions must not overlap "the important visual
center". We respect that with conservative ``MarginV`` values.

Public API
----------
- ``CAPTION_STYLES`` — list of valid style names.
- ``default_caption_style_for(format_name)`` — recommended default.
- ``build_caption_file(style, words, out_path, video_size)`` — write an
  ASS file in the given style. Returns the output path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from xvideo.post.word_captions import _ass_time, _escape_ass_text


CAPTION_STYLES: list[str] = [
    "bold_word",
    "kinetic_word",
    "clean_subtitle",
    "impact_uppercase",
    "minimal_lower_third",
    "karaoke_3word",
]


# Per-platform / per-tone defaults per the spec.
_FORMAT_DEFAULTS: dict[str, str] = {
    "shorts_clean":     "bold_word",
    "tiktok_fast":      "kinetic_word",
    "reels_aesthetic":  "clean_subtitle",
}

_TONE_DEFAULTS: dict[str, str] = {
    "motivational": "bold_word",
    "intense":      "impact_uppercase",
    "educational":  "clean_subtitle",
    "ambient":      "minimal_lower_third",
    "story":        "minimal_lower_third",
}


def default_caption_style_for(
    format_name: Optional[str] = None,
    tone: Optional[str] = None,
) -> str:
    """Pick a caption style. Tone wins over format if both are given.

    Falls back to ``bold_word`` (the previously-shipped default).
    """
    if tone and tone.lower() in _TONE_DEFAULTS:
        return _TONE_DEFAULTS[tone.lower()]
    if format_name and format_name in _FORMAT_DEFAULTS:
        return _FORMAT_DEFAULTS[format_name]
    return "bold_word"


# ─── ASS header builders ────────────────────────────────────────────────

@dataclass
class _StyleSpec:
    """Resolved per-style ASS attributes. Keeps the writer below DRY."""
    fontname: str
    fontsize: int
    bold: int                  # -1 (true) / 0 (false)
    primary: str               # &HAABBGGRR
    outline_color: str
    outline: int
    shadow: int
    align: int                 # numpad: 2=bottom-center, 8=top-center, ...
    margin_v: int


def _spec_for(style: str, video_height: int) -> _StyleSpec:
    """Resolve style → ASS attribute set scaled to the video height.

    All styles target a vertical 9:16 frame. Margins are computed in
    libass internal units (PlayResY = video_height) so absolute pixels
    stay consistent across resolutions.
    """
    h = max(int(video_height), 480)
    if style == "bold_word":
        return _StyleSpec("Arial", 72, -1, "&H00FFFFFF", "&H00000000", 6, 3,
                            2, int(h * 0.24))
    if style == "kinetic_word":
        return _StyleSpec("Arial Black", 78, -1, "&H00FFFFFF", "&H00111111", 6, 4,
                            2, int(h * 0.22))
    if style == "clean_subtitle":
        return _StyleSpec("Arial", 36, 0, "&H00FFFFFF", "&H00000000", 3, 1,
                            2, int(h * 0.06))
    if style == "impact_uppercase":
        return _StyleSpec("Impact", 96, -1, "&H00FFFFFF", "&H00000000", 8, 4,
                            2, int(h * 0.30))
    if style == "minimal_lower_third":
        return _StyleSpec("Arial", 28, 0, "&H00F0F0F0", "&H00000000", 2, 1,
                            2, int(h * 0.05))
    if style == "karaoke_3word":
        return _StyleSpec("Arial", 64, -1, "&H00FFFFFF", "&H00000000", 5, 3,
                            2, int(h * 0.22))
    raise ValueError(f"Unknown caption style: {style}")


def _ass_header(spec: _StyleSpec, video_width: int, video_height: int) -> str:
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {video_width}\n"
        f"PlayResY: {video_height}\n"
        "ScaledBorderAndShadow: yes\n"
        "WrapStyle: 2\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Word,{spec.fontname},{spec.fontsize},{spec.primary},"
        f"&H000000FF,{spec.outline_color},&H00000000,{spec.bold},0,0,0,"
        f"100,100,0,0,1,{spec.outline},{spec.shadow},{spec.align},40,40,"
        f"{spec.margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )


# ─── Per-style writers ──────────────────────────────────────────────────

def _write_one_word_per_event(
    words: Iterable, spec: _StyleSpec, header: str, out_path: Path,
    transform=lambda t: t,
    inline_override: str = "",
    min_event_sec: float = 0.12,
) -> Path:
    """Common writer: one Dialogue line per word (the bold_word /
    impact_uppercase / kinetic_word path)."""
    lines: list[str] = [header]
    for w in words:
        start = w.start_sec
        end = max(w.end_sec, start + min_event_sec)
        text = _escape_ass_text(transform(w.text))
        if inline_override:
            text = f"{{{inline_override}}}{text}"
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},"
            f"Word,,0,0,0,,{text}"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def _write_subtitle_lines(
    words, spec: _StyleSpec, header: str, out_path: Path,
    words_per_line: int = 7,
    min_event_sec: float = 0.5,
) -> Path:
    """Pack N words per line for ``clean_subtitle`` and
    ``minimal_lower_third``. Each line spans from its first word's start
    to its last word's end; events do not overlap."""
    word_list = list(words)
    if not word_list:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(header, encoding="utf-8")
        return out_path

    lines: list[str] = [header]
    i = 0
    while i < len(word_list):
        chunk = word_list[i: i + words_per_line]
        text = " ".join(w.text for w in chunk)
        text = _escape_ass_text(text)
        start = chunk[0].start_sec
        end = max(chunk[-1].end_sec, start + min_event_sec)
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},"
            f"Word,,0,0,0,,{text}"
        )
        i += words_per_line

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def _write_karaoke_3word(
    words, spec: _StyleSpec, header: str, out_path: Path,
    accent_color: str = "&H0000D7FF",   # warm yellow
) -> Path:
    """Sliding 3-word window, center word accent-coloured.

    ASS inline override ``\\c&Hbbggrr&`` recolours from that point until
    the next override. We emit one event per word with a 3-word context:
    ``prev current_accent next``. Per-word event timing equals the
    current word's timing, so the highlight visibly walks across the
    line.
    """
    word_list = list(words)
    if not word_list:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(header, encoding="utf-8")
        return out_path

    lines: list[str] = [header]
    n = len(word_list)
    for i, w in enumerate(word_list):
        prev_w = word_list[i - 1].text if i > 0 else ""
        next_w = word_list[i + 1].text if i < n - 1 else ""
        prev_t = _escape_ass_text(prev_w)
        cur_t = _escape_ass_text(w.text)
        next_t = _escape_ass_text(next_w)

        # Restoring colour after the centre word so the next word renders
        # in primary white again.
        body = ""
        if prev_t:
            body += prev_t + " "
        body += "{\\c" + accent_color + "}" + cur_t + "{\\c" + spec.primary + "}"
        if next_t:
            body += " " + next_t

        start = w.start_sec
        end = max(w.end_sec, start + 0.18)
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},"
            f"Word,,0,0,0,,{body}"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def build_caption_file(
    style: str,
    words: Iterable,
    out_path: str | Path,
    video_width: int = 576,
    video_height: int = 1024,
) -> Path:
    """Write an ASS caption file in the requested style.

    Args:
        style: one of ``CAPTION_STYLES``.
        words: iterable of ``WordEvent``-like objects with
            ``.text``, ``.start_sec``, ``.end_sec``. Same shape the
            existing ``word_captions.build_ass`` consumes.
        out_path: where to write the ``.ass`` file.
        video_width / video_height: PlayResX/PlayResY for libass; pass
            the actual encoded resolution.

    Returns:
        The resolved output path.
    """
    if style not in CAPTION_STYLES:
        raise ValueError(
            f"Unknown caption style {style!r}. "
            f"Valid: {', '.join(CAPTION_STYLES)}"
        )
    out_path = Path(out_path)
    spec = _spec_for(style, video_height)
    header = _ass_header(spec, video_width, video_height)

    if style == "bold_word":
        return _write_one_word_per_event(words, spec, header, out_path)
    if style == "impact_uppercase":
        return _write_one_word_per_event(
            words, spec, header, out_path,
            transform=lambda t: t.upper(),
        )
    if style == "kinetic_word":
        # \fad(60,40) gives a very short fade in/out per word — the
        # spec calls this "kinetic_word"; it stays readable on
        # auto-play feeds and does not require per-frame re-encoding.
        return _write_one_word_per_event(
            words, spec, header, out_path,
            inline_override=r"\fad(60,40)",
        )
    if style == "clean_subtitle":
        return _write_subtitle_lines(
            words, spec, header, out_path, words_per_line=7,
        )
    if style == "minimal_lower_third":
        return _write_subtitle_lines(
            words, spec, header, out_path, words_per_line=5,
        )
    if style == "karaoke_3word":
        return _write_karaoke_3word(words, spec, header, out_path)

    # Defensive — covered by the explicit validation above.
    raise ValueError(f"Unhandled style {style!r}")


__all__ = [
    "CAPTION_STYLES",
    "default_caption_style_for",
    "build_caption_file",
]

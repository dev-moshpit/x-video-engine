"""Caption style tests — ASS file shape per style."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from xvideo.prompt_native import (
    CAPTION_STYLES,
    build_caption_file,
    default_caption_style_for,
)


@dataclass
class _Word:
    text: str
    start_sec: float
    end_sec: float


@pytest.fixture
def words() -> list[_Word]:
    return [
        _Word("discipline", 0.00, 0.60),
        _Word("is",         0.60, 0.85),
        _Word("built",      0.85, 1.30),
        _Word("quietly",    1.30, 1.85),
        _Word("alone",      1.85, 2.40),
        _Word("in",         2.40, 2.55),
        _Word("the",        2.55, 2.70),
        _Word("cold",       2.70, 3.20),
    ]


def test_all_styles_listed():
    expected = {
        "bold_word", "kinetic_word", "clean_subtitle",
        "impact_uppercase", "minimal_lower_third", "karaoke_3word",
    }
    assert expected.issubset(set(CAPTION_STYLES))


def test_default_style_per_format():
    assert default_caption_style_for("shorts_clean") == "bold_word"
    assert default_caption_style_for("tiktok_fast") == "kinetic_word"
    assert default_caption_style_for("reels_aesthetic") == "clean_subtitle"
    # Unknown format → safe default
    assert default_caption_style_for("nonsense") == "bold_word"


def test_default_style_per_tone_overrides_format():
    # Tone wins
    assert default_caption_style_for("shorts_clean", tone="ambient") == "minimal_lower_third"
    assert default_caption_style_for("shorts_clean", tone="intense") == "impact_uppercase"


@pytest.mark.parametrize("style", [
    "bold_word", "kinetic_word", "clean_subtitle",
    "impact_uppercase", "minimal_lower_third", "karaoke_3word",
])
def test_each_style_writes_valid_ass(tmp_path: Path, words: list[_Word], style: str):
    out = tmp_path / f"{style}.ass"
    result = build_caption_file(style, words, out, video_width=576, video_height=1024)

    assert result == out
    body = out.read_text(encoding="utf-8")
    # Must include ASS section markers
    assert "[Script Info]" in body
    assert "[V4+ Styles]" in body
    assert "[Events]" in body
    assert "Dialogue:" in body
    # PlayRes must be present
    assert "PlayResX: 576" in body
    assert "PlayResY: 1024" in body


def test_one_word_per_event_styles(tmp_path: Path, words: list[_Word]):
    """bold_word, kinetic_word, impact_uppercase emit one Dialogue per word."""
    for style in ("bold_word", "kinetic_word", "impact_uppercase"):
        out = tmp_path / f"{style}.ass"
        build_caption_file(style, words, out)
        body = out.read_text(encoding="utf-8")
        n = body.count("Dialogue:")
        assert n == len(words), f"{style}: expected {len(words)}, got {n}"


def test_subtitle_styles_pack_words_into_lines(tmp_path: Path, words: list[_Word]):
    """clean_subtitle / minimal_lower_third group N words per line."""
    out_clean = tmp_path / "clean.ass"
    build_caption_file("clean_subtitle", words, out_clean)
    n_clean = out_clean.read_text(encoding="utf-8").count("Dialogue:")
    assert 1 <= n_clean < len(words)  # grouped, not per-word

    out_min = tmp_path / "min.ass"
    build_caption_file("minimal_lower_third", words, out_min)
    n_min = out_min.read_text(encoding="utf-8").count("Dialogue:")
    assert 1 <= n_min < len(words)


def test_impact_uppercase_uppercases_text(tmp_path: Path, words: list[_Word]):
    out = tmp_path / "impact.ass"
    build_caption_file("impact_uppercase", words, out)
    body = out.read_text(encoding="utf-8")
    # Original is lowercase; uppercased should be present
    assert "DISCIPLINE" in body
    assert "discipline" not in body.split("[Events]")[1]


def test_karaoke_3word_includes_color_overrides(tmp_path: Path, words: list[_Word]):
    out = tmp_path / "kara.ass"
    build_caption_file("karaoke_3word", words, out)
    body = out.read_text(encoding="utf-8")
    # ASS inline colour override marker (\c&H...)
    assert "\\c" in body


def test_unknown_style_raises():
    with pytest.raises(ValueError):
        build_caption_file("not_a_real_style", [], "/tmp/x.ass")

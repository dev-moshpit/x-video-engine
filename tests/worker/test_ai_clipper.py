"""AI Clipper engine tests — Platform Phase 1.

Three layers exercised:

  1. ``segment.find_moments`` — windowing logic against synthetic
     transcripts (no whisper involved).
  2. ``score.score_moment`` — each scoring dimension separately,
     plus the weighted total bound check.
  3. ``export.export_one_clip`` — real ffmpeg cut against a synthetic
     mp4 (no real-world video required).

The transcription path itself is covered indirectly by the existing
auto-captions whisper tests; here we exercise the rest of the pipeline
with hand-built TranscriptSegment dataclasses so the suite runs fast
and works on machines without faster-whisper installed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg
import pytest

from apps.worker.ai_clipper.export import export_one_clip
from apps.worker.ai_clipper.score import (
    DEFAULT_WEIGHTS,
    MomentScore,
    score_moment,
    score_moments,
)
from apps.worker.ai_clipper.segment import Moment, find_moments
from apps.worker.ai_clipper.transcribe import (
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)


# ─── Fixtures ───────────────────────────────────────────────────────────


def _word(text: str, start: float, end: float) -> TranscriptWord:
    return TranscriptWord(text=text, start=start, end=end)


def _seg(
    sid: int, start: float, end: float, text: str,
    *, no_speech: float = 0.0, logprob: float = -0.2,
) -> TranscriptSegment:
    """Build a TranscriptSegment with words synthesized from ``text``."""
    tokens = text.split()
    if not tokens:
        words = ()
    else:
        per = (end - start) / len(tokens)
        words = tuple(
            _word(t.strip(".,!?"), start + i * per, start + (i + 1) * per)
            for i, t in enumerate(tokens)
        )
    return TranscriptSegment(
        id=sid, start=start, end=end, text=text, words=words,
        avg_logprob=logprob, no_speech_prob=no_speech,
    )


def _transcript(segs: list[TranscriptSegment]) -> Transcript:
    duration = max((s.end for s in segs), default=0.0)
    return Transcript(
        duration=duration, language="en",
        segments=tuple(segs),
        audio_path=Path("/tmp/none.wav"),
    )


def _make_silent_video(out: Path, duration: float = 60.0) -> Path:
    """Render a small silent black mp4 we can clip against.

    Both lavfi inputs get an explicit duration via ``-t`` so neither
    runs forever — Windows ffmpeg builds choke on indefinite anullsrc
    even with ``-shortest``.
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-t", f"{duration:.2f}",
        "-f", "lavfi",
        "-i", "color=c=black:s=320x240:r=24",
        "-t", f"{duration:.2f}",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=mono:sample_rate=16000",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    return out


# ─── Segmenter ─────────────────────────────────────────────────────────


def test_find_moments_returns_empty_for_empty_transcript():
    assert find_moments(_transcript([])) == []


def test_find_moments_groups_consecutive_segments_into_clip_window():
    """Six tightly-packed 5s segments → one ~30s window."""
    segs = [_seg(i, i * 5.0, i * 5.0 + 5.0, f"Sentence number {i}.") for i in range(6)]
    moments = find_moments(_transcript(segs), min_duration=10.0,
                           target_duration=30.0, max_duration=45.0)
    assert len(moments) == 1
    m = moments[0]
    assert m.start == 0.0
    assert m.duration >= 25.0
    assert m.duration <= 45.0
    assert m.text.startswith("Sentence number 0.")


def test_find_moments_breaks_on_natural_pause():
    """A long gap between segments must end the current window."""
    segs = [
        _seg(0, 0.0, 8.0, "First idea ends here cleanly with enough text."),
        _seg(1, 8.5, 17.0, "Second idea continues briefly with related text."),
        # > 5s gap
        _seg(2, 22.5, 30.0, "Third idea after a long pause."),
        _seg(3, 30.0, 38.0, "Continuation of the third idea."),
    ]
    moments = find_moments(_transcript(segs), min_duration=8.0,
                           target_duration=15.0, max_duration=30.0,
                           min_gap=2.0)
    # Gap forces at least 2 windows.
    assert len(moments) >= 2


def test_find_moments_respects_max_duration():
    """Max cap must be honored even with no pause."""
    segs = [_seg(i, i * 10.0, i * 10.0 + 10.0, f"Segment {i} a b c.") for i in range(20)]
    moments = find_moments(_transcript(segs), min_duration=10.0,
                           target_duration=40.0, max_duration=60.0)
    for m in moments:
        assert m.duration <= 60.0


def test_find_moments_drops_too_short_windows():
    """Micro-pauses can't synthesize a clip < min_duration."""
    segs = [_seg(0, 0.0, 5.0, "Short tease.")]
    moments = find_moments(_transcript(segs), min_duration=12.0)
    assert moments == []


# ─── Scoring ───────────────────────────────────────────────────────────


def test_score_moment_returns_normalized_total():
    seg = _seg(0, 0.0, 30.0,
               "What if you could double your income in 30 days? Listen carefully.")
    moment = Moment("m000", 0.0, 30.0, seg.text, (seg,))
    score = score_moment(moment)
    assert isinstance(score, MomentScore)
    assert 0.0 <= score.total <= 1.0
    for k in ("hook_strength", "emotional_spike", "controversy",
              "clarity", "length_fit", "speaker_energy", "caption_potential"):
        v = getattr(score, k)
        assert 0.0 <= v <= 1.0, f"{k}={v} out of range"


def test_question_opener_scores_higher_than_neutral():
    qmoment = Moment(
        "mq", 0.0, 30.0,
        "What if everything you knew about money was wrong?",
        (_seg(0, 0.0, 30.0, "What if everything you knew about money was wrong?"),),
    )
    nmoment = Moment(
        "mn", 0.0, 30.0,
        "Today the weather is fine and the wind is calm.",
        (_seg(0, 0.0, 30.0, "Today the weather is fine and the wind is calm."),),
    )
    qs = score_moment(qmoment)
    ns = score_moment(nmoment)
    assert qs.hook_strength > ns.hook_strength


def test_emotion_lexicon_lifts_emotional_spike():
    flat = Moment(
        "mf", 0.0, 30.0,
        "The plan describes an ordinary work routine in the office.",
        (_seg(0, 0.0, 30.0, "The plan describes an ordinary work routine in the office."),),
    )
    hot = Moment(
        "mh", 0.0, 30.0,
        "This is absolutely insane — completely shocking and amazing!",
        (_seg(0, 0.0, 30.0, "This is absolutely insane — completely shocking and amazing!"),),
    )
    assert score_moment(hot).emotional_spike > score_moment(flat).emotional_spike


def test_length_fit_peak_around_thirty_five_seconds():
    short = Moment("ms", 0.0, 12.0, "x", (_seg(0, 0.0, 12.0, "x"),))
    ideal = Moment("mi", 0.0, 35.0, "x", (_seg(0, 0.0, 35.0, "x"),))
    long_ = Moment("ml", 0.0, 70.0, "x", (_seg(0, 0.0, 70.0, "x"),))
    assert score_moment(ideal).length_fit > score_moment(short).length_fit
    assert score_moment(ideal).length_fit > score_moment(long_).length_fit


def test_default_weights_sum_to_one():
    """Sanity — default weight set should be in [0.95, 1.05]."""
    assert 0.95 <= sum(DEFAULT_WEIGHTS.values()) <= 1.05


def test_score_moments_returns_one_per_input():
    moments = [
        Moment(f"m{i}", i * 30.0, i * 30.0 + 30.0,
               "Test sentence here.",
               (_seg(0, i * 30.0, i * 30.0 + 30.0, "Test sentence here."),))
        for i in range(3)
    ]
    scores = score_moments(moments)
    assert len(scores) == 3
    for m, s in zip(moments, scores):
        assert s.moment_id == m.moment_id


# ─── Export ────────────────────────────────────────────────────────────


def test_export_one_clip_produces_real_mp4(tmp_path: Path):
    src = _make_silent_video(tmp_path / "src.mp4", duration=20.0)
    seg = _seg(0, 5.0, 12.0,
               "This is a short sentence used as the on-screen caption test.")
    moment = Moment(
        moment_id="m_test",
        start=5.0,
        end=12.0,
        text=seg.text,
        segments=(seg,),
    )
    out = export_one_clip(
        src_url=str(src),
        moment=moment,
        work_dir=tmp_path,
        aspect="9:16",
        burn_captions=True,
    )
    assert out.exists()
    assert out.stat().st_size > 5_000


def test_export_one_clip_rejects_invalid_aspect(tmp_path: Path):
    seg = _seg(0, 0.0, 5.0, "Invalid aspect rejection test.")
    moment = Moment("m1", 0.0, 5.0, seg.text, (seg,))
    with pytest.raises(ValueError):
        export_one_clip(
            src_url="any",
            moment=moment,
            work_dir=tmp_path,
            aspect="4:3",
        )


def test_export_one_clip_rejects_zero_duration(tmp_path: Path):
    seg = _seg(0, 0.0, 0.0, "")
    moment = Moment("m0", 5.0, 5.0, "", (seg,))
    with pytest.raises(ValueError):
        export_one_clip(
            src_url="any", moment=moment, work_dir=tmp_path, aspect="9:16",
        )


def test_export_no_captions_still_succeeds(tmp_path: Path):
    """``burn_captions=False`` must skip the ASS pass cleanly."""
    src = _make_silent_video(tmp_path / "src.mp4", duration=15.0)
    seg = _seg(0, 2.0, 8.0, "Skip caption burn-in path.")
    moment = Moment("m_no_cap", 2.0, 8.0, seg.text, (seg,))
    out = export_one_clip(
        src_url=str(src), moment=moment, work_dir=tmp_path,
        aspect="1:1", burn_captions=False,
    )
    assert out.exists()
    assert out.stat().st_size > 5_000

"""Score candidate viral moments across seven dimensions.

The scoring function is heuristic + deterministic — no LLM required —
which makes it cheap, testable, and reproducible. It mirrors the
"viral-moment" intuitions from systems like OpusClip / Vizard:

  hook_strength       — does the first sentence open with a question
                        or strong declarative? questions and
                        "imagine if" / "wait until" / "the truth is"
                        type openers score higher.

  emotional_spike     — density of emotion / intensifier words and
                        ALL-CAPS yelling tokens.

  controversy         — "but", "actually", "wrong", question marks
                        per second.

  clarity             — average word length, no_speech_prob from the
                        whisper segments. Penalize uhh/umm fillers.

  length_fit          — duration distance from a 30-40s sweet spot.

  speaker_energy      — words-per-second density (proxy for speaker
                        energy when no audio-level analysis is run).

  caption_potential   — frequency of pithy short sentences (≤ 8 words)
                        — these caption well as standalone overlays.

Each dimension is normalized to [0, 1]. ``MomentScore.total`` is a
weighted sum. Weights live in ``DEFAULT_WEIGHTS`` and can be passed
through ``score_moment(weights=...)`` for experimentation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

from apps.worker.ai_clipper.segment import Moment


DEFAULT_WEIGHTS: Mapping[str, float] = {
    "hook_strength": 0.22,
    "emotional_spike": 0.15,
    "controversy": 0.12,
    "clarity": 0.13,
    "length_fit": 0.10,
    "speaker_energy": 0.13,
    "caption_potential": 0.15,
}


_HOOK_OPENERS = {
    # Questions
    "what", "why", "how", "when", "where", "who",
    # Strong declaratives
    "imagine", "picture", "wait", "stop", "listen", "look",
    "actually", "truth", "secret", "nobody", "everyone", "everybody",
    "this", "that's", "thats", "here's", "heres", "the",
    # Hot framings
    "if", "have", "did",
}

# Strong sentiment + intensifiers. Lowercased; matched as whole words.
_EMOTION_LEXICON = frozenset({
    "amazing", "incredible", "awesome", "insane", "crazy", "wild",
    "shocking", "unbelievable", "terrible", "horrible", "awful",
    "terrifying", "devastating", "best", "worst", "extreme",
    "love", "hate", "always", "never", "literally", "absolutely",
    "definitely", "totally", "completely", "honestly", "actually",
    "obviously", "shocked", "stunned", "amazed", "destroyed",
    "exposed", "revealed", "leaked", "cancelled", "viral",
    "rich", "broke", "millionaire", "billionaire", "free",
    "warning", "danger", "stop", "wait", "wow",
})

_CONTROVERSY_LEXICON = frozenset({
    "but", "however", "actually", "wrong", "lie", "lied", "lies",
    "fake", "real", "truth", "proof", "exposed", "controversial",
    "debate", "argue", "disagree", "myth", "secret", "hidden",
})

_FILLERS = frozenset({
    "uh", "um", "uhh", "umm", "like", "you", "know", "sort", "kind",
    "basically", "literally",  # "literally" doubles as filler
})


@dataclass(frozen=True)
class MomentScore:
    """Per-dimension breakdown + the weighted total in [0, 1]."""
    moment_id: str
    total: float
    hook_strength: float
    emotional_spike: float
    controversy: float
    clarity: float
    length_fit: float
    speaker_energy: float
    caption_potential: float
    notes: tuple[str, ...] = field(default_factory=tuple)


# ─── Per-dimension helpers ─────────────────────────────────────────────


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z']+", text)]


def _first_sentence(text: str) -> str:
    """Return text up to the first ``.``, ``?``, or ``!``."""
    m = re.search(r"[.?!]", text)
    return text[: m.start() + 1] if m else text


def _hook_strength(moment: Moment) -> tuple[float, str]:
    if not moment.text:
        return 0.0, "no text"
    head = _first_sentence(moment.text).strip()
    if not head:
        return 0.0, "no first sentence"
    tokens = _tokenize(head)
    if not tokens:
        return 0.0, "no tokens"

    score = 0.0
    notes: list[str] = []

    # Question opener? Strong hook.
    if head.endswith("?"):
        score += 0.45
        notes.append("opens with a question")

    # First-token check — stronger weight.
    first = tokens[0]
    if first in _HOOK_OPENERS:
        score += 0.30
        notes.append(f"opens with '{first}'")

    # Multi-token check — anywhere in first 8 tokens.
    multi_hits = sum(1 for t in tokens[:8] if t in _HOOK_OPENERS)
    score += min(0.20, multi_hits * 0.05)

    # Tight first sentence (<= 12 words) is more "hook-shaped".
    if len(tokens) <= 12:
        score += 0.10
        notes.append("punchy opener")

    return min(1.0, score), "; ".join(notes) or "neutral opener"


def _emotional_spike(moment: Moment) -> float:
    tokens = _tokenize(moment.text)
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t in _EMOTION_LEXICON)
    # ALL-CAPS run length (excluding short acronyms)
    caps_runs = re.findall(r"\b[A-Z]{4,}\b", moment.text)
    base = hits / max(len(tokens), 1)
    cap_bonus = min(0.3, 0.1 * len(caps_runs))
    return min(1.0, base * 5.0 + cap_bonus)  # density × 5 — words/100 ≈ 0.5


def _controversy(moment: Moment) -> float:
    text = moment.text
    tokens = _tokenize(text)
    dur = max(moment.duration, 1.0)
    qs = text.count("?") / dur  # questions per second
    hits = sum(1 for t in tokens if t in _CONTROVERSY_LEXICON)
    density = hits / max(len(tokens), 1)
    return min(1.0, density * 6.0 + qs * 4.0)


def _clarity(moment: Moment) -> float:
    """Higher = cleaner audio + lower filler density."""
    if not moment.segments:
        return 0.5
    no_speech = sum(s.no_speech_prob for s in moment.segments) / len(moment.segments)
    avg_logprob = sum(s.avg_logprob for s in moment.segments) / len(moment.segments)
    # avg_logprob is typically in [-1.0, -0.1] for clean speech; map to [0, 1].
    logprob_norm = max(0.0, min(1.0, 1.0 + avg_logprob))  # -0.0 → 1.0; -1.0 → 0.0

    tokens = _tokenize(moment.text)
    filler_hits = sum(1 for t in tokens if t in _FILLERS)
    filler_density = filler_hits / max(len(tokens), 1)
    # Penalize fillers above a 5% rate.
    filler_pen = min(1.0, max(0.0, (filler_density - 0.05) * 6.0))

    base = (1.0 - no_speech) * 0.4 + logprob_norm * 0.6
    return max(0.0, min(1.0, base * (1.0 - filler_pen * 0.5)))


def _length_fit(moment: Moment, target: float = 35.0, span: float = 25.0) -> float:
    """Triangle peak at ``target`` seconds; 0 outside [target ± span]."""
    d = moment.duration
    if d <= 0:
        return 0.0
    diff = abs(d - target)
    return max(0.0, 1.0 - diff / span)


def _speaker_energy(moment: Moment) -> float:
    if moment.duration <= 0:
        return 0.0
    wps = moment.word_count / moment.duration
    # Conversational speech ≈ 2.5-3 wps; rapid delivery ≈ 4 wps.
    if wps <= 1.0:
        return 0.0
    if wps >= 4.5:
        return 1.0
    return min(1.0, (wps - 1.0) / 3.5)


def _caption_potential(moment: Moment) -> float:
    """Fraction of segments that are short, caption-shaped sentences."""
    if not moment.segments:
        return 0.0
    short = 0
    for s in moment.segments:
        wc = len(s.words) or len(s.text.split())
        if 3 <= wc <= 8:
            short += 1
    return min(1.0, short / max(len(moment.segments), 1))


# ─── Public API ────────────────────────────────────────────────────────


def score_moment(
    moment: Moment,
    *,
    weights: Mapping[str, float] = DEFAULT_WEIGHTS,
) -> MomentScore:
    """Score a single moment and return a :class:`MomentScore`."""
    hook, hook_note = _hook_strength(moment)
    emo = _emotional_spike(moment)
    contro = _controversy(moment)
    clar = _clarity(moment)
    fit = _length_fit(moment)
    energy = _speaker_energy(moment)
    cap = _caption_potential(moment)

    components = {
        "hook_strength": hook,
        "emotional_spike": emo,
        "controversy": contro,
        "clarity": clar,
        "length_fit": fit,
        "speaker_energy": energy,
        "caption_potential": cap,
    }
    total = sum(components[k] * weights.get(k, 0.0) for k in components)
    # Normalize back to [0, 1] in case weights don't sum to 1.
    weight_sum = sum(weights.get(k, 0.0) for k in components)
    if weight_sum > 0:
        total = total / weight_sum

    notes: list[str] = [f"hook: {hook_note}"]
    if energy > 0.7:
        notes.append("high speaker energy")
    if cap > 0.5:
        notes.append("caption-friendly cadence")
    if fit < 0.3:
        notes.append("duration outside ideal 25-45s window")

    return MomentScore(
        moment_id=moment.moment_id,
        total=round(total, 4),
        hook_strength=round(hook, 4),
        emotional_spike=round(emo, 4),
        controversy=round(contro, 4),
        clarity=round(clar, 4),
        length_fit=round(fit, 4),
        speaker_energy=round(energy, 4),
        caption_potential=round(cap, 4),
        notes=tuple(notes),
    )


def score_moments(
    moments: list[Moment],
    *,
    weights: Mapping[str, float] = DEFAULT_WEIGHTS,
) -> list[MomentScore]:
    return [score_moment(m, weights=weights) for m in moments]

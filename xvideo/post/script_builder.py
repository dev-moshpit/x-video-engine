"""Build a voiceover script from a clip's publish metadata.

Each sidecar already has a `publish` block (title, caption, cta, platforms)
that we compiled at batch time. Post-production reuses it: the title is
the on-screen hook, and the caption body + cta become the voiceover script.

No LLM. No regeneration. Same copy the operator reviewed in the gallery.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class VoiceScript:
    """Text fed to the TTS engine + on-screen hook text."""
    hook: str                              # displayed in first ~2s
    lines: list[str] = field(default_factory=list)   # VO script, one line per caption
    cta: str = ""

    def as_plain_text(self) -> str:
        """What the TTS engine reads (one sentence per line)."""
        return "\n".join(self.lines)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in items:
        key = s.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(s.strip())
    return out


def _clean_for_tts(text: str) -> str:
    """Strip markdown, stray hashtags/emojis that don't read well aloud."""
    text = re.sub(r"#\w+", "", text)                  # inline hashtags
    text = re.sub(r"[\*_`]+", "", text)               # markdown emphasis
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_script(publish: dict, primary_platform: str | None = None) -> VoiceScript:
    """Compose a VoiceScript from a sidecar's `publish` block.

    Prefers the primary platform's caption if one is set (usually by the
    --format layer), else falls back to `publish.caption`. The title is
    always used as the on-screen hook.

    Args:
        publish:  the sidecar's `publish` dict
        primary_platform: "shorts" | "tiktok" | "reels" | None

    Returns:
        VoiceScript with hook, lines, cta.
    """
    if not publish:
        return VoiceScript(hook="", lines=[], cta="")

    title = (publish.get("title") or "").strip()
    cta = (publish.get("cta") or "").strip()

    caption_source = ""
    if primary_platform:
        pv = (publish.get("platforms") or {}).get(primary_platform) or {}
        caption_source = (pv.get("caption") or "").strip()
    if not caption_source:
        caption_source = (publish.get("caption") or "").strip()

    # Caption templates separate sections with blank lines.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", caption_source) if b.strip()]

    # Candidates for VO script: title + each caption block + CTA. The CTA
    # may already appear in the caption (e.g. default platform template);
    # dedupe catches that. For platform variants that omit CTA (shorts),
    # the explicit append ensures it still gets voiced.
    candidates = [title] + blocks + [cta]
    seen: set[str] = set()
    lines: list[str] = []
    for raw in candidates:
        cleaned = _clean_for_tts(raw)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            lines.append(cleaned)

    return VoiceScript(hook=title, lines=lines, cta=cta)

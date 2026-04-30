"""Script engine — hook / VO / CTA composition.

This module exposes the script side of a ``VideoPlan`` as a small,
self-contained API so callers (UI, tests, future LLM planner) can ask
just for the script:

    from xvideo.prompt_native.script_engine import script_from_plan
    s = script_from_plan(plan)
    print(s.hook, s.voiceover_lines, s.captions, s.cta)

The director already builds a script as part of the plan; we don't
duplicate that logic here. The point of this module is to:

1. Document the script structure (hook → pressure → turn → CTA).
2. Provide a typed accessor (``ScriptResult``) so downstream stages
   don't have to know plan field names.
3. Provide a *bare* generator (``build_script``) for the rare case
   where a caller has narration but no full plan and wants to run the
   normal hook/CTA composition logic. Used by future LLM mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from xvideo.prompt_native.schema import VideoPlan


@dataclass
class ScriptResult:
    """The script side of a VideoPlan, isolated from visual state."""
    hook: str
    voiceover_lines: list[str]
    captions: list[str]
    cta: str
    voice_tone: str = ""
    caption_style: str = ""
    audience: str = ""
    emotional_angle: str = ""

    def is_complete(self) -> bool:
        return bool(self.hook and self.voiceover_lines and self.cta)


def script_from_plan(plan: VideoPlan) -> ScriptResult:
    """Project a ``VideoPlan`` to its script-only view."""
    captions = [s.on_screen_caption for s in plan.scenes if s.on_screen_caption]
    return ScriptResult(
        hook=plan.hook,
        voiceover_lines=list(plan.voiceover_lines),
        captions=captions,
        cta=plan.cta,
        voice_tone=plan.voice_tone,
        caption_style=plan.caption_style,
        audience=plan.audience,
        emotional_angle=plan.emotional_angle,
    )


def build_script(
    *,
    hook: str,
    voiceover_lines: list[str],
    captions: Optional[list[str]] = None,
    cta: str = "",
    voice_tone: str = "",
    caption_style: str = "word",
) -> ScriptResult:
    """Construct a ``ScriptResult`` from raw parts.

    Used by future ``--planner llm`` integrations and by tests that want
    to assemble a script without invoking the director.
    """
    return ScriptResult(
        hook=hook,
        voiceover_lines=list(voiceover_lines),
        captions=list(captions or []),
        cta=cta,
        voice_tone=voice_tone,
        caption_style=caption_style,
    )


__all__ = ["ScriptResult", "script_from_plan", "build_script"]

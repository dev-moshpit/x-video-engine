"""Render-adapter dispatcher.

Each adapter is a (input_model, module) pair indexed by template_id.
Storing the *module* (not the bound render function) gives us late
binding — tests can patch ``apps.worker.render_adapters.ai_story.render``
and the dispatcher picks up the patch on the next call.

The worker's queue consumer calls ``render_for_template`` which
validates the raw ``template_input`` dict against the right Pydantic
model before invoking ``module.render(typed_input, work_dir)``.

Phase 1 templates: ai_story, reddit_story, voiceover, auto_captions.
Phase 2 templates: fake_text, would_you_rather, split_video, twitter,
top_five, roblox_rant.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Type

from pydantic import BaseModel

from apps.worker.render_adapters import (
    ai_story,
    auto_captions,
    fake_text,
    reddit_story,
    roblox_rant,
    split_video,
    top_five,
    twitter,
    voiceover,
    would_you_rather,
)
from apps.worker.template_inputs import (
    AIStoryInput,
    AutoCaptionsInput,
    FakeTextInput,
    RedditStoryInput,
    RobloxRantInput,
    SplitVideoInput,
    TopFiveInput,
    TwitterInput,
    VoiceoverInput,
    WouldYouRatherInput,
)


@dataclass(frozen=True)
class AdapterEntry:
    """One template → adapter mapping.

    ``module`` is the adapter module — the dispatcher looks up
    ``module.render`` at call time so test patches on the module's
    ``render`` attribute take effect (late binding).
    """
    input_model: Type[BaseModel]
    module: ModuleType


ADAPTERS: dict[str, AdapterEntry] = {
    "ai_story":         AdapterEntry(AIStoryInput,         ai_story),
    "reddit_story":     AdapterEntry(RedditStoryInput,     reddit_story),
    "voiceover":        AdapterEntry(VoiceoverInput,       voiceover),
    "auto_captions":    AdapterEntry(AutoCaptionsInput,    auto_captions),
    "fake_text":        AdapterEntry(FakeTextInput,        fake_text),
    "would_you_rather": AdapterEntry(WouldYouRatherInput,  would_you_rather),
    "split_video":      AdapterEntry(SplitVideoInput,      split_video),
    "twitter":          AdapterEntry(TwitterInput,         twitter),
    "top_five":         AdapterEntry(TopFiveInput,         top_five),
    "roblox_rant":      AdapterEntry(RobloxRantInput,      roblox_rant),
}


def render_for_template(
    template: str, raw_input: dict, work_dir: Path,
) -> Path:
    """Validate the raw template_input + dispatch to the right adapter.

    Raises ``ValueError`` for an unknown template. Pydantic's
    ``ValidationError`` propagates if the input doesn't match the
    template's schema — the worker (PR 6) will surface that as a
    failed render with the validation message in ``renders.error``.
    """
    entry = ADAPTERS.get(template)
    if entry is None:
        raise ValueError(
            f"unknown template '{template}' — known: {sorted(ADAPTERS)}"
        )
    typed = entry.input_model.model_validate(raw_input)
    return entry.module.render(typed, work_dir)

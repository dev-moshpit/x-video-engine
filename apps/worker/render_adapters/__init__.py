"""Render-adapter dispatcher.

Each adapter is a (input_model, module) pair indexed by template_id.
Storing the *module* (not the bound render function) gives us late
binding — tests can patch ``apps.worker.render_adapters.ai_story.render``
and the dispatcher picks up the patch on the next call.

The worker's queue consumer (PR 6) will call ``render_for_template``
which validates the raw template_input dict against the right Pydantic
model before invoking ``module.render(typed_input, work_dir)``.

Adding a Phase 2 template (Fake Text, Would You Rather, etc.) is one
new ``ADAPTERS`` entry plus a new module under this package.
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
    reddit_story,
    voiceover,
)
from apps.worker.template_inputs import (
    AIStoryInput,
    AutoCaptionsInput,
    RedditStoryInput,
    VoiceoverInput,
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
    "ai_story":      AdapterEntry(AIStoryInput,      ai_story),
    "reddit_story":  AdapterEntry(RedditStoryInput,  reddit_story),
    "voiceover":     AdapterEntry(VoiceoverInput,    voiceover),
    "auto_captions": AdapterEntry(AutoCaptionsInput, auto_captions),
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

"""Per-render context — Phase 6.

Adapters that respect branding (top_five, would_you_rather, twitter,
fake_text) read the user's brand kit via :func:`get_brand_kit` instead
of taking it as a third argument. Keeps all 10 adapter signatures
identical and avoids threading the same dict through every helper
that doesn't care.

The context is a module-level dict managed by the dispatcher around
each ``render`` call:

    set_brand_kit({"brand_color": "#1f6feb", ...})
    try:
        adapter.render(typed, work_dir)
    finally:
        set_brand_kit(None)

Worker is single-threaded per process today, so a module-level
variable is fine. If we move to a multi-threaded worker we swap to
:class:`contextvars.ContextVar` without touching the adapters.
"""

from __future__ import annotations

from typing import Optional


_brand_kit: Optional[dict] = None


def set_brand_kit(kit: Optional[dict]) -> None:
    global _brand_kit
    _brand_kit = kit or None


def get_brand_kit() -> dict:
    """Return the active brand kit dict, or empty when none set."""
    return _brand_kit or {}


def get_brand_color(field: str, default: str) -> str:
    """Look up a brand color by token, falling back to ``default``.

    ``field`` is one of ``brand_color | accent_color | text_color``.
    Returns ``default`` when no kit is active or the field is empty.
    """
    return (_brand_kit or {}).get(field) or default

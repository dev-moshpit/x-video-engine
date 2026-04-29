"""Legacy font helper — forwards to ``_fonts`` for backwards compatibility.

The new implementation lives in :mod:`apps.worker.render_adapters._fonts`
which adds glyph-aware fallback (so emoji codepoints don't render as
``.notdef`` boxes) and a semantic role-based registry. Old call sites
that import ``load_font`` and ``_candidate_paths`` from here keep
working unchanged.
"""

from __future__ import annotations

from apps.worker.render_adapters._fonts import _candidates, load_font  # noqa: F401


def _candidate_paths(*, want_bold: bool) -> list[str]:
    """Legacy signature — pre-``_fonts`` callers asked for the path list
    by ``want_bold`` only. Forwards to the new ``_candidates(kind=…)``
    so both APIs stay in sync.
    """
    return list(_candidates("bold" if want_bold else "text"))


__all__ = ["load_font", "_candidate_paths"]

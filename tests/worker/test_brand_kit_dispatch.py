"""Brand-kit dispatcher pop + context plumbing — Phase 6.

The worker injects ``_brand_kit`` into the raw template_input dict
before calling the dispatcher. The dispatcher must:

  1. Pop ``_brand_kit`` out so Pydantic's ``extra="forbid"`` doesn't
     reject the input.
  2. Stash the kit on the per-render context module so panel adapters
     (top_five, twitter) can read it via ``get_brand_color``.
  3. Clear the context after the render so a paid-tier render doesn't
     leak its kit into the next free-tier job in the same worker.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from apps.worker.render_adapters import _context, render_for_template
from apps.worker.render_adapters._panels import render_wyr_panel


def test_dispatcher_pops_brand_kit_and_sets_context(tmp_path: Path):
    """Patch the panel adapter so we don't actually render — just
    confirm the context is set when the adapter runs."""
    captured: dict = {}

    def fake_render(typed, work_dir):
        captured["kit"] = _context.get_brand_kit()
        captured["template_input_keys"] = list(typed.model_dump().keys())
        out = work_dir / "fake.mp4"
        out.write_bytes(b"x" * 2000)
        return out

    raw = {
        "title": "Top 3 cities",
        "items": [
            {"title": "Tokyo"}, {"title": "Reykjavik"}, {"title": "Cape Town"},
        ],
        "_brand_kit": {"brand_color": "#1f6feb", "accent_color": "#101010"},
    }

    with patch(
        "apps.worker.render_adapters.top_five.render", side_effect=fake_render,
    ):
        result = render_for_template("top_five", raw, tmp_path)

    assert result.exists()
    assert captured["kit"]["brand_color"] == "#1f6feb"
    # _brand_kit must NOT have leaked through to the validated input.
    assert "_brand_kit" not in captured["template_input_keys"]


def test_context_is_cleared_after_render(tmp_path: Path):
    """After render_for_template returns, the next get_brand_kit()
    call must return {} so the kit doesn't leak across jobs."""

    def fake_render(typed, work_dir):
        out = work_dir / "fake.mp4"
        out.write_bytes(b"x" * 2000)
        return out

    raw_with_kit = {
        "title": "Top 3", "items": [
            {"title": "a"}, {"title": "b"}, {"title": "c"},
        ],
        "_brand_kit": {"brand_color": "#1f6feb"},
    }

    with patch(
        "apps.worker.render_adapters.top_five.render", side_effect=fake_render,
    ):
        render_for_template("top_five", raw_with_kit, tmp_path)

    # After the call, no kit active.
    assert _context.get_brand_kit() == {}


def test_panel_uses_brand_color_when_context_set(tmp_path: Path):
    """End-to-end: setting the context affects the rendered PNG.

    We don't pixel-check; we verify the call doesn't crash + a panel
    file lands. The full rendering integration is exercised by the
    Phase 2 panel adapter tests."""
    _context.set_brand_kit({"brand_color": "#1f6feb", "accent_color": "#101010"})
    try:
        out = render_wyr_panel(
            question="Brand kit smoke test for the WYR renderer?",
            option_a="Yes",
            option_b="No",
            color_a="#dc2626",
            color_b="#1f6feb",
            timer_label="3",
            pct_a=None, pct_b=None,
            size=(576, 1024),
            out_path=tmp_path / "wyr_smoke.png",
        )
        assert out.exists()
        assert out.stat().st_size > 1_000
    finally:
        _context.set_brand_kit(None)


def test_dispatcher_works_when_no_brand_kit_provided(tmp_path: Path):
    """Backward compat: jobs without _brand_kit must dispatch normally."""

    def fake_render(typed, work_dir):
        out = work_dir / "fake.mp4"
        out.write_bytes(b"x" * 2000)
        return out

    raw = {
        "title": "Top 3", "items": [
            {"title": "a"}, {"title": "b"}, {"title": "c"},
        ],
    }
    with patch(
        "apps.worker.render_adapters.top_five.render", side_effect=fake_render,
    ):
        out = render_for_template("top_five", raw, tmp_path)
    assert out.exists()
    # No leaked context.
    assert _context.get_brand_kit() == {}

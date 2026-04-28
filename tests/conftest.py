"""Shared pytest setup — make ``xvideo`` importable from tests + register
custom marks used by adapter integration tests."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def pytest_configure(config):
    """Register custom marks so ``-m`` selection works without warnings."""
    config.addinivalue_line(
        "markers",
        "slow: integration test that runs real TTS / ffmpeg — skip with "
        "'pytest -m \"not slow\"' for fast iteration.",
    )

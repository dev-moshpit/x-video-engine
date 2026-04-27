"""SaaS API package.

Adds the project root to ``sys.path`` so submodules can import the
plan-only surface of the engine (``xvideo.prompt_native``) without a
custom PYTHONPATH at process start. The api MUST stay on the cheap
surface — the heavy renderer lives in apps/worker.

The path adjustment is idempotent (no-op if the entry already exists).
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_root_str = str(_PROJECT_ROOT)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

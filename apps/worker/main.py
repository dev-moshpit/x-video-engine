"""SaaS render worker — Python process (PR 1 stub).

Pops ``RenderJobRequest`` payloads off Redis and runs the appropriate
render adapter. The full job loop arrives in PR 6; for PR 1 this is a
liveness stub that just verifies the process can start and the project
root is importable.

Run from the project root:

    py -3.11 apps/worker/main.py

or via the pnpm script:

    pnpm dev:worker
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

# Make the project root importable so the worker can pull from
# ``xvideo.*`` once PR 5 lands the render adapters.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("worker")


def main() -> int:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    log.info("worker starting (PR 1 stub) — redis_url=%s", redis_url)
    log.info("project_root=%s", _PROJECT_ROOT)
    log.info(
        "PR 5+ will smoke-import xvideo.prompt_native; "
        "PR 6 wires the consume loop"
    )
    log.info("idle — Ctrl-C to exit")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("shutdown")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

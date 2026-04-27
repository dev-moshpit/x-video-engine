"""SaaS render worker — Redis queue consumer (PR 6).

Loop:
  1. BLPOP a RenderJobRequest off the queue
  2. Mark renders.stage = "rendering"
  3. Validate template_input + dispatch to the right adapter
  4. On success: mark stage = "complete" (PR 7 will set final_mp4_url
     after uploading to R2 between "rendering" and "complete")
  5. On any exception: mark stage = "failed", store the message in
     renders.error

Run from the project root (after ``pnpm dev:infra`` brings up Redis +
Postgres):

    py -3.11 apps/worker/main.py

or via the pnpm script:

    pnpm dev:worker
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

# Make the project root importable so the worker can pull from xvideo.*
# and apps.worker.* without a custom PYTHONPATH at process start.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from apps.worker.queue import (  # noqa: E402
    consume_one,
    mark_stage,
    update_render_status,
)
from apps.worker.render_adapters import render_for_template  # noqa: E402
from apps.worker.schemas import RenderJobRequest, RenderStage  # noqa: E402
from apps.worker.storage import upload_render_mp4  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("worker")


WORK_ROOT = Path(os.getenv(
    "WORKER_WORK_ROOT",
    Path(tempfile.gettempdir()) / "xve_renders",
))


def run_one_job(req: RenderJobRequest) -> None:
    """Render a single job. Updates DB status as it progresses."""
    work_dir = WORK_ROOT / req.job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    log.info("[%s] template=%s starting", req.job_id, req.template)
    mark_stage(req.job_id, RenderStage.SCRIPTING, progress=0.05)
    mark_stage(req.job_id, RenderStage.RENDERING, progress=0.10)

    try:
        final_mp4 = render_for_template(
            req.template, req.template_input, work_dir,
        )
    except Exception as e:
        # The full traceback is helpful in the worker log; the user-facing
        # error message is the exception string.
        log.exception("[%s] render failed", req.job_id)
        update_render_status(
            req.job_id,
            stage=RenderStage.FAILED.value,
            progress=0.0,
            error=f"{type(e).__name__}: {e}",
            set_completed_now=True,
        )
        return

    # PR 7: upload to R2/MinIO between RENDERING and COMPLETE.
    mark_stage(req.job_id, RenderStage.UPLOADING, progress=0.92)
    try:
        public_url = upload_render_mp4(
            final_mp4, user_id=req.user_id, job_id=req.job_id,
        )
    except Exception as e:
        log.exception("[%s] upload failed", req.job_id)
        update_render_status(
            req.job_id,
            stage=RenderStage.FAILED.value,
            error=f"upload failed: {type(e).__name__}: {e}",
            set_completed_now=True,
        )
        return

    log.info("[%s] complete: %s", req.job_id, public_url)
    update_render_status(
        req.job_id,
        stage=RenderStage.COMPLETE.value,
        progress=1.0,
        final_mp4_url=public_url,
        set_completed_now=True,
    )


def main() -> int:
    log.info("worker starting — queue=Redis, work_root=%s", WORK_ROOT)
    while True:
        try:
            req = consume_one(timeout_sec=5)
        except KeyboardInterrupt:
            log.info("shutdown")
            return 0
        except Exception:
            log.exception("queue poll failed; backoff 5s")
            time.sleep(5)
            continue

        if req is None:
            continue

        try:
            run_one_job(req)
        except KeyboardInterrupt:
            # Mid-job interrupt: best-effort mark failed.
            update_render_status(
                req.job_id,
                stage=RenderStage.FAILED.value,
                error="worker interrupted",
                set_completed_now=True,
            )
            log.info("shutdown mid-job")
            return 0
        except Exception:
            log.exception("[%s] unexpected error in run_one_job", req.job_id)
            traceback.print_exc()


if __name__ == "__main__":
    raise SystemExit(main())

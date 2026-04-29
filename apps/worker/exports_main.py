"""Export-variant worker — Phase 13.5.

Independent loop that drains ``saas:export:jobs``. Each job downloads
the source mp4, runs an ffmpeg reframe, uploads the result to
R2/MinIO, and writes the public URL back into the artifact row.

Run separately from the main render worker:

    py -3.11 apps/worker/exports_main.py

Sharing the same Redis + DB connections as ``apps/worker/main.py`` is
fine — they touch different rows and queues.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

# Project-root sys.path bump (mirrors apps/worker/main.py).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from apps.worker.queue import (  # noqa: E402
    consume_export_one,
    update_artifact,
)
from apps.worker.render_adapters._reframe import reframe_to_aspect  # noqa: E402
from apps.worker.schemas import ExportJobRequest  # noqa: E402
from apps.worker.storage import get_s3_client, R2_BUCKET, R2_PUBLIC_BASE_URL  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("exports")


WORK_ROOT = Path(os.getenv(
    "WORKER_WORK_ROOT",
    Path(tempfile.gettempdir()) / "xve_exports",
))


def _artifact_key(user_id: str, job_id: str, artifact_id: str) -> str:
    return f"renders/{user_id}/{job_id}.export.{artifact_id}.mp4"


def process_export_job(req: ExportJobRequest) -> None:
    """Reframe → upload → write URL back to render_artifacts."""
    work_dir = WORK_ROOT / req.artifact_id
    work_dir.mkdir(parents=True, exist_ok=True)

    update_artifact(req.artifact_id, status="rendering")

    try:
        out_mp4 = reframe_to_aspect(
            src_url=req.src_url, aspect=req.aspect, work_dir=work_dir,
        )
    except Exception as e:
        log.exception("[%s] reframe failed", req.artifact_id)
        update_artifact(
            req.artifact_id,
            status="failed",
            error=f"{type(e).__name__}: {e}",
        )
        return

    try:
        key = _artifact_key(req.user_id, req.job_id, req.artifact_id)
        get_s3_client().upload_file(
            str(out_mp4), R2_BUCKET, key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
        public_url = f"{R2_PUBLIC_BASE_URL.rstrip('/')}/{key}"
    except Exception as e:
        log.exception("[%s] upload failed", req.artifact_id)
        update_artifact(
            req.artifact_id,
            status="failed",
            error=f"upload failed: {type(e).__name__}: {e}",
        )
        return

    update_artifact(req.artifact_id, status="complete", url=public_url)
    log.info("[%s] complete: %s", req.artifact_id, public_url)


def main() -> int:
    log.info("export worker starting — work_root=%s", WORK_ROOT)
    while True:
        try:
            req = consume_export_one(timeout_sec=5)
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
            process_export_job(req)
        except Exception as e:
            # Unhandled exception in process_export_job (e.g. update_artifact
            # itself failed because the DB connection died). Without this
            # fallback the artifact stays at "pending" forever and the user
            # sees no failure / no retry path. Best-effort write — if the
            # DB is unreachable we can't do anything but log.
            log.exception("[%s] unexpected error", req.artifact_id)
            try:
                update_artifact(
                    req.artifact_id,
                    status="failed",
                    error=f"{type(e).__name__}: {e}",
                )
            except Exception:
                log.exception(
                    "[%s] could not flip artifact to failed",
                    req.artifact_id,
                )


if __name__ == "__main__":
    raise SystemExit(main())

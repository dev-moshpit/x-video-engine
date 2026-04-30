"""Editor worker — Platform Phase 1.

Drains ``saas:editor:jobs``. Each job runs the
``apps.worker.editor.process_editor_job`` pipeline (trim, optional
captions, reframe), uploads the result to R2, and writes the public
URL back into the row.

Run separately from the main render / clipper workers:

    py -3.11 apps/worker/editor_main.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

# Project-root sys.path bump (mirrors apps/worker/main.py).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from apps.worker.editor import EditorJobInput, process_editor_job  # noqa: E402
from apps.worker.queue import (  # noqa: E402
    consume_editor_one,
    update_editor_job,
)
from apps.worker.storage import (  # noqa: E402
    R2_BUCKET,
    R2_PUBLIC_BASE_URL,
    ensure_bucket,
    get_s3_client,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("editor")


WORK_ROOT = Path(os.getenv(
    "WORKER_WORK_ROOT",
    Path(tempfile.gettempdir()) / "xve_editor",
))


def process_one(raw: str) -> None:
    payload = json.loads(raw)
    job_id = payload["job_id"]
    user_id = payload["user_id"]
    work_dir = WORK_ROOT / job_id

    log.info("[%s] editor starting", job_id)
    update_editor_job(job_id, status="running", progress=0.10)

    inp = EditorJobInput(
        source_url=payload["source_url"],
        trim_start=payload.get("trim_start"),
        trim_end=payload.get("trim_end"),
        aspect=payload.get("aspect", "9:16"),
        captions=bool(payload.get("captions", True)),
        caption_language=payload.get("caption_language", "auto"),
    )

    try:
        out_mp4 = process_editor_job(inp, work_dir)
    except Exception as e:
        log.exception("[%s] editor pipeline failed", job_id)
        update_editor_job(
            job_id,
            status="failed",
            error=f"{type(e).__name__}: {e}",
            set_completed_now=True,
        )
        return

    update_editor_job(job_id, progress=0.92)
    try:
        ensure_bucket(R2_BUCKET)
        key = f"editor/{user_id}/{job_id}.mp4"
        get_s3_client().upload_file(
            str(out_mp4), R2_BUCKET, key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
        public_url = f"{R2_PUBLIC_BASE_URL.rstrip('/')}/{key}"
    except Exception as e:
        log.exception("[%s] editor upload failed", job_id)
        update_editor_job(
            job_id,
            status="failed",
            error=f"upload failed: {type(e).__name__}: {e}",
            set_completed_now=True,
        )
        return

    update_editor_job(
        job_id,
        status="complete",
        progress=1.0,
        output_url=public_url,
        set_completed_now=True,
    )
    log.info("[%s] editor complete: %s", job_id, public_url)


def main() -> int:
    log.info("editor worker starting — work_root=%s", WORK_ROOT)
    while True:
        try:
            raw = consume_editor_one(timeout_sec=5)
        except KeyboardInterrupt:
            return 0
        except Exception:
            log.exception("queue poll failed; backoff 5s")
            time.sleep(5)
            continue
        if raw is None:
            continue
        try:
            process_one(raw)
        except Exception:
            log.exception("unexpected error in editor worker")


if __name__ == "__main__":
    raise SystemExit(main())

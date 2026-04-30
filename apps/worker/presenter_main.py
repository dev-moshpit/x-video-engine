"""Presenter worker — Platform Phase 1.

Drains ``saas:presenter:jobs``. Each job runs the chosen lipsync
provider (Wav2Lip / SadTalker / MuseTalk), optionally overlays a
news-style lower-third, uploads the result to R2, and writes the
public URL back into the row.

Run separately from other workers:

    py -3.11 apps/worker/presenter_main.py
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

from apps.worker.presenter import (  # noqa: E402
    PresenterNotAvailable,
    PresenterRequest,
    apply_news_template,
    get_presenter_provider,
)
from apps.worker.presenter.provider import UnknownPresenter  # noqa: E402
from apps.worker.queue import (  # noqa: E402
    consume_presenter_one,
    update_presenter_job,
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
log = logging.getLogger("presenter")


WORK_ROOT = Path(os.getenv(
    "WORKER_WORK_ROOT",
    Path(tempfile.gettempdir()) / "xve_presenter",
))


def process_one(raw: str) -> None:
    payload = json.loads(raw)
    job_id = payload["job_id"]
    user_id = payload["user_id"]
    provider_id = payload["provider_id"]
    work_dir = WORK_ROOT / job_id

    log.info("[%s] presenter starting (%s)", job_id, provider_id)
    update_presenter_job(job_id, status="running", progress=0.05)

    try:
        provider = get_presenter_provider(provider_id)
    except UnknownPresenter as e:
        update_presenter_job(
            job_id, status="failed",
            error=f"unknown presenter: {e}",
            set_completed_now=True,
        )
        return

    req = PresenterRequest(
        script=payload["script"],
        avatar_image_url=payload["avatar_image_url"],
        voice=payload.get("voice"),
        voice_rate=payload.get("voice_rate", "+0%"),
        aspect_ratio=payload.get("aspect_ratio", "9:16"),
        headline=payload.get("headline"),
        ticker=payload.get("ticker"),
    )

    update_presenter_job(job_id, progress=0.15)
    try:
        result = provider.render(req, work_dir)
    except PresenterNotAvailable as e:
        log.warning("[%s] presenter unavailable: %s", job_id, e)
        update_presenter_job(
            job_id,
            status="failed",
            error=f"{provider_id} unavailable: {e} (hint: {e.hint})",
            set_completed_now=True,
        )
        return
    except Exception as e:
        log.exception("[%s] presenter failed", job_id)
        update_presenter_job(
            job_id,
            status="failed",
            error=f"{type(e).__name__}: {e}",
            set_completed_now=True,
        )
        return

    final_mp4 = result.video_path
    update_presenter_job(job_id, progress=0.75)

    if req.headline:
        try:
            final_mp4 = apply_news_template(
                src_video=result.video_path,
                work_dir=work_dir,
                headline=req.headline,
                ticker=req.ticker,
                aspect=req.aspect_ratio,
            )
        except Exception as e:
            log.exception("[%s] news template failed", job_id)
            update_presenter_job(
                job_id,
                status="failed",
                error=f"news template overlay failed: {e}",
                set_completed_now=True,
            )
            return

    update_presenter_job(job_id, progress=0.92)
    try:
        ensure_bucket(R2_BUCKET)
        key = f"presenter/{user_id}/{job_id}.mp4"
        get_s3_client().upload_file(
            str(final_mp4), R2_BUCKET, key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
        public_url = f"{R2_PUBLIC_BASE_URL.rstrip('/')}/{key}"
    except Exception as e:
        log.exception("[%s] presenter upload failed", job_id)
        update_presenter_job(
            job_id,
            status="failed",
            error=f"upload failed: {type(e).__name__}: {e}",
            set_completed_now=True,
        )
        return

    update_presenter_job(
        job_id,
        status="complete",
        progress=1.0,
        output_url=public_url,
        set_completed_now=True,
    )
    log.info("[%s] presenter complete: %s", job_id, public_url)


def main() -> int:
    log.info("presenter worker starting — work_root=%s", WORK_ROOT)
    while True:
        try:
            raw = consume_presenter_one(timeout_sec=5)
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
            log.exception("unexpected error in presenter worker")


if __name__ == "__main__":
    raise SystemExit(main())

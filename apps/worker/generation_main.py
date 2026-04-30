"""Video-generation worker — Platform Phase 1.

Drains ``saas:videogen:jobs``. Each payload names a provider (sdxl_parallax,
svd, wan21, hunyuan_video, cogvideox) + the prompt + knobs. The worker
pulls the provider out of the registry, invokes ``generate``, uploads
the result to R2, and writes the public URL back into the row.

If the chosen provider isn't installed, ``generate`` raises
``ModelNotAvailable`` — we surface its install hint into ``error`` so
the operator sees exactly what's missing. There is no silent fallback.

Run separately from other workers:

    py -3.11 apps/worker/generation_main.py
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

from apps.worker.queue import (  # noqa: E402
    consume_generation_one,
    update_video_generation,
)
from apps.worker.storage import (  # noqa: E402
    R2_BUCKET,
    R2_PUBLIC_BASE_URL,
    ensure_bucket,
    get_s3_client,
)
from apps.worker.video_models import (  # noqa: E402
    GenerationRequest,
    ModelNotAvailable,
    get_provider,
)
from apps.worker.video_models.provider import UnknownProvider  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("videogen")


WORK_ROOT = Path(os.getenv(
    "WORKER_WORK_ROOT",
    Path(tempfile.gettempdir()) / "xve_videogen",
))


def process_one(raw: str) -> None:
    payload = json.loads(raw)
    job_id = payload["job_id"]
    user_id = payload["user_id"]
    provider_id = payload["provider_id"]
    work_dir = WORK_ROOT / job_id

    log.info("[%s] generate starting (%s)", job_id, provider_id)
    update_video_generation(job_id, status="running", progress=0.05)

    try:
        provider = get_provider(provider_id)
    except UnknownProvider as e:
        update_video_generation(
            job_id, status="failed",
            error=f"unknown provider: {e}",
            set_completed_now=True,
        )
        return

    req = GenerationRequest(
        prompt=payload["prompt"],
        duration_seconds=float(payload.get("duration_seconds", 4.0)),
        fps=int(payload.get("fps", 24)),
        seed=payload.get("seed"),
        aspect_ratio=payload.get("aspect_ratio", "9:16"),
        image_url=payload.get("image_url"),
        extra=payload.get("extra") or {},
    )

    update_video_generation(job_id, progress=0.10)
    try:
        out_mp4 = provider.generate(req, work_dir)
    except ModelNotAvailable as e:
        log.warning("[%s] provider not available: %s", job_id, e)
        update_video_generation(
            job_id,
            status="failed",
            error=f"{provider_id} unavailable: {e} (hint: {e.hint})",
            set_completed_now=True,
        )
        return
    except Exception as e:
        log.exception("[%s] generation failed", job_id)
        update_video_generation(
            job_id,
            status="failed",
            error=f"{type(e).__name__}: {e}",
            set_completed_now=True,
        )
        return

    update_video_generation(job_id, progress=0.92)
    try:
        ensure_bucket(R2_BUCKET)
        key = f"videogen/{user_id}/{job_id}.mp4"
        get_s3_client().upload_file(
            str(out_mp4), R2_BUCKET, key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
        public_url = f"{R2_PUBLIC_BASE_URL.rstrip('/')}/{key}"
    except Exception as e:
        log.exception("[%s] upload failed", job_id)
        update_video_generation(
            job_id,
            status="failed",
            error=f"upload failed: {type(e).__name__}: {e}",
            set_completed_now=True,
        )
        return

    update_video_generation(
        job_id,
        status="complete",
        progress=1.0,
        output_url=public_url,
        set_completed_now=True,
    )
    log.info("[%s] complete: %s", job_id, public_url)


def main() -> int:
    log.info("video-generation worker starting — work_root=%s", WORK_ROOT)
    while True:
        try:
            raw = consume_generation_one(timeout_sec=5)
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
            log.exception("unexpected error in videogen worker")


if __name__ == "__main__":
    raise SystemExit(main())

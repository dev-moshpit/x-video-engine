"""Publishing worker — Platform Phase 1.

Drains ``saas:publish:jobs``. For each request, calls the right
provider's ``upload`` and writes the resulting external_id /
external_url into the row. If the provider isn't configured, the row
flips to failed with the setup hint — no silent skip.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

# Project-root sys.path bump.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from apps.worker.publishing import (  # noqa: E402
    PublishingNotConfigured,
    PublishingRequest,
    get_publishing_provider,
)
from apps.worker.publishing.provider import UnknownPublisher  # noqa: E402
from apps.worker.queue import (  # noqa: E402
    consume_publish_one,
    update_publishing_job,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("publishing")


def process_one(raw: str) -> None:
    payload = json.loads(raw)
    job_id = payload["job_id"]
    provider_id = payload["provider_id"]

    log.info("[%s] publish starting (%s)", job_id, provider_id)
    update_publishing_job(job_id, status="running")

    try:
        provider = get_publishing_provider(provider_id)
    except UnknownPublisher as e:
        update_publishing_job(
            job_id, status="failed",
            error=f"unknown publisher: {e}",
            set_completed_now=True,
        )
        return

    req = PublishingRequest(
        provider_id=provider_id,
        video_url=payload["video_url"],
        title=payload["title"],
        description=payload.get("description", ""),
        tags=list(payload.get("tags") or []),
        privacy=payload.get("privacy", "private"),
    )

    try:
        result = provider.upload(req)
    except PublishingNotConfigured as e:
        log.warning("[%s] provider not configured: %s", job_id, e)
        update_publishing_job(
            job_id, status="failed",
            error=f"{provider_id} not configured: {e} (hint: {e.hint})",
            set_completed_now=True,
        )
        return
    except Exception as e:
        log.exception("[%s] upload failed", job_id)
        update_publishing_job(
            job_id, status="failed",
            error=f"{type(e).__name__}: {e}",
            set_completed_now=True,
        )
        return

    update_publishing_job(
        job_id,
        status="complete",
        external_id=result.external_id,
        external_url=result.external_url,
        set_completed_now=True,
    )
    log.info("[%s] published: %s", job_id, result.external_url)


def main() -> int:
    log.info("publishing worker starting")
    while True:
        try:
            raw = consume_publish_one(timeout_sec=5)
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
            log.exception("unexpected error in publishing worker")


if __name__ == "__main__":
    raise SystemExit(main())

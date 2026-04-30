"""AI Clipper worker — Platform Phase 1.

Drains two Redis queues:

  saas:clipper:analyze   transcribe + segment + score
  saas:clipper:export    cut one moment → mp4 + caption burn + upload

Run separately from the main render / export workers:

    py -3.11 apps/worker/clipper_main.py
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from time import monotonic

# Project-root sys.path bump (mirrors apps/worker/main.py).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from apps.worker.ai_clipper import (  # noqa: E402
    export_one_clip,
    find_moments,
    score_moments,
    transcribe_full,
)
from apps.worker.queue import (  # noqa: E402
    CLIPPER_ANALYZE_QUEUE_KEY,
    consume_clipper_one,
    update_clip_artifact,
    update_clip_job,
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
log = logging.getLogger("clipper")


WORK_ROOT = Path(os.getenv(
    "WORKER_WORK_ROOT",
    Path(tempfile.gettempdir()) / "xve_clipper",
))


# ─── Helpers ───────────────────────────────────────────────────────────


def _download_to(work_dir: Path, url: str) -> Path:
    """Resolve ``url`` (http(s) or local path) into ``work_dir/source.*``."""
    work_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(url.split("?")[0]).suffix or ".bin"
    dst = work_dir / f"source{suffix}"
    if url.startswith(("http://", "https://")):
        urllib.request.urlretrieve(url, dst)
    else:
        src = Path(url)
        if not src.exists():
            raise FileNotFoundError(f"clipper source missing: {url}")
        dst.write_bytes(src.read_bytes())
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(f"download produced empty file for {url}")
    return dst


def _serialize_moments_with_scores(moments, scores) -> list[dict]:
    """Bundle moment + score into the JSON the api ships to the frontend.

    The frontend's Moment shape needs both ranges and the score
    breakdown so the dashboard can show why a clip was picked. We
    keep the per-segment text + start/end inline so the export step
    has everything without a second DB read.
    """
    out: list[dict] = []
    for m, s in zip(moments, scores):
        out.append({
            "moment_id": m.moment_id,
            "start": m.start,
            "end": m.end,
            "duration": m.duration,
            "text": m.text,
            "segments": [
                {
                    "id": seg.id,
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                    "words": [dataclasses.asdict(w) for w in seg.words],
                    "avg_logprob": seg.avg_logprob,
                    "no_speech_prob": seg.no_speech_prob,
                }
                for seg in m.segments
            ],
            "score": s.total,
            "score_breakdown": {
                "hook_strength": s.hook_strength,
                "emotional_spike": s.emotional_spike,
                "controversy": s.controversy,
                "clarity": s.clarity,
                "length_fit": s.length_fit,
                "speaker_energy": s.speaker_energy,
                "caption_potential": s.caption_potential,
            },
            "notes": list(s.notes),
        })
    return out


def _moment_from_payload(payload: dict):
    """Rebuild a Moment + TranscriptSegment tree from the api payload.

    The api hands back the same JSON the analyze step wrote — we just
    rehydrate the dataclasses so :func:`export_one_clip` can use them.
    """
    from apps.worker.ai_clipper.segment import Moment
    from apps.worker.ai_clipper.transcribe import (
        TranscriptSegment,
        TranscriptWord,
    )
    segs: list[TranscriptSegment] = []
    for seg in (payload.get("segments") or []):
        words = tuple(
            TranscriptWord(text=w.get("text", ""),
                           start=float(w.get("start", 0.0)),
                           end=float(w.get("end", 0.0)))
            for w in (seg.get("words") or [])
        )
        segs.append(TranscriptSegment(
            id=int(seg.get("id", 0)),
            start=float(seg.get("start", 0.0)),
            end=float(seg.get("end", 0.0)),
            text=seg.get("text", ""),
            words=words,
            avg_logprob=float(seg.get("avg_logprob", 0.0)),
            no_speech_prob=float(seg.get("no_speech_prob", 0.0)),
        ))
    return Moment(
        moment_id=payload.get("moment_id", "m000"),
        start=float(payload.get("start", 0.0)),
        end=float(payload.get("end", 0.0)),
        text=payload.get("text", ""),
        segments=tuple(segs),
    )


# ─── Job processors ────────────────────────────────────────────────────


def process_analyze(req_json: str) -> None:
    """Transcribe → segment → score → write moments back to DB."""
    payload = json.loads(req_json)
    job_id = payload["job_id"]
    work_dir = WORK_ROOT / job_id

    log.info("[%s] analyze starting (source=%s)", job_id, payload["source_url"])
    started = monotonic()
    update_clip_job(job_id, status="running", progress=0.05)

    try:
        media = _download_to(work_dir, payload["source_url"])
        update_clip_job(job_id, progress=0.15)
        transcript = transcribe_full(
            media=media,
            work_dir=work_dir,
            language=payload.get("language", "auto"),
        )
        update_clip_job(
            job_id,
            progress=0.65,
            duration_sec=transcript.duration,
            transcript_text=transcript.text,
        )
        moments = find_moments(transcript)
        scores = score_moments(moments)
        moment_payload = _serialize_moments_with_scores(moments, scores)
        update_clip_job(
            job_id,
            status="complete",
            progress=1.0,
            moments=moment_payload,
            set_completed_now=True,
        )
        log.info(
            "[%s] analyze complete: %d moments in %.1fs",
            job_id, len(moments), monotonic() - started,
        )
    except Exception as e:
        log.exception("[%s] analyze failed", job_id)
        update_clip_job(
            job_id,
            status="failed",
            error=f"{type(e).__name__}: {e}",
            set_completed_now=True,
        )


def process_export(req_json: str) -> None:
    """Cut one moment → upload → write URL into the artifact row."""
    payload = json.loads(req_json)
    artifact_id = payload["artifact_id"]
    user_id = payload["user_id"]
    job_id = payload["job_id"]

    work_dir = WORK_ROOT / f"{job_id}_export_{artifact_id[:8]}"
    update_clip_artifact(artifact_id, status="running")

    try:
        moment = _moment_from_payload(payload["moment"])
        out_mp4 = export_one_clip(
            src_url=payload["source_url"],
            moment=moment,
            work_dir=work_dir,
            aspect=payload.get("aspect", "9:16"),
            burn_captions=bool(payload.get("captions", True)),
        )
    except Exception as e:
        log.exception("[%s] clip export failed", artifact_id)
        update_clip_artifact(
            artifact_id,
            status="failed",
            error=f"{type(e).__name__}: {e}",
        )
        return

    try:
        ensure_bucket(R2_BUCKET)
        key = f"clips/{user_id}/{job_id}/{artifact_id}.mp4"
        get_s3_client().upload_file(
            str(out_mp4),
            R2_BUCKET, key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
        public_url = f"{R2_PUBLIC_BASE_URL.rstrip('/')}/{key}"
    except Exception as e:
        log.exception("[%s] upload failed", artifact_id)
        update_clip_artifact(
            artifact_id,
            status="failed",
            error=f"upload failed: {type(e).__name__}: {e}",
        )
        return

    update_clip_artifact(artifact_id, status="complete", url=public_url)
    log.info("[%s] clip ready: %s", artifact_id, public_url)


# ─── Main loop ─────────────────────────────────────────────────────────


def main() -> int:
    log.info("clipper worker starting — work_root=%s", WORK_ROOT)
    while True:
        try:
            queue, raw = consume_clipper_one(timeout_sec=5)
        except KeyboardInterrupt:
            log.info("shutdown")
            return 0
        except Exception:
            log.exception("queue poll failed; backoff 5s")
            time.sleep(5)
            continue
        if queue is None or raw is None:
            continue
        try:
            if queue == CLIPPER_ANALYZE_QUEUE_KEY:
                process_analyze(raw)
            else:
                process_export(raw)
        except Exception:
            log.exception("[%s] unexpected error in clipper worker", queue)


if __name__ == "__main__":
    raise SystemExit(main())

"""R2 / S3-compatible upload (PR 7).

Uses boto3 with an explicit ``endpoint_url`` so the same code path
works against:
  - real Cloudflare R2 (``https://<account>.r2.cloudflarestorage.com``)
  - local MinIO from docker-compose.dev.yaml (``http://localhost:9000``)
  - moto in tests (any endpoint; intercepted at the botocore layer)

The worker (``apps/worker/main.py``) calls ``upload_render_mp4`` after
the render adapter produces a final mp4 and before marking the
``renders.stage`` complete.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger(__name__)


R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "http://localhost:9000")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "minioadmin")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "minioadmin")
R2_BUCKET = os.environ.get("R2_BUCKET", "renders-dev")
R2_PUBLIC_BASE_URL = os.environ.get(
    "R2_PUBLIC_BASE_URL", f"{R2_ENDPOINT}/{R2_BUCKET}",
)
R2_REGION = os.environ.get("R2_REGION", "auto")


_client = None


def get_s3_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name=R2_REGION,
        )
    return _client


def set_s3_client(client) -> None:
    """Test hook — install a moto-mocked client."""
    global _client
    _client = client


def ensure_bucket(bucket: str = R2_BUCKET) -> None:
    """Create the bucket if it doesn't exist. Idempotent."""
    client = get_s3_client()
    try:
        client.head_bucket(Bucket=bucket)
        return
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code not in ("404", "NoSuchBucket", "NotFound"):
            raise
    client.create_bucket(Bucket=bucket)


def render_key_for(user_id: str, job_id: str) -> str:
    """Stable object key. Sharded by user so listings are bounded."""
    return f"renders/{user_id}/{job_id}.mp4"


def upload_render_mp4(
    local_path: Path,
    *,
    user_id: str,
    job_id: str,
    bucket: str = R2_BUCKET,
    public_base_url: Optional[str] = None,
) -> str:
    """Upload ``local_path`` to ``{bucket}/renders/{user_id}/{job_id}.mp4``.

    Returns the public URL (composed from ``public_base_url`` or the
    module default ``R2_PUBLIC_BASE_URL``). The bucket is created on
    demand; the upload sets ``Content-Type: video/mp4``.
    """
    if not local_path.exists():
        raise FileNotFoundError(f"render mp4 missing: {local_path}")

    ensure_bucket(bucket)

    key = render_key_for(user_id, job_id)
    base = public_base_url or R2_PUBLIC_BASE_URL

    logger.info(
        "uploading %s → s3://%s/%s (%d bytes)",
        local_path, bucket, key, local_path.stat().st_size,
    )
    get_s3_client().upload_file(
        str(local_path),
        bucket,
        key,
        ExtraArgs={"ContentType": "video/mp4"},
    )
    return f"{base.rstrip('/')}/{key}"

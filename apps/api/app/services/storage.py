"""Presigned upload URLs (PR 7).

Used for client-side direct uploads of media that the worker will then
reference by URL — currently the voiceover template's
``background_url`` and the auto-captions audio (Phase 2). Returns a
PUT URL valid for a short window (default 15 min).

The api never streams large files itself; all client-side uploads go
straight to R2/MinIO with a presigned PUT.
"""

from __future__ import annotations

import os
import uuid
from typing import Optional

import boto3


R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "http://localhost:9000")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "minioadmin")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "minioadmin")
R2_BUCKET = os.environ.get("R2_BUCKET", "renders-dev")
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


_ALLOWED_KINDS = {"audio", "video", "image"}
_KIND_PREFIXES = {"audio": "uploads/audio", "video": "uploads/video",
                   "image": "uploads/image"}


def make_presigned_put(
    *,
    user_id: str,
    kind: str,
    content_type: str,
    expires_sec: int = 900,
) -> dict:
    """Return a PUT URL the browser uses to upload directly to R2.

    Returns ``{"url", "key", "expires_in", "method": "PUT"}``. Caller
    saves ``key`` so the worker can later read the object by key.
    """
    if kind not in _ALLOWED_KINDS:
        raise ValueError(
            f"unsupported upload kind '{kind}' — known: {sorted(_ALLOWED_KINDS)}"
        )
    key = f"{_KIND_PREFIXES[kind]}/{user_id}/{uuid.uuid4().hex}"
    url = get_s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": R2_BUCKET,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_sec,
        HttpMethod="PUT",
    )
    return {
        "url": url,
        "key": key,
        "method": "PUT",
        "expires_in": expires_sec,
        "content_type": content_type,
    }

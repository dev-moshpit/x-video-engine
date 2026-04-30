"""YouTube Data API publisher — Platform Phase 1.

Uses an OAuth2 refresh token (env: ``YOUTUBE_REFRESH_TOKEN``) plus the
client_id / client_secret of a registered Google Cloud OAuth client.
The full per-user OAuth consent flow lands in Phase 7+; for Phase 1
we ship the platform-level credentials path so a single account (the
operator's) can publish via the api.

Required env vars:

  YOUTUBE_CLIENT_ID
  YOUTUBE_CLIENT_SECRET
  YOUTUBE_REFRESH_TOKEN

Required python deps:

  google-auth-oauthlib
  google-api-python-client

If any are missing the provider reports ``configured=False`` and the
api surfaces the setup hint. There is no silent skip.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import urllib.request
import uuid
from pathlib import Path
from tempfile import gettempdir
from typing import Optional

from apps.worker.publishing.base import (
    PublishingNotConfigured,
    PublishingProviderInfo,
    PublishingRequest,
    PublishingResult,
)


logger = logging.getLogger(__name__)


_PROVIDER_ID = "youtube"
_REQUIRED_ENV = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
                 "YOUTUBE_REFRESH_TOKEN")
_REQUIRED_MODULES = ("googleapiclient.discovery", "google.oauth2.credentials")


def _missing_env() -> list[str]:
    return [e for e in _REQUIRED_ENV if not os.environ.get(e)]


def _missing_modules() -> list[str]:
    out: list[str] = []
    for mod in _REQUIRED_MODULES:
        try:
            if importlib.util.find_spec(mod) is None:
                out.append(mod)
        except (ValueError, ImportError, ModuleNotFoundError):
            out.append(mod)
    return out


def _info(configured: bool, error: Optional[str] = None) -> PublishingProviderInfo:
    return PublishingProviderInfo(
        id=_PROVIDER_ID,
        name="YouTube (Data API v3)",
        configured=configured,
        setup_hint=(
            "Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and "
            "YOUTUBE_REFRESH_TOKEN; install google-api-python-client + "
            "google-auth-oauthlib"
        ),
        error=error,
        description=(
            "Uploads via the YouTube Data API. Requires an OAuth2 "
            "refresh token from a Google Cloud project."
        ),
    )


class YouTubeProvider:

    @property
    def info(self) -> PublishingProviderInfo:
        miss_env = _missing_env()
        miss_mod = _missing_modules()
        if miss_env or miss_mod:
            problems: list[str] = []
            if miss_env:
                problems.append(f"missing env: {', '.join(miss_env)}")
            if miss_mod:
                problems.append(f"missing python module(s): {', '.join(miss_mod)}")
            return _info(False, error="; ".join(problems))
        return _info(True)

    def upload(self, req: PublishingRequest) -> PublishingResult:
        info = self.info
        if not info.configured:
            raise PublishingNotConfigured(
                _PROVIDER_ID,
                info.error or "youtube provider not configured",
                info.setup_hint,
            )

        try:
            from google.oauth2.credentials import Credentials  # type: ignore
            from googleapiclient.discovery import build  # type: ignore
            from googleapiclient.http import MediaFileUpload  # type: ignore
        except ImportError as e:
            raise PublishingNotConfigured(
                _PROVIDER_ID,
                f"google client libs not importable: {e}",
                info.setup_hint,
            ) from e

        creds = Credentials(
            token=None,
            refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
            token_uri="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )

        # Resolve the video file. If it's an http(s) url, download into a
        # temp file first — google's MediaFileUpload only takes paths.
        if req.video_url.startswith(("http://", "https://")):
            tmp = Path(gettempdir()) / f"yt_upload_{uuid.uuid4().hex[:12]}.mp4"
            urllib.request.urlretrieve(req.video_url, tmp)
            local_path = tmp
        else:
            local_path = Path(req.video_url)
            if not local_path.exists():
                raise PublishingNotConfigured(
                    _PROVIDER_ID,
                    f"source video not found: {req.video_url}",
                    "ensure the video URL or local path is reachable",
                )

        privacy = req.privacy if req.privacy in (
            "public", "unlisted", "private",
        ) else "private"

        body = {
            "snippet": {
                "title": req.title[:100],
                "description": req.description[:5000],
                "tags": [t[:30] for t in (req.tags or [])][:25],
                "categoryId": str(req.extra.get("category_id", "22")),
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            str(local_path),
            chunksize=-1, resumable=True,
            mimetype="video/mp4",
        )
        youtube = build("youtube", "v3", credentials=creds)
        request = youtube.videos().insert(
            part="snippet,status", body=body, media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(
                    "youtube upload progress: %.1f%%",
                    status.progress() * 100,
                )

        video_id = response.get("id")
        if not video_id:
            raise RuntimeError(f"youtube upload missing id: {response}")

        return PublishingResult(
            provider_id=_PROVIDER_ID,
            external_id=video_id,
            external_url=f"https://www.youtube.com/watch?v={video_id}",
            raw_response=response or {},
        )

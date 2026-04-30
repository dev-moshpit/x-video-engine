"""Publishing provider abstraction tests — Platform Phase 1."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.worker.publishing import (
    PublishingNotConfigured,
    PublishingProviderInfo,
    PublishingRequest,
    get_publishing_provider,
    list_publishing_providers,
)
from apps.worker.publishing.provider import UnknownPublisher


def test_list_providers_includes_youtube():
    infos = list_publishing_providers()
    ids = {p.id for p in infos}
    assert "youtube" in ids


def test_provider_info_well_formed():
    for info in list_publishing_providers():
        assert isinstance(info, PublishingProviderInfo)
        assert info.id
        assert info.name
        assert isinstance(info.configured, bool)
        if not info.configured:
            assert info.setup_hint
            assert info.error


def test_get_unknown_publisher_raises():
    with pytest.raises(UnknownPublisher):
        get_publishing_provider("not_a_real_publisher_xyz")


def test_youtube_unconfigured_upload_raises():
    """No silent skip when env vars are absent."""
    from apps.worker.publishing.youtube import YouTubeProvider

    fake = PublishingProviderInfo(
        id="youtube", name="YouTube",
        configured=False, setup_hint="set YOUTUBE_*",
        error="missing env",
    )
    with patch.object(
        YouTubeProvider, "info", new=property(lambda self: fake),
    ):
        provider = YouTubeProvider()
        with pytest.raises(PublishingNotConfigured) as ei:
            provider.upload(PublishingRequest(
                provider_id="youtube",
                video_url="https://example.com/x.mp4",
                title="hi",
            ))
        assert ei.value.provider_id == "youtube"
        assert ei.value.hint


def test_youtube_info_reflects_env_state():
    """The info probe respects YOUTUBE_* env presence."""
    with patch.dict("os.environ", {}, clear=False) as env:
        for key in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
                    "YOUTUBE_REFRESH_TOKEN"):
            env.pop(key, None)
        info = get_publishing_provider("youtube").info
    assert info.configured is False
    assert "missing env" in (info.error or "") or \
           "missing python module" in (info.error or "")

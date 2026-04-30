"""Presenter pipeline tests — Platform Phase 1.

Exercises:
  * Provider registry — list_presenter_providers, get_presenter_provider.
  * Each provider's ``info`` probe never raises and reports installed=False
    cleanly when the upstream repo isn't on disk.
  * ``render`` raises PresenterNotAvailable when info.installed is False
    (no silent fake fallback).
  * news_template overlay produces a real mp4 against a synthetic input.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import imageio_ffmpeg
import pytest

from apps.worker.presenter import (
    PresenterNotAvailable,
    PresenterProviderInfo,
    PresenterRequest,
    apply_news_template,
    get_presenter_provider,
    list_presenter_providers,
)
from apps.worker.presenter.provider import UnknownPresenter


def test_list_presenter_providers_returns_all_known():
    infos = list_presenter_providers()
    ids = {p.id for p in infos}
    assert {"wav2lip", "sadtalker", "musetalk"}.issubset(ids)


def test_each_provider_info_is_well_formed():
    for info in list_presenter_providers():
        assert isinstance(info, PresenterProviderInfo)
        assert info.id
        assert info.name
        assert isinstance(info.installed, bool)
        if not info.installed:
            assert info.install_hint
            assert info.error


def test_get_unknown_presenter_raises():
    with pytest.raises(UnknownPresenter):
        get_presenter_provider("definitely_not_a_real_presenter")


def test_uninstalled_provider_render_raises(tmp_path: Path):
    """No silent fallback — render must raise PresenterNotAvailable
    when the chosen provider isn't installed."""
    from apps.worker.presenter.wav2lip_adapter import Wav2LipPresenter

    fake = PresenterProviderInfo(
        id="wav2lip",
        name="Wav2Lip",
        installed=False,
        install_hint="git clone …",
        error="not configured",
    )
    with patch.object(
        Wav2LipPresenter, "info", new=property(lambda self: fake),
    ):
        provider = Wav2LipPresenter()
        with pytest.raises(PresenterNotAvailable) as ei:
            provider.render(
                PresenterRequest(
                    script="hello world",
                    avatar_image_url="http://localhost/avatar.png",
                ),
                tmp_path,
            )
        assert ei.value.provider_id == "wav2lip"
        assert ei.value.hint  # hint propagated


def _make_silent_video(out: Path, duration: float = 4.0) -> Path:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-t", f"{duration:.2f}",
        "-f", "lavfi",
        "-i", "color=c=black:s=320x240:r=24",
        "-t", f"{duration:.2f}",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=mono:sample_rate=16000",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-400:]
    return out


def test_apply_news_template_overlays_banner(tmp_path: Path):
    src = _make_silent_video(tmp_path / "src.mp4", duration=3.0)
    out = apply_news_template(
        src_video=src,
        work_dir=tmp_path,
        headline="LIVE: TEST EVENT IN PROGRESS",
        ticker="Markets up · Eagles win · …",
        aspect="9:16",
    )
    assert out.exists()
    assert out.stat().st_size > 5_000


def test_news_template_rejects_unknown_aspect(tmp_path: Path):
    src = _make_silent_video(tmp_path / "src.mp4", duration=2.0)
    with pytest.raises(ValueError):
        apply_news_template(
            src_video=src,
            work_dir=tmp_path,
            headline="x",
            aspect="4:3",
        )


def test_news_template_works_without_ticker(tmp_path: Path):
    src = _make_silent_video(tmp_path / "src.mp4", duration=2.0)
    out = apply_news_template(
        src_video=src,
        work_dir=tmp_path,
        headline="HEADLINE ONLY",
        ticker=None,
        aspect="16:9",
    )
    assert out.exists()
    assert out.stat().st_size > 5_000

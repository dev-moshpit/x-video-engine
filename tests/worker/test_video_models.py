"""Video-model provider abstraction tests — Platform Phase 1.

Two layers:

  1. Registry — list_providers + get_provider + UnknownProvider.
  2. Each provider's ``info`` probe — must return ProviderInfo with
     ``installed`` reflecting actual machine state, never raise.
  3. Each provider's ``generate`` — when ``installed=False``, raises
     :class:`ModelNotAvailable` with a hint (no silent fake fallback).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from apps.worker.video_models import (
    GenerationRequest,
    ModelNotAvailable,
    ProviderInfo,
    get_provider,
    list_providers,
)
from apps.worker.video_models.provider import UnknownProvider


def test_list_providers_returns_all_known_backends():
    infos = list_providers()
    ids = {p.id for p in infos}
    expected = {"sdxl_parallax", "svd", "wan21", "hunyuan_video", "cogvideox"}
    assert expected.issubset(ids)


def test_each_provider_info_is_well_formed():
    for info in list_providers():
        assert isinstance(info, ProviderInfo)
        assert info.id
        assert info.name
        assert info.mode in ("text-to-video", "image-to-video")
        assert info.required_vram_gb >= 0.0
        assert isinstance(info.installed, bool)
        # If not installed, the operator must see a hint.
        if not info.installed:
            assert info.install_hint
            assert info.error is not None


def test_get_provider_returns_provider_with_info():
    p = get_provider("sdxl_parallax")
    assert p.info.id == "sdxl_parallax"


def test_get_unknown_provider_raises():
    with pytest.raises(UnknownProvider):
        get_provider("definitely_not_a_real_provider_xyz")


def test_provider_info_unaffected_by_torch_absence():
    """Removing torch from sys.modules must not crash the info probe."""
    # Force importlib.util.find_spec to return None for torch.
    real_spec = __import__("importlib").util.find_spec

    def fake_spec(name):
        if name in ("torch", "diffusers"):
            return None
        return real_spec(name)

    with patch(
        "apps.worker.video_models.svd_provider.importlib.util.find_spec",
        side_effect=fake_spec,
    ):
        info = get_provider("svd").info
        assert info.installed is False
        assert "not importable" in (info.error or "")


def test_unavailable_provider_generate_raises_model_not_available(tmp_path: Path):
    """If a provider isn't installed, ``generate`` must raise the
    user-visible exception with a hint — never silently return a
    different model's output."""
    # Force the SVD provider to report not-installed via patching its
    # info property, then call generate.
    from apps.worker.video_models.svd_provider import SVDProvider

    not_installed_info = ProviderInfo(
        id="svd",
        name="SVD",
        mode="image-to-video",
        required_vram_gb=12.0,
        installed=False,
        install_hint="huggingface-cli download stabilityai/...",
        error="weight cache missing",
    )

    with patch.object(SVDProvider, "info", new=property(lambda self: not_installed_info)):
        provider = SVDProvider()
        with pytest.raises(ModelNotAvailable) as ei:
            provider.generate(
                GenerationRequest(
                    prompt="test",
                    image_url="http://example.com/x.png",
                ),
                tmp_path,
            )
        assert ei.value.provider_id == "svd"
        assert ei.value.hint  # hint is propagated


def test_svd_rejects_missing_image_url(tmp_path: Path):
    """SVD is image-to-video; a request without image_url must fail."""
    from apps.worker.video_models.svd_provider import SVDProvider

    fake_installed = ProviderInfo(
        id="svd",
        name="SVD",
        mode="image-to-video",
        required_vram_gb=12.0,
        installed=True,
        install_hint="",
    )
    with patch.object(SVDProvider, "info", new=property(lambda self: fake_installed)):
        provider = SVDProvider()
        with pytest.raises(ModelNotAvailable) as ei:
            provider.generate(
                GenerationRequest(prompt="anything"),
                tmp_path,
            )
        assert "image_url" in str(ei.value)


def test_text_to_video_providers_have_correct_mode():
    expect = {
        "sdxl_parallax": "text-to-video",
        "wan21": "text-to-video",
        "hunyuan_video": "text-to-video",
        "cogvideox": "text-to-video",
        "svd": "image-to-video",
    }
    for pid, mode in expect.items():
        assert get_provider(pid).info.mode == mode


def test_no_silent_fallback_via_get_provider():
    """``get_provider("wan21")`` must always return the wan21 instance,
    never substitute SDXL parallax even if Wan is uninstalled."""
    p = get_provider("wan21")
    assert p.info.id == "wan21"
    p2 = get_provider("hunyuan_video")
    assert p2.info.id == "hunyuan_video"


def test_generation_request_carries_extra_dict():
    req = GenerationRequest(
        prompt="a", duration_seconds=2.0, fps=24, seed=7,
        extra={"guidance_scale": 7.5},
    )
    assert req.extra["guidance_scale"] == 7.5

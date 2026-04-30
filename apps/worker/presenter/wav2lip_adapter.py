"""Wav2Lip presenter adapter — Platform Phase 1.

Wav2Lip is a lightweight (~4 GB VRAM) lipsync model. Operators install
it manually because the upstream repo doesn't ship a pip package — we
look for the checkpoints at ``XVE_MODELS_DIR/wav2lip/checkpoints/``.

The ``inference.py`` script that ships with the upstream Wav2Lip repo
produces an output mp4 in one CLI call. We invoke it via subprocess
with a strict timeout so a stuck process can't hang the worker queue.

If the runtime / weights aren't present, the adapter raises
:class:`PresenterNotAvailable` from ``info`` access (so the provider
listing reflects reality) and from ``render`` (so the worker fails
fast with the install hint).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from apps.worker.presenter._tts import fetch_image, synthesize_voice
from apps.worker.presenter.base import (
    PresenterNotAvailable,
    PresenterProviderInfo,
    PresenterRequest,
    PresenterResult,
)


logger = logging.getLogger(__name__)


_PROVIDER_ID = "wav2lip"


def _models_root() -> Optional[Path]:
    if env := os.environ.get("XVE_MODELS_DIR"):
        return Path(env)
    return None


def _wav2lip_root() -> Optional[Path]:
    """Return the wav2lip checkout directory if configured."""
    if env := os.environ.get("XVE_WAV2LIP_DIR"):
        return Path(env)
    if root := _models_root():
        cand = root / "wav2lip"
        if cand.exists():
            return cand
    return None


def _wav2lip_checkpoint() -> Optional[Path]:
    """Return the path to the wav2lip checkpoint .pth file, if present."""
    root = _wav2lip_root()
    if root is None:
        return None
    for sub in ("checkpoints", "."):
        for name in ("wav2lip_gan.pth", "wav2lip.pth"):
            cand = root / sub / name
            if cand.exists():
                return cand
    return None


def _info(installed: bool, error: Optional[str] = None,
          cache_path: Optional[str] = None) -> PresenterProviderInfo:
    return PresenterProviderInfo(
        id=_PROVIDER_ID,
        name="Wav2Lip (lipsync)",
        installed=installed,
        install_hint=(
            "git clone https://github.com/Rudrabha/Wav2Lip into "
            "$XVE_MODELS_DIR/wav2lip + download wav2lip_gan.pth into "
            "$XVE_MODELS_DIR/wav2lip/checkpoints"
        ),
        error=error,
        cache_path=cache_path,
        description=(
            "Lightweight lipsync. Needs OpenCV + the upstream Wav2Lip "
            "checkpoint."
        ),
        required_vram_gb=4.0,
    )


class Wav2LipPresenter:

    @property
    def info(self) -> PresenterProviderInfo:
        if shutil.which("python") is None and shutil.which("python3") is None:
            return _info(False, error="no python interpreter on PATH")
        root = _wav2lip_root()
        if root is None:
            return _info(False, error="wav2lip dir not found")
        ckpt = _wav2lip_checkpoint()
        if ckpt is None:
            return _info(
                False, error="wav2lip_gan.pth checkpoint missing",
                cache_path=str(root),
            )
        return _info(True, cache_path=str(ckpt))

    def render(
        self, req: PresenterRequest, work_dir: Path,
    ) -> PresenterResult:
        info = self.info
        if not info.installed:
            raise PresenterNotAvailable(
                _PROVIDER_ID,
                info.error or "wav2lip not ready",
                info.install_hint,
            )

        work_dir.mkdir(parents=True, exist_ok=True)
        avatar = fetch_image(
            req.avatar_image_url, work_dir / "avatar.png",
        )
        audio_path, duration = synthesize_voice(
            text=req.script, voice=req.voice, rate=req.voice_rate,
            work_dir=work_dir,
        )

        root = _wav2lip_root()
        ckpt = _wav2lip_checkpoint()
        assert root is not None and ckpt is not None  # checked above

        out_mp4 = work_dir / "wav2lip_out.mp4"
        inference = root / "inference.py"
        if not inference.exists():
            raise PresenterNotAvailable(
                _PROVIDER_ID,
                f"wav2lip inference.py missing at {inference}",
                "ensure the wav2lip repo is checked out at XVE_MODELS_DIR/wav2lip",
            )

        py = shutil.which("python") or shutil.which("python3") or "python"
        cmd = [
            py, str(inference),
            "--checkpoint_path", str(ckpt),
            "--face", str(avatar),
            "--audio", str(audio_path),
            "--outfile", str(out_mp4),
        ]
        logger.info("wav2lip: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True,
            timeout=int(os.environ.get("XVE_WAV2LIP_TIMEOUT", "1800")),
        )
        if proc.returncode != 0:
            raise PresenterNotAvailable(
                _PROVIDER_ID,
                f"wav2lip inference failed (exit={proc.returncode}): "
                f"{proc.stderr[-1000:]}",
                "check wav2lip dependencies; see "
                "https://github.com/Rudrabha/Wav2Lip",
            )
        if not out_mp4.exists() or out_mp4.stat().st_size < 1000:
            raise PresenterNotAvailable(
                _PROVIDER_ID, "wav2lip produced empty output",
                "see worker logs for the inference stdout/stderr",
            )

        return PresenterResult(
            video_path=out_mp4,
            audio_path=audio_path,
            duration_sec=duration,
        )

"""Presenter provider registry — Platform Phase 1."""

from __future__ import annotations

from typing import Callable

from apps.worker.presenter.base import (
    PresenterProvider,
    PresenterProviderInfo,
)
from apps.worker.presenter.musetalk_adapter import MuseTalkPresenter
from apps.worker.presenter.sadtalker_adapter import SadTalkerPresenter
from apps.worker.presenter.wav2lip_adapter import Wav2LipPresenter


_REGISTRY: dict[str, Callable[[], PresenterProvider]] = {
    "wav2lip": Wav2LipPresenter,
    "sadtalker": SadTalkerPresenter,
    "musetalk": MuseTalkPresenter,
}


class UnknownPresenter(KeyError):
    """The api asked for a presenter id we don't have registered."""


def get_presenter_provider(provider_id: str) -> PresenterProvider:
    factory = _REGISTRY.get(provider_id)
    if factory is None:
        raise UnknownPresenter(
            f"unknown presenter provider {provider_id!r}; "
            f"known: {sorted(_REGISTRY)}"
        )
    return factory()


def list_presenter_providers() -> list[PresenterProviderInfo]:
    return [get_presenter_provider(pid).info for pid in _REGISTRY]

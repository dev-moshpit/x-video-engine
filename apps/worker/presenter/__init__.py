"""Presenter / talking-head pipeline — Platform Phase 1.

Lipsync providers (Wav2Lip / SadTalker / MuseTalk) take an avatar
image + a synthesized voice track and output a talking-head mp4. The
``news_template`` composer optionally adds a lower-third banner.

Public surface:

  PresenterRequest        request dataclass
  list_presenter_providers()
  get_presenter_provider(provider_id)
  PresenterNotAvailable
  apply_news_template(...) overlay banner + headline
"""

from apps.worker.presenter.base import (
    PresenterNotAvailable,
    PresenterProviderInfo,
    PresenterRequest,
    PresenterResult,
)
from apps.worker.presenter.news_template import apply_news_template
from apps.worker.presenter.provider import (
    UnknownPresenter,
    get_presenter_provider,
    list_presenter_providers,
)

__all__ = [
    "PresenterNotAvailable",
    "PresenterProviderInfo",
    "PresenterRequest",
    "PresenterResult",
    "UnknownPresenter",
    "apply_news_template",
    "get_presenter_provider",
    "list_presenter_providers",
]

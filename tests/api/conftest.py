"""Shared test config for SaaS API tests.

Sets env vars BEFORE the app modules are imported, since several of
those modules read env at module-load time:
  - DATABASE_URL is read by app.db.session
  - CLERK_JWT_ISSUER is read by app.auth.clerk
  - CLERK_WEBHOOK_SECRET is read by app.routers.webhooks

Also adds apps/api to sys.path so ``from app.main import app`` works.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CLERK_JWT_ISSUER", "https://example.invalid")
os.environ.setdefault(
    "CLERK_WEBHOOK_SECRET",
    "whsec_dGVzdHNlY3JldGZvcnVuaXR0ZXN0c29ubHk=",  # base64("testsecretforunittestsonly")
)

_API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

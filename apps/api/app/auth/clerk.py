"""Clerk JWT verification for the SaaS API.

Auth flow:

  Browser  →  Clerk frontend SDK  →  short-lived RS256 JWT (~1 min ttl)
  Browser  →  this api with `Authorization: Bearer <jwt>`
  This api →  verify signature against Clerk's JWKS (cached 5 min)
            →  validate iss + exp claims
            →  return ClerkPrincipal{user_id, session_id, email}

We do NOT call Clerk's REST API for verification — JWKS-based local
verification is the documented happy path and avoids a per-request
round trip. The api never holds long-lived Clerk credentials beyond
the public JWKS.

Public surface:
- ``verify_clerk_jwt(token)``  → claims dict (raises PyJWTError on failure)
- ``current_user``             → FastAPI dependency
- ``ClerkPrincipal``           → typed Pydantic model exposed in /api/me
- ``CurrentUser``              → ``Annotated[ClerkPrincipal, Depends(current_user)]``

Tests can override ``current_user`` via ``app.dependency_overrides``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient
from pydantic import BaseModel


CLERK_JWT_ISSUER = os.environ.get("CLERK_JWT_ISSUER", "").rstrip("/")
CLERK_AUDIENCE = os.environ.get("CLERK_AUDIENCE") or None


class ClerkPrincipal(BaseModel):
    """The verified Clerk user behind the current request."""

    user_id: str
    session_id: str | None = None
    email: str | None = None


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    """Cached JWKS client for the configured Clerk issuer."""
    if not CLERK_JWT_ISSUER:
        raise RuntimeError(
            "CLERK_JWT_ISSUER env var is not set; "
            "the api cannot verify tokens."
        )
    jwks_url = f"{CLERK_JWT_ISSUER}/.well-known/jwks.json"
    # PyJWKClient caches keys for 5 minutes by default.
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=300)


def verify_clerk_jwt(token: str) -> dict[str, Any]:
    """Verify a Clerk-issued JWT. Returns the claims dict on success.

    Raises ``jwt.PyJWTError`` for any signature, issuer, or expiry failure.
    """
    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=CLERK_JWT_ISSUER,
        audience=CLERK_AUDIENCE,
        options={
            "require": ["exp", "iss", "sub"],
            "verify_aud": CLERK_AUDIENCE is not None,
        },
    )


def _bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="empty bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def current_user(request: Request) -> ClerkPrincipal:
    """FastAPI dependency. Extracts + verifies the bearer token.

    On success returns a ``ClerkPrincipal`` from the JWT claims. On any
    failure raises 401 with a Bearer challenge.
    """
    token = _bearer_token(request)
    try:
        claims = verify_clerk_jwt(token)
    except jwt.PyJWTError as e:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    return ClerkPrincipal(
        user_id=claims["sub"],
        session_id=claims.get("sid"),
        email=claims.get("email"),
    )


CurrentUser = Annotated[ClerkPrincipal, Depends(current_user)]

"""Firebase ID token verification.

This is the identity layer for the self-serve dashboard - a human proving
who they are to manage their own API keys - and nothing else. It answers
"who is this person," not "is this a valid gateway request": that stays
app/core/auth.py's job, on a different header, checked by a different
dependency. The two never appear on the same route.

Verifying rather than building auth from scratch (passwords, email
verification, sessions) is deliberate: none of that exists in this
backend today, and it shouldn't have to - Firebase already solves it, and
a sibling project already uses it, so this is a second call site for a
choice already made once, not a new one.
"""

import json

import firebase_admin
from fastapi import HTTPException
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

from app.core.config import settings

_app: firebase_admin.App | None = None


def _get_app() -> firebase_admin.App:
    """Initialized lazily, once, on first use - not at import time, so a
    gateway running without FIREBASE_SERVICE_ACCOUNT_JSON configured (the
    football-data-only deployment this whole project started as) never
    pays for or fails on Firebase at all unless the dashboard is actually
    used."""
    global _app
    if _app is not None:
        return _app

    if not settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON is not set - the self-serve "
            "account dashboard needs a Firebase service account to verify "
            "sign-ins. Data endpoints (X-Gateway-Key) are unaffected."
        )

    cert = credentials.Certificate(json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON))
    _app = firebase_admin.initialize_app(cert)
    return _app


def verify_firebase_token(id_token: str) -> dict:
    """The verified claims for a Firebase ID token, or a clean 401.

    firebase_admin raises a handful of different exception types for a
    bad/expired/malformed token - callers here only ever need to know
    "this bearer token doesn't check out," not which of those it was.
    """
    try:
        return firebase_auth.verify_id_token(id_token, app=_get_app())
    except RuntimeError:
        # Not configured - a deployment problem, not a bad token. Distinct
        # status so it doesn't read as "your token is wrong" in a client.
        raise HTTPException(
            status_code=503, detail="Account sign-in is not configured on this gateway"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=401, detail=f"Invalid or expired sign-in token: {exc}"
        )

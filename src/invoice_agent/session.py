"""Encrypted session cookie for Google OAuth tokens (iron-session parity)."""

from __future__ import annotations

import os
from typing import Any

from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.requests import Request
from starlette.responses import Response

COOKIE_NAME = "invoice_agent_session"
FALLBACK_SECRET = "dev-only-invoice-agent-session-secret-change-me"


def _serializer() -> URLSafeTimedSerializer:
    password = os.environ.get("SESSION_SECRET") or FALLBACK_SECRET
    return URLSafeTimedSerializer(password, salt="invoice-agent-session")


def read_session(request: Request) -> dict[str, Any]:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return {}
    try:
        data = _serializer().loads(raw, max_age=60 * 60 * 24 * 30)
        return data if isinstance(data, dict) else {}
    except BadSignature:
        return {}


def write_session(response: Response, data: dict[str, Any]) -> None:
    secure = os.environ.get("NODE_ENV") == "production" or os.environ.get(
        "ENV", ""
    ).lower() == "production"
    token = _serializer().dumps(data)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=60 * 60 * 24 * 30,
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")

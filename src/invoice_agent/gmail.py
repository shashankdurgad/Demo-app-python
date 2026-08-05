"""Gmail read-only OAuth + candidate email fetch."""

from __future__ import annotations

import base64
import io
import os
import re
from typing import Any

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from invoice_agent.types import RawEmail

GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
USERINFO_EMAIL = "https://www.googleapis.com/auth/userinfo.email"
SCOPES = [GMAIL_READONLY, USERINFO_EMAIL]


def is_google_configured() -> bool:
    return bool(
        os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET")
    )


def get_redirect_uri() -> str:
    return os.environ.get(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/api/auth/callback",
    )


def _client_config() -> dict[str, Any]:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET. See .env.example."
        )
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [get_redirect_uri()],
        }
    }


def get_auth_url() -> str:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=get_redirect_uri(),
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    return auth_url


def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=get_redirect_uri(),
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expiry_date": int(creds.expiry.timestamp() * 1000) if creds.expiry else None,
        "token_type": creds.token_uri and "Bearer",
        "scope": " ".join(creds.scopes) if creds.scopes else None,
    }


def _credentials_from_tokens(tokens: dict[str, Any] | None) -> Credentials:
    if not tokens or not tokens.get("access_token"):
        raise RuntimeError("No Gmail access token in session.")

    expiry = None
    if tokens.get("expiry_date"):
        from datetime import datetime, timezone

        expiry = datetime.fromtimestamp(
            tokens["expiry_date"] / 1000, tz=timezone.utc
        ).replace(tzinfo=None)

    creds = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        scopes=SCOPES,
        expiry=expiry,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
    return creds


def _decode_base64url(data: str | None) -> str:
    if not data:
        return ""
    normalized = data.replace("-", "+").replace("_", "/")
    padding = "=" * (-len(normalized) % 4)
    return base64.b64decode(normalized + padding).decode("utf-8", errors="replace")


def _collect_text_parts(part: dict[str, Any] | None) -> list[str]:
    if not part:
        return []

    chunks: list[str] = []
    mime = part.get("mimeType") or ""
    body = part.get("body") or {}

    if mime in ("text/plain", "text/html") and body.get("data"):
        decoded = _decode_base64url(body.get("data"))
        if mime == "text/html":
            decoded = re.sub(r"<[^>]+>", " ", decoded)
        chunks.append(decoded)

    for child in part.get("parts") or []:
        chunks.extend(_collect_text_parts(child))

    return chunks


def _collect_pdf_attachment_ids(
    part: dict[str, Any] | None,
) -> list[dict[str, str]]:
    if not part:
        return []

    files: list[dict[str, str]] = []
    filename = part.get("filename") or ""
    is_pdf = filename.lower().endswith(".pdf") or part.get("mimeType") == "application/pdf"
    body = part.get("body") or {}
    if is_pdf and body.get("attachmentId"):
        files.append(
            {"attachmentId": body["attachmentId"], "filename": filename}
        )

    for child in part.get("parts") or []:
        files.extend(_collect_pdf_attachment_ids(child))

    return files


def _extract_pdf_text(buffer: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(buffer))
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        return "\n".join(texts)
    except Exception:
        return ""


def _get_header(headers: list[dict[str, Any]] | None, name: str) -> str:
    if not headers:
        return ""
    for header in headers:
        if (header.get("name") or "").lower() == name.lower():
            return header.get("value") or ""
    return ""


def fetch_candidate_emails(
    tokens: dict[str, Any] | None,
    *,
    max_results: int = 40,
) -> list[RawEmail]:
    auth = _credentials_from_tokens(tokens)
    gmail = build("gmail", "v1", credentials=auth, cache_discovery=False)
    query = "newer_than:12m -category:promotions -category:social"

    listing = (
        gmail.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    messages = listing.get("messages") or []
    emails: list[RawEmail] = []

    for message in messages:
        message_id = message.get("id")
        if not message_id:
            continue

        full = (
            gmail.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = full.get("payload") or {}
        headers = payload.get("headers")
        body_text = "\n".join(_collect_text_parts(payload)).strip()
        pdf_refs = _collect_pdf_attachment_ids(payload)[:2]
        attachment_texts: list[str] = []

        for pdf in pdf_refs:
            attachment = (
                gmail.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=message_id, id=pdf["attachmentId"])
                .execute()
            )
            data = attachment.get("data")
            if not data:
                continue
            normalized = data.replace("-", "+").replace("_", "/")
            padding = "=" * (-len(normalized) % 4)
            buffer = base64.b64decode(normalized + padding)
            text = _extract_pdf_text(buffer)
            if text.strip():
                attachment_texts.append(text)

        from datetime import datetime, timezone

        emails.append(
            RawEmail.model_validate(
                {
                    "id": message_id,
                    "threadId": full.get("threadId"),
                    "subject": _get_header(headers, "Subject") or "(no subject)",
                    "from": _get_header(headers, "From") or "Unknown",
                    "date": _get_header(headers, "Date")
                    or datetime.now(timezone.utc).isoformat(),
                    "snippet": full.get("snippet") or "",
                    "bodyText": body_text,
                    "attachmentTexts": attachment_texts,
                }
            )
        )

    return emails


def fetch_user_email(tokens: dict[str, Any] | None) -> str | None:
    auth = _credentials_from_tokens(tokens)
    oauth2 = build("oauth2", "v2", credentials=auth, cache_discovery=False)
    profile = oauth2.userinfo().get().execute()
    return profile.get("email")

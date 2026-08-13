"""Ledgerline FastAPI application."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from invoice_agent.agent.llm import get_llm_status, is_llm_configured
from invoice_agent.agent.triage import run_ledgerline
from invoice_agent.demo_emails import DEMO_EMAILS
from invoice_agent.gmail import (
    exchange_code_for_tokens,
    fetch_candidate_emails,
    fetch_user_email,
    get_auth_url,
    is_google_configured,
)
from invoice_agent.session import clear_session, read_session, write_session
from invoice_agent.types import AuthStatus, ScanResult

# Load .env.local then .env (local overrides)
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT / ".env.local", override=True)

TEMPLATES_DIR = _ROOT / "templates"
STATIC_DIR = _ROOT / "static"

app = FastAPI(title="Ledgerline", version="0.1.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ScanBody(BaseModel):
    mode: Literal["gmail", "demo"] | None = None
    maxResults: int | None = Field(default=None, alias="maxResults")

    model_config = {"populate_by_name": True}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "auth_error": request.query_params.get("authError"),
            "connected": request.query_params.get("connected"),
        },
    )


@app.get("/api/auth/google", response_model=None)
async def auth_google() -> Response:
    if not is_google_configured():
        return JSONResponse(
            {
                "error": (
                    "Google OAuth is not configured. Add GOOGLE_CLIENT_ID and "
                    "GOOGLE_CLIENT_SECRET to .env.local, or use Demo mode."
                )
            },
            status_code=400,
        )
    return RedirectResponse(get_auth_url(), status_code=302)


@app.get("/api/auth/callback")
async def auth_callback(request: Request) -> RedirectResponse:
    origin = str(request.base_url).rstrip("/")
    error = request.query_params.get("error")
    code = request.query_params.get("code")

    if error:
        return RedirectResponse(
            f"{origin}/?authError={quote(error)}", status_code=302
        )
    if not code:
        return RedirectResponse(
            f"{origin}/?authError={quote('Missing OAuth code')}", status_code=302
        )

    try:
        tokens = exchange_code_for_tokens(code)
        email = fetch_user_email(tokens)
        session_data = {
            "tokens": tokens,
            "email": email,
        }
        response = RedirectResponse(f"{origin}/?connected=1", status_code=302)
        write_session(response, session_data)
        return response
    except Exception as err:
        message = str(err) if err else "Failed to complete Google auth"
        return RedirectResponse(
            f"{origin}/?authError={quote(message)}", status_code=302
        )


@app.post("/api/auth/logout")
async def auth_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    clear_session(response)
    return response


@app.get("/api/auth/status")
async def auth_status(request: Request) -> JSONResponse:
    session = read_session(request)
    tokens = session.get("tokens") or {}
    llm = get_llm_status()
    status = AuthStatus.model_validate(
        {
            "connected": bool(tokens.get("access_token")),
            "email": session.get("email"),
            "hasLlm": llm["configured"],
            "llmProvider": llm["provider"],
            "llmModel": llm["model"],
            "googleConfigured": is_google_configured(),
        }
    )
    return JSONResponse(status.model_dump(by_alias=True))


@app.post("/api/scan")
async def scan(request: Request) -> JSONResponse:
    if not is_llm_configured():
        return JSONResponse(
            {
                "error": (
                    "LLM required. Add OPENAI_API_KEY or OLLAMA_BASE_URL to "
                    ".env.local and restart."
                )
            },
            status_code=400,
        )

    try:
        raw = await request.json()
    except Exception:
        raw = {}

    body = ScanBody.model_validate(raw if isinstance(raw, dict) else {})
    mode = body.mode or "gmail"

    try:
        if mode == "demo":
            run = run_ledgerline(DEMO_EMAILS, "demo")
            result = ScanResult.model_validate(
                {
                    "scanned": len(DEMO_EMAILS),
                    "invoices": run.invoices,
                    "plan": run.plan,
                    "mode": "demo",
                    "scannedAt": datetime.now(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            )
            return JSONResponse(result.model_dump(by_alias=True))

        session = read_session(request)
        tokens = session.get("tokens")
        if not tokens or not tokens.get("access_token"):
            return JSONResponse(
                {
                    "error": "Connect Gmail with read access first, or use Demo mode."
                },
                status_code=401,
            )

        max_results = body.maxResults if body.maxResults is not None else 25
        emails = fetch_candidate_emails(tokens, max_results=max_results)
        run = run_ledgerline(emails, "gmail")
        result = ScanResult.model_validate(
            {
                "scanned": len(emails),
                "invoices": run.invoices,
                "plan": run.plan,
                "mode": "gmail",
                "scannedAt": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
        return JSONResponse(result.model_dump(by_alias=True))
    except Exception as err:
        message = str(err) if err else "Failed to run invoice LLM agent"
        return JSONResponse({"error": message}, status_code=500)


def create_app() -> FastAPI:
    return app

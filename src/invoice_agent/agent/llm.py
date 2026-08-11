"""LLM client — OpenAI / Ollama chat completions for invoice triage."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Literal

from openai import OpenAI

from invoice_agent.observability import is_langfuse_configured
from invoice_agent.types import LlmExtraction

SYSTEM_PROMPT = """You are Ledgerline, an accounting invoice triage agent.
You ONLY decide from email content whether the message is a payable invoice / bill for accounting, and extract structured fields.

Rules:
- isInvoice=true only for unpaid/payable invoices, bills, or statements with an amount owed.
- isInvoice=false for receipts already paid, marketing, newsletters, personal chat, shipping notices without a bill, and unrelated mail.
- amount must be the total amount due (number only, no currency symbols).
- currency must be an ISO code like USD, GBP, EUR when known.
- dueDate must be YYYY-MM-DD when known, else null.
- Prefer explicit "amount due" / "total" / "balance due" over subtotals or tax lines.
- If uncertain whether it is a payable invoice, set isInvoice=false unless evidence is strong.

Confidence (required):
- Grade confidence from 0.0 to 1.0 on how sure you are that your full extraction is correct
  (isInvoice decision + extracted fields that you populated).
- Use a decimal in [0, 1], never a percentage (e.g. 0.82 not 82).
- Calibrate roughly as:
  - 0.90–1.00: clear payable invoice (or clear non-invoice) with explicit amount/due date or unambiguous rejection cues
  - 0.70–0.89: likely correct, but a field is missing, ambiguous, or inferred
  - 0.40–0.69: mixed signals (receipt vs invoice, partial bill, weak vendor/amount evidence)
  - 0.00–0.39: guessing; content is sparse, contradictory, or mostly unrelated
- Lower confidence when amount/due date/vendor are guessed, when paid receipts look like invoices, or when multiple totals conflict.
- Higher confidence when the email explicitly says invoice/bill/amount due and fields are stated plainly.
- Do not default every answer to 0.9+; spread scores when evidence strength differs.

Return JSON only. No markdown."""


@dataclass(frozen=True)
class LlmEndpoint:
    provider: Literal["openai", "ollama"]
    base_url: str
    model: str
    api_key: str


def is_llm_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("OLLAMA_BASE_URL"))


def require_llm_configured() -> None:
    if is_llm_configured():
        return
    raise RuntimeError(
        "LLM is required. Set OPENAI_API_KEY (or OLLAMA_BASE_URL for a local model) "
        "in .env.local, then restart the app."
    )


def _openai_compatible_base_url(raw: str) -> str:
    """Normalize chat-completions URLs to an OpenAI client base_url (.../v1)."""
    base = raw.rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    return base


def get_llm_endpoint() -> LlmEndpoint:
    require_llm_configured()

    if os.environ.get("OPENAI_API_KEY"):
        raw = os.environ.get(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        )
        return LlmEndpoint(
            provider="openai",
            base_url=_openai_compatible_base_url(raw),
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=os.environ["OPENAI_API_KEY"],
        )

    ollama_base = (os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip(
        "/"
    )
    return LlmEndpoint(
        provider="ollama",
        base_url=f"{ollama_base}/v1",
        model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
        api_key="ollama",
    )


def get_llm_status() -> dict[str, Any]:
    if not is_llm_configured():
        return {"configured": False, "provider": None, "model": None}

    endpoint = get_llm_endpoint()
    return {
        "configured": True,
        "provider": endpoint.provider,
        "model": endpoint.model,
    }


def _get_openai_client(endpoint: LlmEndpoint) -> OpenAI:
    """Build an OpenAI client; use Langfuse drop-in when tracing is configured."""
    if is_langfuse_configured():
        from invoice_agent.observability import init_langfuse
        from langfuse.openai import OpenAI as LangfuseOpenAI

        init_langfuse()
        return LangfuseOpenAI(
            api_key=endpoint.api_key,
            base_url=endpoint.base_url,
            timeout=120.0,
        )

    return OpenAI(
        api_key=endpoint.api_key,
        base_url=endpoint.base_url,
        timeout=120.0,
    )


def _extract_json_object(content: str) -> Any:
    trimmed = content.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        return json.loads(trimmed)

    match = re.search(r"\{[\s\S]*\}", trimmed)
    if not match:
        raise RuntimeError("LLM did not return JSON.")
    return json.loads(match.group(0))


def analyze_email_with_llm(
    *,
    subject: str,
    from_: str,
    date: str,
    text: str,
) -> LlmExtraction:
    endpoint = get_llm_endpoint()
    temperature = 0

    user_prompt = f"""Analyze this email for accounting invoice triage.

Return ONLY valid JSON with exactly these keys:
{{
  "isInvoice": boolean,
  "vendor": string|null,
  "amount": number|null,
  "currency": string|null,
  "dueDate": "YYYY-MM-DD"|null,
  "invoiceNumber": string|null,
  "summary": string|null,
  "confidence": number
}}

For "confidence": score 0.0–1.0 for how confident you are in this triage + extraction
(not how likely the email is an invoice by itself). Example: a clear newsletter can be
isInvoice=false with confidence 0.95; a blurry maybe-invoice might be isInvoice=false
with confidence 0.45.

Email date: {date}
Email subject: {subject}
From: {from_}
Body / attachments text:
{text[:10000]}"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    client = _get_openai_client(endpoint)
    create_kwargs: dict[str, Any] = {
        "model": endpoint.model,
        "temperature": temperature,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    if is_langfuse_configured():
        create_kwargs["name"] = "classify-invoice"
        create_kwargs["metadata"] = {
            "provider": endpoint.provider,
            "langfuse_tags": ["invoice-triage"],
        }

    try:
        response = client.chat.completions.create(**create_kwargs)
    except Exception as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc

    raw_content = None
    if response.choices:
        raw_content = response.choices[0].message.content

    if not raw_content:
        raise RuntimeError("LLM returned an empty response.")

    parsed = _extract_json_object(raw_content)
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM returned invalid invoice JSON: not an object")

    # Some models return confidence as 0–100; normalize to 0–1 for the schema.
    confidence = parsed.get("confidence")
    if isinstance(confidence, (int, float)) and confidence > 1:
        parsed["confidence"] = min(confidence / 100, 1)

    try:
        return LlmExtraction.model_validate(parsed)
    except Exception as exc:
        raise RuntimeError(f"LLM returned invalid invoice JSON: {exc}") from exc

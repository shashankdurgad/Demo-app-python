"""LLM client — OpenAI / Ollama chat completions for invoice triage."""

from __future__ import annotations

import atexit
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from overmind import (
    SpanType,
    entry_point,
    force_flush_traces,
    init,
    observe,
    set_agent_name,
    set_tag,
    workflow,
)

from invoice_agent.types import LlmExtraction

if os.environ.get("OVERMIND_API_KEY"):
    init(service_name="ledgerline-invoice-agent")
    set_agent_name("Ledgerline Invoice Triage Agent")
    atexit.register(force_flush_traces)

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
    url: str
    model: str
    headers: dict[str, str]


def is_llm_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("OLLAMA_BASE_URL"))


def require_llm_configured() -> None:
    if is_llm_configured():
        return
    raise RuntimeError(
        "LLM is required. Set OPENAI_API_KEY (or OLLAMA_BASE_URL for a local model) "
        "in .env.local, then restart the app."
    )


def get_llm_endpoint() -> LlmEndpoint:
    require_llm_configured()

    if os.environ.get("OPENAI_API_KEY"):
        return LlmEndpoint(
            provider="openai",
            url=os.environ.get(
                "OPENAI_BASE_URL",
                "https://api.openai.com/v1/chat/completions",
            ),
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            },
        )

    base = (os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    return LlmEndpoint(
        provider="ollama",
        url=f"{base}/v1/chat/completions",
        model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
        headers={"Content-Type": "application/json"},
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


def _extract_json_object(content: str) -> Any:
    trimmed = content.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        return json.loads(trimmed)

    match = re.search(r"\{[\s\S]*\}", trimmed)
    if not match:
        raise RuntimeError("LLM did not return JSON.")
    return json.loads(match.group(0))


def _parts_messages(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {"role": m["role"], "parts": [{"type": "text", "content": m["content"]}]}
        for m in messages
    ]


@observe(type=SpanType.LLM)
def _post_chat_completions(
    *,
    endpoint: LlmEndpoint,
    messages: list[dict[str, str]],
    temperature: float,
) -> httpx.Response:
    set_tag("gen_ai.input.messages", json.dumps(_parts_messages(messages)))
    set_tag("gen_ai.request.model", endpoint.model)
    set_tag("gen_ai.request.temperature", temperature)
    set_tag("gen_ai.request.response_format", "json_object")
    set_tag("gen_ai.request.max_input_chars", 10000)
    set_tag("gen_ai.system", endpoint.provider)

    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            endpoint.url,
            headers=endpoint.headers,
            json={
                "model": endpoint.model,
                "temperature": temperature,
                "messages": messages,
                "response_format": {"type": "json_object"},
            },
        )

    if response.status_code < 400:
        data = response.json()
        choices = data.get("choices") or []
        raw_content = None
        if choices:
            raw_content = (choices[0].get("message") or {}).get("content")
        if raw_content:
            set_tag(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": raw_content}],
                        }
                    ]
                ),
            )
        usage = data.get("usage") or {}
        if usage.get("prompt_tokens") is not None:
            set_tag("gen_ai.usage.prompt_tokens", usage["prompt_tokens"])
        if usage.get("completion_tokens") is not None:
            set_tag("gen_ai.usage.completion_tokens", usage["completion_tokens"])
        if usage.get("total_tokens") is not None:
            set_tag("gen_ai.usage.total_tokens", usage["total_tokens"])

    return response


@workflow("per_email_extraction")
def _per_email_extraction(
    *,
    endpoint: LlmEndpoint,
    subject: str,
    from_: str,
    date: str,
    text: str,
    temperature: float,
) -> httpx.Response:
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
    return _post_chat_completions(
        endpoint=endpoint, messages=messages, temperature=temperature
    )


@entry_point("Ledgerline Invoice Triage Agent")
def analyze_email_with_llm(
    *,
    subject: str,
    from_: str,
    date: str,
    text: str,
) -> LlmExtraction:
    endpoint = get_llm_endpoint()
    temperature = 0

    response = _per_email_extraction(
        endpoint=endpoint,
        subject=subject,
        from_=from_,
        date=date,
        text=text,
        temperature=temperature,
    )

    if response.status_code >= 400:
        error_text = response.text[:240] if response.text else response.reason_phrase
        raise RuntimeError(
            f"LLM request failed ({response.status_code}): {error_text}"
        )

    data = response.json()
    choices = data.get("choices") or []
    raw_content = None
    if choices:
        raw_content = (choices[0].get("message") or {}).get("content")

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

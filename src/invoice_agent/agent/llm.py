"""LLM client — OpenAI / Ollama chat completions for invoice triage."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from typing import Any, Literal

import overmind
from langsmith import traceable
from openai import OpenAI

from invoice_agent.agent.braintrust_tracing import braintrust_enabled, configure_braintrust
from invoice_agent.agent.galileo_tracing import configure_galileo
from invoice_agent.agent.langfuse_tracing import configure_langfuse, langfuse_enabled
from invoice_agent.agent.overmind_tracing import configure_overmind
from invoice_agent.agent.tracing import configure_tracing, tracing_enabled
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
            model=os.environ.get("OPENAI_MODEL", "gpt-5.2"),
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


def get_adjudicator_model() -> str:
    return os.environ.get("ADJUDICATOR_MODEL", "gpt-5.6")


def get_adjudicator_endpoint() -> LlmEndpoint:
    """Same client construction as triage, with the adjudicator's own model pin."""
    base = get_llm_endpoint()
    return replace(base, model=get_adjudicator_model())


def get_adjudicator_llm_status() -> dict[str, Any]:
    if not is_llm_configured():
        return {"configured": False, "provider": None, "model": None}
    endpoint = get_adjudicator_endpoint()
    return {
        "configured": True,
        "provider": endpoint.provider,
        "model": endpoint.model,
    }


@dataclass(frozen=True)
class ChatToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ChatCompletionMessage:
    content: str | None
    tool_calls: list[ChatToolCall]


def _get_openai_client(endpoint: LlmEndpoint) -> OpenAI:
    configure_tracing()
    # Must run before the client is constructed so the OpenAI SDK is patched.
    configure_overmind()
    configure_galileo()
    configure_langfuse()
    configure_braintrust()
    client = OpenAI(
        api_key=endpoint.api_key,
        base_url=endpoint.base_url,
        timeout=120.0,
    )
    if tracing_enabled():
        from langsmith.wrappers import wrap_openai

        return wrap_openai(
            client,
            tracing_extra={
                "metadata": {
                    "provider": endpoint.provider,
                    "model": endpoint.model,
                }
            },
        )
    return client


def _extract_json_object(content: str) -> Any:
    trimmed = content.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        return json.loads(trimmed)

    match = re.search(r"\{[\s\S]*\}", trimmed)
    if not match:
        raise RuntimeError("LLM did not return JSON.")
    return json.loads(match.group(0))


def _supports_temperature(model: str) -> bool:
    """GPT-5 reasoning models reject custom temperature; chat variants allow it."""
    name = model.split("/")[-1].lower()
    if name.startswith("gpt-5") and "chat" not in name:
        return False
    return True


@overmind.function(name="chat_json")
@traceable(name="chat_json", tags=["llm"])
def chat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    span_name: str,
    temperature: float = 0,
) -> dict:
    """Run one JSON-mode chat completion and return the parsed object."""
    endpoint = get_llm_endpoint()
    client = _get_openai_client(endpoint)

    create_kwargs: dict[str, Any] = {
        "model": endpoint.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    if langfuse_enabled():
        create_kwargs["name"] = span_name
        create_kwargs["metadata"] = {"provider": endpoint.provider}
    if braintrust_enabled():
        # Braintrust consumes span_info to name the span; it never reaches OpenAI.
        create_kwargs["span_info"] = {"name": span_name}
    if _supports_temperature(endpoint.model):
        create_kwargs["temperature"] = temperature

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
        raise RuntimeError("LLM returned invalid JSON: not an object")
    return parsed


@overmind.function(name="create_chat_completion")
@traceable(name="create_chat_completion", tags=["llm"])
def create_chat_completion(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
    temperature: float = 0,
    tool_choice: str | dict[str, Any] | None = None,
) -> ChatCompletionMessage:
    """One chat.completions round, optionally with OpenAI tools."""
    endpoint = (
        get_adjudicator_endpoint()
        if model is None
        else replace(get_llm_endpoint(), model=model)
    )
    client = _get_openai_client(endpoint)

    create_kwargs: dict[str, Any] = {
        "model": endpoint.model,
        "messages": messages,
    }
    if tools:
        create_kwargs["tools"] = tools
        if tool_choice is not None:
            create_kwargs["tool_choice"] = tool_choice
        # gpt-5.x reasoning models reject tools on chat.completions unless
        # reasoning_effort is none (otherwise they require the Responses API).
        if not _supports_temperature(endpoint.model):
            create_kwargs["reasoning_effort"] = "none"
    if _supports_temperature(endpoint.model):
        create_kwargs["temperature"] = temperature
    if langfuse_enabled():
        create_kwargs["name"] = "adjudicate-llm"
        create_kwargs["metadata"] = {"provider": endpoint.provider}
    if braintrust_enabled():
        create_kwargs["span_info"] = {"name": "adjudicate-llm"}

    try:
        response = client.chat.completions.create(**create_kwargs)
    except Exception as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc

    if not response.choices:
        raise RuntimeError("LLM returned no choices.")
    message = response.choices[0].message
    tool_calls: list[ChatToolCall] = []
    for item in getattr(message, "tool_calls", None) or []:
        function = getattr(item, "function", None)
        if function is None:
            continue
        tool_calls.append(
            ChatToolCall(
                id=str(item.id),
                name=str(function.name),
                arguments=str(function.arguments or "{}"),
            )
        )
    return ChatCompletionMessage(content=message.content, tool_calls=tool_calls)


@overmind.function(name="analyze_email_with_llm")
@traceable(name="analyze_email_with_llm", tags=["triage"])
def analyze_email_with_llm(
    *,
    subject: str,
    from_: str,
    date: str,
    text: str,
) -> LlmExtraction:
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

    parsed = chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        span_name="classify-invoice",
    )

    # Some models return confidence as 0–100; normalize to 0–1 for the schema.
    confidence = parsed.get("confidence")
    if isinstance(confidence, (int, float)) and confidence > 1:
        parsed["confidence"] = min(confidence / 100, 1)

    try:
        return LlmExtraction.model_validate(parsed)
    except Exception as exc:
        raise RuntimeError(f"LLM returned invalid invoice JSON: {exc}") from exc

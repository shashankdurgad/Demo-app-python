"""Shared Pydantic models for Ledgerline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RawEmail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    thread_id: str | None = Field(default=None, alias="threadId")
    subject: str
    from_: str = Field(alias="from")
    date: str
    snippet: str
    body_text: str = Field(alias="bodyText")
    attachment_texts: list[str] = Field(default_factory=list, alias="attachmentTexts")


class MoneyAmount(BaseModel):
    value: float
    currency: str
    raw: str


class InvoiceRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    email_id: str = Field(alias="emailId")
    thread_id: str | None = Field(default=None, alias="threadId")
    subject: str
    from_: str = Field(alias="from")
    vendor: str
    received_at: str = Field(alias="receivedAt")
    amount: MoneyAmount | None
    due_date: str | None = Field(alias="dueDate")
    invoice_number: str | None = Field(alias="invoiceNumber")
    confidence: float
    summary: str
    gmail_url: str = Field(alias="gmailUrl")
    source: Literal["gmail", "demo"]


class ScanResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scanned: int
    invoices: list[InvoiceRecord]
    mode: Literal["gmail", "demo"]
    scanned_at: str = Field(alias="scannedAt")


class AuthStatus(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    connected: bool
    email: str | None
    has_llm: bool = Field(alias="hasLlm")
    llm_provider: Literal["openai", "ollama"] | None = Field(alias="llmProvider")
    llm_model: str | None = Field(alias="llmModel")
    google_configured: bool = Field(alias="googleConfigured")


class LlmExtraction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    is_invoice: bool = Field(alias="isInvoice")
    vendor: str | None = None
    amount: float | None = None
    currency: str | None = None
    due_date: str | None = Field(default=None, alias="dueDate")
    invoice_number: str | None = Field(default=None, alias="invoiceNumber")
    summary: str | None = None
    confidence: float = Field(ge=0, le=1)

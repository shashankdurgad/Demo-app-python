"""Themes stress corpus — ported from themes-corpus.ts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from invoice_agent.agent.llm import analyze_email_with_llm
from invoice_agent.generate_demo_emails import generate_demo_emails
from invoice_agent.types import InvoiceRecord, MoneyAmount, RawEmail

ThemeFailureMode = Literal[
    "ok",
    "missing_amount",
    "missing_due_date",
    "currency_confusion",
    "false_positive",
    "false_negative",
    "post_llm_error",
    "llm_call_error",
    "oddball",
]


class ThemesCorpusItem(BaseModel):
    email: RawEmail
    mode: ThemeFailureMode


class ThemesAnalyzeResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email_id: str = Field(alias="emailId")
    mode: ThemeFailureMode
    ok: bool
    is_invoice: bool = Field(alias="isInvoice")
    error: str | None
    record: InvoiceRecord | None


def _family(index: int) -> str:
    bucket = index % 20
    if bucket < 9:
        return "invoice"
    if bucket < 13:
        return "receipt"
    if bucket < 16:
        return "personal"
    if bucket < 18:
        return "newsletter"
    return "shipping"


def _pick_indices(pool: list[int], count: int, salt: int) -> list[int]:
    if count <= 0 or not pool:
        return []
    scored = [
        {
            "idx": idx,
            "rank": ((idx * 2654435761 + salt * 40503) & 0xFFFFFFFF) % 1_000_003,
        }
        for idx in pool
    ]
    scored.sort(key=lambda s: (s["rank"], s["idx"]))
    return [s["idx"] for s in scored[: min(count, len(scored))]]


ODDBALLS: list[RawEmail] = [
    RawEmail.model_validate(
        {
            "id": "themes-oddball-dispute",
            "threadId": "themes-oddball-dispute",
            "subject": "Formal dispute — INV-4419 overcharged labour hours",
            "from": "Legal <disputes@ledgerline-ap.example>",
            "date": "Mon, 06 Jul 2026 09:00:00 +0000",
            "snippet": "We dispute line 3; please hold payment",
            "bodyText": """
We formally dispute invoice INV-4419 from Brightline Telecom.

Line 3 (after-hours labour) was never authorised. Please place the invoice
on hold and confirm a credit memo. This is a dispute letter, not a payment
instruction.
""".strip(),
            "attachmentTexts": [],
        }
    ),
    RawEmail.model_validate(
        {
            "id": "themes-oddball-partial-refund",
            "threadId": "themes-oddball-partial-refund",
            "subject": "Partial refund processed — RMA-882",
            "from": "Returns <returns@novadesign.example>",
            "date": "Tue, 07 Jul 2026 11:22:00 +0000",
            "snippet": "€120.00 credited to original card",
            "bodyText": """
Partial refund note for RMA-882.

Original invoice: ND-2104
Refunded: €120.00 of €480.00 (damaged goods)
Method: original card ending 4412

No amount is due. This confirms a credit already issued.
""".strip(),
            "attachmentTexts": [],
        }
    ),
    RawEmail.model_validate(
        {
            "id": "themes-oddball-dunning-de",
            "threadId": "themes-oddball-dunning-de",
            "subject": "Zweite Mahnung — offene Rechnung RG-7781",
            "from": "Buchhaltung <mahnung@cloudhost.example>",
            "date": "Wed, 08 Jul 2026 08:15:00 +0000",
            "snippet": "Bitte überweisen Sie 890,00 EUR bis 16.07.2026",
            "bodyText": """
Sehr geehrte Damen und Herren,

dies ist die zweite Mahnung zu Rechnung RG-7781.

Offener Betrag: 890,00 EUR
Fällig spätestens: 16.07.2026
Verwendungszweck: RG-7781

Bitte begleichen Sie den Betrag unverzüglich, um weitere Schritte zu vermeiden.
""".strip(),
            "attachmentTexts": [],
        }
    ),
    RawEmail.model_validate(
        {
            "id": "themes-oddball-scan-only",
            "threadId": "themes-oddball-scan-only",
            "subject": "Scanned cafe receipt (image OCR dump)",
            "from": "Expenses <expenses@ledgerline.example>",
            "date": "Thu, 09 Jul 2026 17:40:00 +0000",
            "snippet": "OCR from phone photo — barely readable",
            "bodyText": """
Attached OCR dump from a phone photo of a paper receipt.
Body has no structured fields; only the attachment text may contain totals.
""".strip(),
            "attachmentTexts": [
                """
=== OCR (low confidence) ===
CAFE LUMEN
t0tal ?? 14.5O
dte: 0?/1?/26
card ****9912
PAID
===========================
""".strip(),
            ],
        }
    ),
]


def _pathologize(email: RawEmail, mode: ThemeFailureMode, index: int) -> RawEmail:
    if mode in ("ok", "llm_call_error", "post_llm_error"):
        return email

    if mode == "missing_amount":
        import re

        vendor_name = email.from_.split("<")[0].strip() or "Vendor"
        subject_tail = re.sub(r"^Invoice\s+", "", email.subject, flags=re.IGNORECASE)
        return RawEmail.model_validate(
            {
                "id": email.id,
                "threadId": email.thread_id,
                "subject": f"Invoice details for {subject_tail}",
                "from": email.from_,
                "date": email.date,
                "snippet": "Please review the attached schedule — totals omitted from body",
                "bodyText": f"""
{vendor_name}

Payable invoice — field schedule attached.

Vendor confirmed. Payment terms: due on receipt of funds clearance.
Amount due: [see attachment page 2 — not included in this text extract]
Due date: July {(index % 20) + 10}, 2026
Invoice ref: PATH-AMT-{1000 + index}

The body intentionally omits a numeric total.
""".strip(),
                "attachmentTexts": [
                    "Schedule page 1 only.\nNo grand total printed on the extracted page.\nSubline items redacted.\n",
                ],
            }
        )

    if mode == "missing_due_date":
        return RawEmail.model_validate(
            {
                "id": email.id,
                "threadId": email.thread_id,
                "subject": email.subject,
                "from": email.from_,
                "date": email.date,
                "snippet": "Amount due listed; due date written as net-30 only",
                "bodyText": f"""
Payable invoice

Amount due: ${(40 + (index % 900) + (index % 10) / 10):.2f} USD
Payment terms: net 30 from receipt (no calendar due date stated)
Invoice number: PATH-DUE-{1000 + index}

Please remit per standard net-30 terms.
""".strip(),
                "attachmentTexts": [],
            }
        )

    if mode == "currency_confusion":
        whole = 1000 + (index % 800)
        frac = f"{(index * 7) % 100:02d}"
        return RawEmail.model_validate(
            {
                "id": email.id,
                "threadId": email.thread_id,
                "subject": email.subject,
                "from": email.from_,
                "date": email.date,
                "snippet": f"Betrag {whole},{frac} EUR (also shows $ glyph in footer)",
                "bodyText": f"""
RECHNUNG / INVOICE PATH-CUR-{1000 + index}

Rechnungsbetrag: {whole},{frac} EUR
(Anzeige in Portal manchmal als ${whole}.{frac})

Fällig: {(index % 20) + 10}.07.2026

Bitte überweisen Sie den EUR-Betrag. Ignore any $ decorative glyph in the footer.
Footer: prices may display with a $ icon in our US template — currency is EUR.
""".strip(),
                "attachmentTexts": [],
            }
        )

    if mode == "false_positive":
        return RawEmail.model_validate(
            {
                "id": email.id,
                "threadId": email.thread_id,
                "subject": f"Action required: account review #{index + 1}",
                "from": email.from_,
                "date": email.date,
                "snippet": "Exclusive offer — upgrade before Friday",
                "bodyText": """
Weekly Partner Digest

Unlock Pro analytics this week.
Many customers ask about "invoice-like" upgrade confirmations.

Promo code SAVE20 — not a bill.
Estimated list price if you upgraded: $49/mo (marketing only).

Unsubscribe | This is a newsletter, not an accounts-payable invoice.
""".strip(),
                "attachmentTexts": [
                    "Upgrade quote (not payable):\nVendor: Growth Lab\nQuoted: 49.00 USD\n",
                ],
            }
        )

    if mode == "false_negative":
        return RawEmail.model_validate(
            {
                "id": email.id,
                "threadId": email.thread_id,
                "subject": f"Informational copy of statement ST-{1000 + index}",
                "from": email.from_,
                "date": email.date,
                "snippet": "FYI statement attached — accounting copy",
                "bodyText": f"""
INFORMATIONAL — for your records

Some portals label this "do not pay online" because payment is via ACH only.
This IS a payable invoice / bill for accounting.

Vendor: Orbit Analytics
Amount due: ${(120 + (index % 400)):.2f} USD
Due date: July {(index % 15) + 12}, 2026
Invoice: ST-{1000 + index}

Remit by ACH using the amount and due date above.
""".strip(),
                "attachmentTexts": [],
            }
        )

    return email


def generate_themes_corpus(
    count: int = 1200,
) -> tuple[list[ThemesCorpusItem], dict[str, ThemeFailureMode]]:
    if count < 500:
        raise ValueError("themes corpus count must be >= 500 (platform learns on first 500)")

    base = generate_demo_emails(count)
    modes: list[ThemeFailureMode] = ["ok"] * count

    invoice_idx: list[int] = []
    bait_idx: list[int] = []
    for i in range(count - 4):
        family = _family(i)
        if family == "invoice":
            invoice_idx.append(i)
        if family in ("receipt", "newsletter"):
            bait_idx.append(i)

    def assign(pool: list[int], mode: ThemeFailureMode, n: int, salt: int) -> None:
        for idx in _pick_indices(pool, n, salt):
            modes[idx] = mode

    assign(invoice_idx, "missing_amount", 60, 11)
    assign([i for i in invoice_idx if modes[i] == "ok"], "missing_due_date", 60, 22)
    assign([i for i in invoice_idx if modes[i] == "ok"], "currency_confusion", 60, 33)
    assign([i for i in invoice_idx if modes[i] == "ok"], "false_negative", 40, 44)
    assign([i for i in invoice_idx if modes[i] == "ok"], "post_llm_error", 30, 55)
    assign([i for i in invoice_idx if modes[i] == "ok"], "llm_call_error", 20, 66)
    assign([i for i in bait_idx if modes[i] == "ok"], "false_positive", 60, 77)

    for k in range(4):
        idx = count - 4 + k
        modes[idx] = "oddball"
        odd = ODDBALLS[k]
        base[idx] = RawEmail.model_validate(
            {
                "id": f"gen-{idx + 1}",
                "threadId": f"gen-thread-{idx + 1}",
                "subject": odd.subject,
                "from": odd.from_,
                "date": odd.date,
                "snippet": odd.snippet,
                "bodyText": odd.body_text,
                "attachmentTexts": odd.attachment_texts,
            }
        )

    items: list[ThemesCorpusItem] = []
    for index, email in enumerate(base):
        mode = modes[index]
        shaped = email if mode == "oddball" else _pathologize(email, mode, index)
        items.append(ThemesCorpusItem(email=shaped, mode=mode))

    mode_by_email_id = {item.email.id: item.mode for item in items}
    return items, mode_by_email_id


def _received_at(date_str: str) -> str:
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def analyze_themes_email(item: ThemesCorpusItem) -> ThemesAnalyzeResult:
    try:
        if item.mode == "llm_call_error":
            raise RuntimeError(
                "Simulated provider failure before output (themes corpus llm_call_error)"
            )

        combined_text = "\n".join(
            filter(
                None,
                [
                    item.email.subject,
                    item.email.snippet,
                    item.email.body_text,
                    *item.email.attachment_texts,
                ],
            )
        )

        llm = analyze_email_with_llm(
            subject=item.email.subject,
            from_=item.email.from_,
            date=item.email.date,
            text=combined_text,
        )

        is_invoice = llm.is_invoice
        amount = llm.amount
        currency = llm.currency
        due_date = llm.due_date
        vendor = llm.vendor

        if item.mode == "missing_amount":
            amount = None
        if item.mode == "missing_due_date":
            due_date = None
        if item.mode == "currency_confusion":
            currency = "USD"
        if item.mode == "false_positive":
            is_invoice = True
            vendor = vendor or "Growth Lab"
            amount = amount if amount is not None else 49
            currency = currency or "USD"
        if item.mode == "false_negative":
            is_invoice = False

        if item.mode == "post_llm_error":
            raise RuntimeError(
                "Due-date normalisation failed (themes corpus post_llm_error)"
            )

        record: InvoiceRecord | None = None
        if is_invoice:
            cur = currency or "USD"
            money = (
                MoneyAmount(value=amount, currency=cur, raw=f"{cur} {amount}")
                if amount is not None
                else None
            )
            record = InvoiceRecord.model_validate(
                {
                    "id": f"demo-{item.email.id}",
                    "emailId": item.email.id,
                    "threadId": item.email.thread_id or None,
                    "subject": item.email.subject,
                    "from": item.email.from_,
                    "vendor": vendor or "Unknown vendor",
                    "receivedAt": _received_at(item.email.date),
                    "amount": money,
                    "dueDate": due_date,
                    "invoiceNumber": llm.invoice_number,
                    "confidence": round(llm.confidence, 2),
                    "summary": llm.summary or item.email.snippet or item.email.subject,
                    "gmailUrl": "#",
                    "source": "demo",
                }
            )

        return ThemesAnalyzeResult.model_validate(
            {
                "emailId": item.email.id,
                "mode": item.mode,
                "ok": True,
                "isInvoice": bool(record),
                "error": None,
                "record": record,
            }
        )
    except Exception as err:
        message = str(err)
        return ThemesAnalyzeResult.model_validate(
            {
                "emailId": item.email.id,
                "mode": item.mode,
                "ok": False,
                "isInvoice": False,
                "error": message,
                "record": None,
            }
        )


def tally_modes(items: list[ThemesCorpusItem]) -> dict[ThemeFailureMode, int]:
    counts: dict[ThemeFailureMode, int] = {}
    for item in items:
        counts[item.mode] = counts.get(item.mode, 0) + 1
    return counts

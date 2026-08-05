"""Deterministic generated demo email corpus — ported from generate-demo-emails.ts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, TypeVar

from invoice_agent.types import RawEmail

Currency = Literal["USD", "GBP", "EUR"]
T = TypeVar("T")

WEEKDAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

INVOICE_VENDORS = (
    {"name": "Northwind Supplies", "from": "billing@northwind.example", "domain": "northwind"},
    {"name": "Amazon Web Services", "from": "no-reply@amazon.com", "domain": "aws"},
    {"name": "Cloudhost Ltd", "from": "accounts@cloudhost.example", "domain": "cloudhost"},
    {"name": "Stripe, Inc.", "from": "invoices@stripe.com", "domain": "stripe"},
    {"name": "Spotify for Business", "from": "billing@spotify.com", "domain": "spotify"},
    {"name": "Harcourt & Co", "from": "accounts@harcourt-legal.example", "domain": "harcourt"},
    {"name": "Slack Technologies", "from": "billing@slack.com", "domain": "slack"},
    {"name": "Maya Chen Studio", "from": "maya@studio.example", "domain": "maya"},
    {"name": "GitHub, Inc.", "from": "billing@github.com", "domain": "github"},
    {"name": "Apex Advisory", "from": "billing@apex-advisory.example", "domain": "apex"},
    {"name": "Acme SaaS", "from": "billing@acme-saas.example", "domain": "acme"},
    {"name": "Brightline Telecom", "from": "invoices@brightline.example", "domain": "brightline"},
    {"name": "ParcelOps Logistics", "from": "accounts@parcelops.example", "domain": "parcelops"},
    {"name": "Nova Design Co", "from": "finance@novadesign.example", "domain": "nova"},
    {"name": "Orbit Analytics", "from": "billing@orbit-analytics.example", "domain": "orbit"},
)

RECEIPT_VENDORS = (
    {"name": "Figma", "from": "receipts@figma.com"},
    {"name": "Adobe", "from": "noreply@adobe.com"},
    {"name": "Uber", "from": "receipts@uber.com"},
    {"name": "Northern Power", "from": "receipts@northernpower.example"},
    {"name": "Notion", "from": "receipts@notion.so"},
    {"name": "Dropbox", "from": "noreply@dropbox.com"},
    {"name": "Zoom", "from": "receipts@zoom.us"},
)

PEOPLE = (
    "alex@company.example",
    "sam@friends.example",
    "jordan@company.example",
    "chris@personal.example",
    "taylor@company.example",
    "riley@friends.example",
)

NEWSLETTERS = (
    "Product Weekly <digest@newsletter.example>",
    "Growth Tips <hello@growthlab.example>",
    "Dev Digest <news@devdigest.example>",
    "Office Perks <offers@officeperks.example>",
)

SHIPPERS = (
    "ShopFast Shipping <ship@shopfast.example>",
    "QuickCart Fulfillment <ship@quickcart.example>",
    "ParcelTrack <updates@parceltrack.example>",
)


def _pick(items: tuple[T, ...] | list[T], index: int) -> T:
    return items[index % len(items)]


def format_rfc_date(day_offset: int) -> str:
    date = datetime(
        2026,
        7,
        1 + (day_offset % 20),
        8 + (day_offset % 10),
        (day_offset * 7) % 60,
        tzinfo=timezone.utc,
    )
    # JS getUTCDay(): Sun=0 … Sat=6
    js_day = (date.weekday() + 1) % 7
    weekday = WEEKDAYS[js_day]
    day = f"{date.day:02d}"
    month = MONTHS[date.month - 1]
    year = date.year
    hh = f"{date.hour:02d}"
    mm = f"{date.minute:02d}"
    return f"{weekday}, {day} {month} {year} {hh}:{mm}:00 +0000"


def format_due_date(day_offset: int, currency: Currency) -> str:
    from datetime import timedelta

    # Match JS Date.UTC(2026, 6, 15 + (dayOffset % 25)) overflow into August+.
    # GBP/USD text formats hardcode "July" like the TypeScript source.
    date = datetime(2026, 7, 15, tzinfo=timezone.utc) + timedelta(
        days=(day_offset % 25)
    )
    day = date.day
    month = date.month
    year = date.year
    if currency == "EUR":
        return f"{day:02d}/{month:02d}/{year}"
    if currency == "GBP":
        return f"{day} July {year}"
    return f"July {day}, {year}"


def money(value: float, currency: Currency) -> str:
    rounded = round(value * 100) / 100
    if currency == "GBP":
        return f"£{rounded:.2f}"
    if currency == "EUR":
        return f"€{rounded:.2f}"
    return f"${rounded:.2f}"


def make_invoice(index: int) -> RawEmail:
    vendor = _pick(INVOICE_VENDORS, index)
    currency = _pick(("USD", "GBP", "EUR"), index)
    amount = 40 + ((index * 37) % 4900) + (index % 100) / 100
    invoice_number = f"{vendor['domain'].upper()[:3]}-{1000 + index}"
    due = format_due_date(index, currency)
    with_attachment = index % 5 == 0

    body_text = f"""
{vendor['name']}

INVOICE {invoice_number}
Bill To: Ledgerline Demo

Amount due: {money(amount, currency)} {"USD" if currency == "USD" else currency}
Due date: {due}

Please remit payment by the due date to avoid service interruption.
""".strip()

    return RawEmail.model_validate(
        {
            "id": f"gen-{index + 1}",
            "threadId": f"gen-thread-{index + 1}",
            "subject": f"Invoice {invoice_number} from {vendor['name']}",
            "from": f"{vendor['name']} <{vendor['from']}>",
            "date": format_rfc_date(index),
            "snippet": f"Invoice {invoice_number} — {money(amount, currency)} due {due}",
            "bodyText": (
                f"Hello,\n\nPlease see the attached invoice {invoice_number}.\n\n"
                f"Regards,\n{vendor['name']} Billing\n"
                if with_attachment
                else body_text
            ),
            "attachmentTexts": (
                [
                    f"{vendor['name']}\nTAX INVOICE {invoice_number}\n"
                    f"Total amount due: {money(amount, currency)} {currency}\n"
                    f"Due date: {due}\n"
                ]
                if with_attachment
                else []
            ),
        }
    )


def make_receipt(index: int) -> RawEmail:
    vendor = _pick(RECEIPT_VENDORS, index)
    amount = 8 + ((index * 13) % 120) + (index % 10) / 10
    return RawEmail.model_validate(
        {
            "id": f"gen-{index + 1}",
            "threadId": f"gen-thread-{index + 1}",
            "subject": f"Receipt for your {vendor['name']} payment",
            "from": f"{vendor['name']} <{vendor['from']}>",
            "date": format_rfc_date(index),
            "snippet": f"You paid {money(amount, 'USD')} — payment received.",
            "bodyText": f"""
{vendor['name']} Receipt

Amount paid: {money(amount, "USD")}
Payment date: July {(index % 20) + 1}, 2026
Status: Paid in full

This is not a bill. No further action needed.
""".strip(),
            "attachmentTexts": [],
        }
    )


def make_personal(index: int) -> RawEmail:
    from_addr = _pick(PEOPLE, index)
    topics = (
        ("Team lunch next week?", "Want to grab lunch with the team next week? No rush either way."),
        ("Birthday dinner plans?", "Are you free for birthday dinner? Thinking Italian — no invoices here."),
        ("Coffee catch-up tomorrow?", "Free at 10am tomorrow for a quick coffee? Just catch up."),
        ("Weekend hiking photos", "Here are a few shots from the trail. Hope you had a good one!"),
        ("Docs review ping", "Can you skim the draft proposal when you get a chance? No payment involved."),
        ("Office move reminders", "Reminder: bring your badge on Friday. Facilities handles the rest."),
    )
    subject, body = _pick(topics, index)
    return RawEmail.model_validate(
        {
            "id": f"gen-{index + 1}",
            "threadId": f"gen-thread-{index + 1}",
            "subject": subject,
            "from": from_addr,
            "date": format_rfc_date(index),
            "snippet": body[:80],
            "bodyText": body,
            "attachmentTexts": [],
        }
    )


def make_newsletter(index: int) -> RawEmail:
    from_addr = _pick(NEWSLETTERS, index)
    return RawEmail.model_validate(
        {
            "id": f"gen-{index + 1}",
            "threadId": f"gen-thread-{index + 1}",
            "subject": f"This week’s digest #{index + 1}",
            "from": from_addr,
            "date": format_rfc_date(index),
            "snippet": "Five launches worth knowing about",
            "bodyText": """
Weekly Digest

1. Product polish
2. Faster exports
3. New shortcuts
4. Customer stories
5. Hiring update

Unsubscribe anytime. This is a marketing newsletter, not a bill.
""".strip(),
            "attachmentTexts": [],
        }
    )


def make_shipping(index: int) -> RawEmail:
    from_addr = _pick(SHIPPERS, index)
    tracking = f"TRK-{900000 + index}"
    return RawEmail.model_validate(
        {
            "id": f"gen-{index + 1}",
            "threadId": f"gen-thread-{index + 1}",
            "subject": f"Your package has shipped — {tracking}",
            "from": from_addr,
            "date": format_rfc_date(index),
            "snippet": f"Tracking number {tracking}",
            "bodyText": f"""
Good news — your order shipped.

Tracking: {tracking}
Estimated delivery: July {(index % 15) + 10}, 2026

No payment is due. This is a shipping notice only.
""".strip(),
            "attachmentTexts": [],
        }
    )


def generate_demo_emails(count: int = 250) -> list[RawEmail]:
    """Deterministic corpus. ~45% payable invoices, ~55% non-invoices."""
    if count < 1:
        raise ValueError("count must be >= 1")

    emails: list[RawEmail] = []
    for i in range(count):
        bucket = i % 20
        if bucket < 9:
            emails.append(make_invoice(i))
        elif bucket < 13:
            emails.append(make_receipt(i))
        elif bucket < 16:
            emails.append(make_personal(i))
        elif bucket < 18:
            emails.append(make_newsletter(i))
        else:
            emails.append(make_shipping(i))
    return emails


GENERATED_DEMO_EMAILS_250 = generate_demo_emails(250)

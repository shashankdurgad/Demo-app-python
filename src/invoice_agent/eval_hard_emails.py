"""100 unique eval emails for a gpt-5.2 teacher dataset.

Buckets are exact. Ambiguous cases (~10) sit inside those buckets so a
calibrated model should emit low confidence without inventing fields.
Every extractable field is present in the email text; missing fields are
deliberately absent.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from invoice_agent.types import RawEmail

EXPECTED_BUCKETS = {
    "clear_invoice": 35,
    "receipt_paid": 15,
    "statement_balance": 10,
    "no_due_date": 8,
    "no_currency": 7,
    "multi_amount": 6,
    "marketing": 5,
    "shipping": 4,
    "credit_note": 4,
    "personal": 3,
    "non_english": 3,
}


@dataclass(frozen=True)
class EvalHardCase:
    bucket: str
    ambiguous: bool
    email: RawEmail


def _mail(
    n: int,
    subject: str,
    from_: str,
    date: str,
    snippet: str,
    body: str,
    attachments: list[str] | None = None,
) -> RawEmail:
    return RawEmail(
        id=f"eval-hard-{n}",
        thread_id=f"eval-hard-thread-{n}",
        subject=subject,
        from_=from_,
        date=date,
        snippet=snippet,
        body_text=body,
        attachment_texts=attachments or [],
    )


def _cases() -> list[EvalHardCase]:
    out: list[EvalHardCase] = []

    # --- 35 clear payable invoices (last 4 are the ambiguous subset) ---
    clear = [
        _mail(
            1,
            "Invoice AA-909 — Northpeak Timber LLC",
            "accounts@northpeak-timber.example",
            "Tue, 04 Aug 2026 09:12:00 +0000",
            "Invoice AA-909 for CAD 4,812.00 due 22 August 2026.",
            """
Northpeak Timber LLC
Accounts receivable

TAX INVOICE
Invoice number: AA-909
Bill to: Ledgerline Demo Co

Kiln-dried spruce, 2.4m — CAD 4,812.00

Amount due: CAD 4,812.00
Due date: 22 August 2026

Please pay by EFT quoting AA-909.
""",
        ),
        _mail(
            2,
            "Helios Printworks invoice #10021",
            "billing@helios-print.example",
            "Mon, 10 Aug 2026 14:03:00 +0000",
            "Invoice #10021 is $312.50 USD, due 09/01/2026.",
            """
HELIOS PRINTWORKS
Invoice #10021

Business cards, 500ct ............... $280.00
Rush surcharge ..................... $32.50
----------------------------------------
TOTAL DUE .......................... $312.50 USD
PAY BY ............................. 09/01/2026

ACH to Helios Printworks. Memo #10021.
""",
        ),
        _mail(
            3,
            "INV/2026/0042 from Kite & Needle Ltd",
            "finance@kiteandneedle.co.uk",
            "Wed, 12 Aug 2026 08:40:00 +0000",
            "INV/2026/0042 for £1,088.40 due 30 Sep 2026.",
            """
Kite & Needle Ltd
Studio retainers — August

Invoice: INV/2026/0042
Issued: 12 August 2026
Payment due: 30 Sep 2026

Net: £907.00
VAT 20%: £181.40
Total payable: £1,088.40 GBP

Sort code on file. Quote INV/2026/0042.
""",
        ),
        _mail(
            4,
            "Vesper Coffee Roasters — invoice 88412",
            "orders@vesper-roasters.example",
            "Fri, 07 Aug 2026 11:18:00 +0000",
            "Invoice 88412, EUR 246.00, due 21.08.2026.",
            "Hi — wholesale beans for the office kitchen.\n\nVendor: Vesper Coffee Roasters\nInvoice 88412\nAmount due EUR 246.00\nDue 21.08.2026\n\nThanks,\nMaya at Vesper\n",
        ),
        _mail(
            5,
            "Atlas Crane Hire Pty Ltd tax invoice W-2026-17",
            "ar@atlascrane.au",
            "Thu, 06 Aug 2026 00:22:00 +0000",
            "W-2026-17 AUD 18,750.00 due 15 September 2026.",
            """
ATLAS CRANE HIRE PTY LTD
TAX INVOICE W-2026-17

Site: Docklands lift, 28 July 2026
Hire of 80t crawler ................ AUD 18,750.00

Total amount payable: AUD 18,750.00
Due date: 15 September 2026
ABN on letterhead.
""",
        ),
        _mail(
            6,
            "Invoice from Quinlan Office Interiors Inc",
            "invoices@quinlan-interiors.example",
            "Sat, 01 Aug 2026 16:55:00 +0000",
            "QI-4408 $24,150.00 due October 3, 2026.",
            """
Quinlan Office Interiors Inc.

Invoice QI-4408
Client: Demo Co — 14th floor fit-out deposit

Balance due: $24,150.00 USD
Due date: October 3, 2026

Wire instructions attached to this email body:
Account name Quinlan Office Interiors Inc.
""",
        ),
        _mail(
            7,
            "Boreal Snow Removal — INV 2026-088",
            "billing@boreal-snow.example",
            "Sun, 02 Aug 2026 19:01:00 +0000",
            "INV 2026-088 CAD 960.00 due 18 Aug 2026.",
            "Season contract call-out 31 Jul.\n\nBoreal Snow Removal\nInvoice INV 2026-088\nAmount owing: CAD 960.00\nPlease remit by 18 Aug 2026.\n",
        ),
        _mail(
            8,
            "Meridian Lab Glass invoice MLG-5519",
            "ar@meridian-labglass.example",
            "Tue, 11 Aug 2026 07:44:00 +0000",
            "MLG-5519 CHF 3,420.75 due 2026-09-08.",
            """
Meridian Lab Glass
Invoice MLG-5519

Borosilicate flasks, lot 19C
Betrag / Amount due: CHF 3,420.75
Fällig / Due: 2026-09-08

IBAN on file. Quote MLG-5519.
""",
        ),
        _mail(
            9,
            "Pebble Path Landscaping bill PP-331",
            "hello@pebblepath.example",
            "Wed, 05 Aug 2026 13:27:00 +0000",
            "PP-331 NZD 1,640.00 due 28 August 2026.",
            """
pebble path landscaping

invoice pp-331
july courtyard tidy + plants

you owe: nzd 1,640.00
pay by: 28 August 2026

bank: pebble path landscaping ltd
""",
        ),
        _mail(
            10,
            "Ironclad Welding Co. invoice 10045",
            "accounts@ironclad-weld.example",
            "Thu, 13 Aug 2026 10:09:00 +0000",
            "Invoice 10045 for $8,900.00 USD due 09/20/2026.",
            """
IRONCLAD WELDING CO.

INVOICE 10045
Job: mezzanine rails, Building C

LABOR 42h ........................ $6,300.00
MATERIALS ....................... $2,600.00
AMOUNT DUE ...................... $8,900.00 USD
DUE DATE ........................ 09/20/2026
""",
        ),
        _mail(
            11,
            "Lumen Display Systems — invoice LDS/77",
            "billing@lumen-display.example",
            "Fri, 14 Aug 2026 15:33:00 +0000",
            "LDS/77 SGD 5,118.20 due 1 Oct 2026.",
            "Lumen Display Systems Pte.\n\nInvoice LDS/77\nLED wall hire, conference week.\nTotal due: SGD 5,118.20\nDue date: 1 Oct 2026\n",
        ),
        _mail(
            12,
            "Cascadia IT Support LLC invoice CIS-2026-014",
            "invoices@cascadia-it.example",
            "Mon, 17 Aug 2026 18:02:00 +0000",
            "CIS-2026-014 $2,240.00 due August 31, 2026.",
            """
Cascadia IT Support LLC
Managed services — July

Invoice number: CIS-2026-014
Amount due: $2,240.00 USD
Payment due date: August 31, 2026

ACH: Cascadia IT Support LLC
""",
        ),
        _mail(
            13,
            "Bramble Catering invoice BR-9092",
            "accounts@bramble-catering.example",
            "Tue, 18 Aug 2026 09:50:00 +0000",
            "BR-9092 £412.15 due 25/08/2026.",
            "Bramble Catering\nInvoice BR-9092\nBoard lunch 14 Aug — 18 covers.\nPlease pay £412.15 GBP by 25/08/2026.\n",
        ),
        _mail(
            14,
            "Oak & Iron Facilities — invoice 77821",
            "ar@oakandiron.example",
            "Wed, 19 Aug 2026 12:11:00 +0000",
            "Invoice 77821 EUR 6,600.00 due 15.09.2026.",
            """
Oak & Iron Facilities

INVOICE 77821
Quarterly HVAC maintenance

Total Amount Due: EUR 6,600.00
Payment Due Date: 15.09.2026
""",
        ),
        _mail(
            15,
            "Redline Auto Fleet invoice RLF-3301",
            "billing@redline-fleet.example",
            "Thu, 20 Aug 2026 06:28:00 +0000",
            "RLF-3301 $1,199.00 due Sep 12, 2026.",
            "Redline Auto Fleet\nInvoice RLF-3301\nVan 14 service + tyres.\nAmount due: $1,199.00 USD\nDue: Sep 12, 2026\n",
        ),
        _mail(
            16,
            "Solstice Photography invoice SP-16B",
            "maya@solstice-photo.example",
            "Fri, 21 Aug 2026 21:04:00 +0000",
            "SP-16B $880.00 due 04 September 2026.",
            """
From: Solstice Photography

Invoice SP-16B
Product stills, 40 retouched frames.

Please transfer $880.00 USD by 04 September 2026.
Invoice number SP-16B on the remittance.
""",
        ),
        _mail(
            17,
            "Harborline Marine Supplies INV-HL-2026-9",
            "accounts@harborline-marine.example",
            "Sat, 22 Aug 2026 04:16:00 +0000",
            "INV-HL-2026-9 NOK 12,450.00 due 2026-09-30.",
            "Harborline Marine Supplies AS\nInvoice INV-HL-2026-9\nFenders and line, order 441.\nÅ betale / Amount due: NOK 12,450.00\nForfall / Due date: 2026-09-30\n",
        ),
        _mail(
            18,
            "Wicker & Finch Legal — invoice WF/2026/203",
            "billing@wickerfinch.example",
            "Sun, 23 Aug 2026 17:41:00 +0000",
            "WF/2026/203 £3,300.00 due 14 October 2026.",
            """
Wicker & Finch LLP

INVOICE WF/2026/203
Professional fees, matter DEMO-11

Amount due: £3,300.00 GBP
Due date: 14 October 2026

This is a bill for legal services.
""",
        ),
        _mail(
            19,
            "Pixelbarn Creative invoice 42",
            "hello@pixelbarn.example",
            "Mon, 24 Aug 2026 10:00:00 +0000",
            "Invoice 42 for $3.50 USD due 31 Aug 2026.",
            "Pixelbarn Creative\nInvoice 42\nStock photo license top-up.\nTotal due: $3.50 USD\nDue date: 31 Aug 2026\nYes, three dollars fifty.\n",
        ),
        _mail(
            20,
            "Nimbus HVAC Services invoice NHS-880",
            "ar@nimbus-hvac.example",
            "Tue, 25 Aug 2026 08:22:00 +0000",
            "NHS-880 $119,000.00 due 11 Nov 2026.",
            """
Nimbus HVAC Services

INVOICE NHS-880
Rooftop plant replacement — progress claim 1

Amount due: $119,000.00 USD
Due date: 11 Nov 2026
""",
        ),
        _mail(
            21,
            "Copperline Electrical invoice CL-10021",
            "invoices@copperline-elec.example",
            "Wed, 26 Aug 2026 13:55:00 +0000",
            "CL-10021 £2,075.00 due 09 September 2026.",
            "Copperline Electrical Ltd\nInvoice CL-10021\nBoard replacement, unit 3.\nPlease pay £2,075.00 by 09 September 2026.\n",
        ),
        _mail(
            22,
            "Fieldnote Surveyors — invoice FN-2026-0042",
            "accounts@fieldnote-survey.example",
            "Thu, 27 Aug 2026 09:19:00 +0000",
            "FN-2026-0042 AUD 7,220.00 due 20/09/2026.",
            """
Fieldnote Surveyors

Tax invoice FN-2026-0042
Boundary re-survey, lot 88

Total payable: AUD 7,220.00
Due: 20/09/2026
""",
        ),
        _mail(
            23,
            "Ambergrain Bakery Wholesale invoice AG-551",
            "billing@ambergrain.example",
            "Fri, 28 Aug 2026 05:47:00 +0000",
            "AG-551 EUR 188.40 due 04.09.2026.",
            "Ambergrain Bakery Wholesale\nInvoice AG-551\nStanding bread order w/c 24 Aug.\nAmount due: EUR 188.40\nDue date: 04.09.2026\n",
        ),
        _mail(
            24,
            "Driftwood Events invoice DE-19",
            "finance@driftwood-events.example",
            "Sat, 29 Aug 2026 16:02:00 +0000",
            "DE-19 $9,450.00 USD due October 1, 2026.",
            """
DRIFTWOOD EVENTS
Invoice DE-19

Offsite facilitation, 2 days + kit hire
AMOUNT DUE: $9,450.00 USD
DUE DATE: October 1, 2026
""",
        ),
        _mail(
            25,
            "Sequoia Archive Storage — invoice SAS-3008",
            "ar@sequoia-archive.example",
            "Sun, 30 Aug 2026 11:36:00 +0000",
            "SAS-3008 $440.00 due 2026-09-15.",
            "Sequoia Archive Storage\nInvoice SAS-3008\nQ3 carton storage.\nAmount due: $440.00 USD\nDue date: 2026-09-15\n",
        ),
        _mail(
            26,
            "Nightowl Security Ltd invoice NOS-77A",
            "billing@nightowl-security.example",
            "Mon, 31 Aug 2026 22:08:00 +0000",
            "NOS-77A £6,080.00 due 30 September 2026.",
            """
Nightowl Security Ltd

Invoice NOS-77A
Overnight coverage, August roster

Total due: £6,080.00 GBP
Pay by: 30 September 2026
""",
        ),
        _mail(
            27,
            "Paperplane Couriers invoice PPC-1007",
            "accounts@paperplane-couriers.example",
            "Tue, 01 Sep 2026 07:14:00 +0000",
            "PPC-1007 ZAR 2,960.00 due 12 Sep 2026.",
            "Paperplane Couriers\nInvoice PPC-1007\nSame-day runs, week 34.\nAmount due: ZAR 2,960.00\nDue date: 12 Sep 2026\n",
        ),
        _mail(
            28,
            "Glacier Water Coolers — invoice GWC-44",
            "invoices@glacier-water.example",
            "Wed, 02 Sep 2026 12:48:00 +0000",
            "GWC-44 DKK 1,125.00 due 16/09/2026.",
            """
Glacier Water Coolers ApS
Faktura GWC-44

Bottle rental + 12 fills
Beløb / Amount due: DKK 1,125.00
Betalingsdato / Due: 16/09/2026
""",
        ),
        _mail(
            29,
            "Thornfield Uniforms invoice TFU-2026-12",
            "ar@thornfield-uniforms.example",
            "Thu, 03 Sep 2026 08:31:00 +0000",
            "TFU-2026-12 $2,810.00 due September 24, 2026.",
            "Thornfield Uniforms\nInvoice TFU-2026-12\nWarehouse polos, 80 units.\nPlease pay $2,810.00 USD by September 24, 2026.\n",
        ),
        _mail(
            30,
            "Maple Court Property Mgmt invoice MC-8801",
            "billing@maplecourt-pm.example",
            "Fri, 04 Sep 2026 15:09:00 +0000",
            "MC-8801 CAD 3,050.00 due 01 Oct 2026.",
            """
Maple Court Property Management

Invoice MC-8801
Common-area cleaning, August

Amount due: CAD 3,050.00
Due date: 01 Oct 2026
""",
        ),
        _mail(
            31,
            "Yarrow Botanicals invoice YB-10021",
            "orders@yarrow-botanicals.example",
            "Sat, 05 Sep 2026 10:44:00 +0000",
            "YB-10021 $126.80 due 19 September 2026.",
            "Yarrow Botanicals\nInvoice YB-10021\nOffice plants, quarterly.\nTotal due: $126.80 USD\nDue: 19 September 2026\n",
        ),
        # Ambiguous clear-invoice slots (golden still only from the text)
        _mail(
            32,
            "Invoice from Voltara Energy — see attachment",
            "billing@voltara-energy.example",
            "Sun, 06 Sep 2026 09:02:00 +0000",
            "Please pay the attached invoice.",
            """
Hello,

Please process the attached Voltara Energy invoice (file: invoice-sept.pdf).

The PDF is not included in this message. I cannot restate the amount or
due date from memory — use the attachment only.

Kind regards,
Voltara Energy billing
""",
        ),
        _mail(
            33,
            "FW: scan of Brightforge Prototypes invoice",
            "shop@brightforge.example",
            "Mon, 07 Sep 2026 18:27:00 +0000",
            "OCR of a blurry scan, figures uncertain.",
            """
OCR output of a phone photo (low contrast, digits smeared):

Vend0r: Brlghtforge Prototypes
Inv0ice ?: BF-??17 or BF-8117 (stamp overlaps the number)
Amount due: 1,24O.5O or 7,240.50 — the first digit is a stain
Curr ency: possibly USD. The symbol is a blob.
Due: "Sept ? 2026" — day unreadable

Operator note: do not guess. Source scan is illegible.
""",
        ),
        _mail(
            34,
            "Cinderblock Construction invoice (truncated)",
            "ar@cinderblock-const.example",
            "Tue, 08 Sep 2026 11:15:00 +0000",
            "Invoice CB-… body cut off in transit.",
            """
Cinderblock Construction Inc.
INVOICE CB-

Progress claim for the west wing pour.

Amount d
Due da

[message truncated by mail gateway after 240 bytes]
""",
        ),
        _mail(
            35,
            "Invoice as discussed — Sandbar Cleaning",
            "hello@sandbar-cleaning.example",
            "Wed, 09 Sep 2026 07:58:00 +0000",
            "As discussed last week.",
            """
Hi,

Sandbar Cleaning here — invoice is the one we talked about on the call.
Same as last time, I think? I'll send the PDF later if you still need it.

No numbers in this email on purpose; I don't have the book in front of me.

Jess
""",
        ),
    ]
    for email in clear:
        n = int(email.id.split("-")[-1])
        out.append(EvalHardCase("clear_invoice", n >= 32, email))

    # --- 15 receipts / already paid (amount present; not payable) ---
    receipts = [
        (
            False,
            _mail(
                36,
                "Receipt for your Figma Professional payment",
                "Figma <receipts@figma.com>",
                "Thu, 10 Jul 2026 08:00:00 +0000",
                "You paid $45.00. This is not a bill.",
                """
Figma Receipt

Figma Professional — July
Amount paid: $45.00 USD
Date paid: July 10, 2026
Status: Paid in full

This is a receipt, not an invoice. No payment is due.
""",
            ),
        ),
        (
            False,
            _mail(
                37,
                "Your Adobe Creative Cloud receipt",
                "Adobe <noreply@adobe.com>",
                "Sat, 04 Jul 2026 07:12:00 +0000",
                "Payment received: $59.99",
                """
Adobe Receipt

Creative Cloud All Apps
Amount charged: $59.99 USD
Payment date: July 4, 2026
Status: Paid in full

This is not a bill. No further action needed.
""",
            ),
        ),
        (
            False,
            _mail(
                38,
                "Uber receipt: trip completed",
                "Uber Receipts <receipts@uber.com>",
                "Mon, 11 Aug 2026 22:14:00 +0000",
                "You paid $18.40 for this trip.",
                "Uber\nTrip receipt\nFrom office to station.\nAmount paid: $18.40 USD\nCharged to Visa ••4412 on 11 Aug 2026.\nThis trip is already paid. Not an invoice.\n",
            ),
        ),
        (
            False,
            _mail(
                39,
                "Notion — payment confirmation",
                "Notion <receipts@notion.so>",
                "Tue, 12 Aug 2026 06:03:00 +0000",
                "We received $96.00 for your workspace.",
                """
Payment confirmation

Notion Plus, annual
Amount paid: $96.00 USD
Paid on: 12 Aug 2026
Invoice? No — this is a payment receipt. Balance due: $0.00
""",
            ),
        ),
        (
            False,
            _mail(
                40,
                "Zoom Workplace receipt",
                "Zoom <receipts@zoom.us>",
                "Wed, 13 Aug 2026 16:40:00 +0000",
                "Charged $149.90 — paid.",
                "Zoom Workplace\nReceipt #Z-88912\nAmount paid: $149.90 USD\nPaid: 13 August 2026\nDo not pay again. This is a receipt for a completed charge.\n",
            ),
        ),
        (
            False,
            _mail(
                41,
                "Dropbox payment received",
                "Dropbox <noreply@dropbox.com>",
                "Thu, 14 Aug 2026 09:21:00 +0000",
                "Your card was charged $119.88.",
                "Dropbox Plus\nPayment confirmation\nAmount paid: $119.88 USD\nDate paid: 14 Aug 2026\nThis is not a request for payment.\n",
            ),
        ),
        (
            False,
            _mail(
                42,
                "GitHub Copilot — charge succeeded",
                "GitHub <billing@github.com>",
                "Fri, 15 Aug 2026 01:55:00 +0000",
                "Paid $19.00 for Copilot.",
                "GitHub billing receipt\nGitHub Copilot Business seat\nAmount paid: $19.00 USD\nPaid on: 15 Aug 2026\nStatus: Payment complete. Nothing is outstanding.\n",
            ),
        ),
        (
            False,
            _mail(
                43,
                "AWS payment confirmation — thank you",
                "Amazon Web Services <no-reply@amazon.com>",
                "Sat, 16 Aug 2026 12:00:00 +0000",
                "We received your payment of $312.88.",
                """
Amazon Web Services
PAYMENT CONFIRMATION

We successfully charged your card.
Amount paid: $312.88 USD
Payment date: August 16, 2026
Original invoice 123456789 is now settled.

This email is a receipt. No amount is due.
""",
            ),
        ),
        (
            False,
            _mail(
                44,
                "Hotel stay paid — The Marlowe receipt",
                "The Marlowe <receipts@themarlowe.example>",
                "Sun, 17 Aug 2026 10:18:00 +0000",
                "You paid GBP 214.00 at checkout.",
                "The Marlowe, receipt R-4419\nRoom 508, 1 night.\nAmount paid: £214.00 GBP\nPaid at checkout 17 Aug 2026.\nBalance: 0.00. This is not an invoice.\n",
            ),
        ),
        (
            False,
            _mail(
                45,
                "Domain renewal receipt — paid",
                "Gandi <noreply@gandi.net>",
                "Mon, 18 Aug 2026 04:44:00 +0000",
                "Paid EUR 15.99 for demo-co.example.",
                "Gandi receipt\nDomain renewal demo-co.example\nAmount paid: EUR 15.99\nPaid: 18 Aug 2026\nThis purchase is complete. No invoice to pay.\n",
            ),
        ),
        (
            False,
            _mail(
                46,
                "Q-Park receipt (already charged)",
                "Q-Park <receipts@q-park.example>",
                "Tue, 19 Aug 2026 19:07:00 +0000",
                "Parking paid: EUR 8.40",
                "Q-Park receipt 8821-A\nAmount paid: EUR 8.40\nPaid by contactless 19 Aug 2026 19:01.\nNot a bill.\n",
            ),
        ),
        (
            False,
            _mail(
                47,
                "Northside Gym — dues paid",
                "Northside Gym <billing@northside-gym.example>",
                "Wed, 20 Aug 2026 07:30:00 +0000",
                "Membership $62.00 collected.",
                "Northside Gym\nPayment receipt\nAugust dues\nAmount paid: $62.00 USD\nCollected: 20 Aug 2026\nYour account has no balance due.\n",
            ),
        ),
        (
            False,
            _mail(
                48,
                "Conference ticket receipt — paid",
                "Leadline Summit <tickets@leadline.example>",
                "Thu, 21 Aug 2026 14:12:00 +0000",
                "You paid $1,250.00 for one pass.",
                """
Leadline Summit
TICKET RECEIPT

Attendee pass, already purchased
Amount paid: $1,250.00 USD
Paid on: 21 Aug 2026
Order ORD-5520 is complete. This is not an invoice.
""",
            ),
        ),
        (
            True,
            _mail(
                49,
                "Invoice INV-28419 from Stripe — PAID",
                "Stripe Billing <invoices@stripe.com>",
                "Fri, 22 Aug 2026 16:30:00 +0000",
                "Invoice INV-28419 for $1,499.00 — payment received.",
                """
Stripe, Inc.

TAX INVOICE INV-28419  (PAID)
Bill to: Ledgerline Demo

Amount: $1,499.00 USD
Invoice date: August 1, 2026

PAYMENT RECEIVED 22 Aug 2026.
Status: Paid in full. Do not pay this invoice again.
This email is a receipt for a settled invoice.
""",
            ),
        ),
        (
            True,
            _mail(
                50,
                "Cloudhost Ltd invoice 7781 — already paid",
                "accounts@cloudhost.example",
                "Sat, 23 Aug 2026 11:45:00 +0000",
                "Invoice 7781 EUR 890.00 was collected.",
                """
Cloudhost Ltd

INVOICE 7781
Total: EUR 890.00
Due Date printed on the original: 16/07/2026

UPDATE: your card on file was charged EUR 890.00 on 23 Aug 2026.
The invoice is closed. Amount paid: EUR 890.00
This is a payment confirmation, not a request to pay.
""",
            ),
        ),
    ]
    for ambiguous, email in receipts:
        out.append(EvalHardCase("receipt_paid", ambiguous, email))

    # --- 10 statements: amount = balance due, not total billed ---
    statements = [
        (
            False,
            _mail(
                51,
                "Northern Power — August account statement",
                "Northern Power <statements@northernpower.example>",
                "Mon, 24 Aug 2026 08:00:00 +0000",
                "Balance due £86.20. Do not pay the billed total.",
                """
Northern Power
ACCOUNT STATEMENT — August 2026

Previous balance: £40.00
New charges billed this period: £112.40
Payments received: £66.20
Credits: £0.00

Total billed this period: £112.40
BALANCE DUE: £86.20 GBP
Pay by: 12 September 2026
Account 440-221
""",
            ),
        ),
        (
            False,
            _mail(
                52,
                "Rivermill Office Park — service charge statement",
                "Rivermill Estates <accounts@rivermill.example>",
                "Tue, 25 Aug 2026 09:33:00 +0000",
                "Balance due $2,410.00.",
                """
Rivermill Estates
STATEMENT (not a single invoice line)

Q3 service charges billed: $4,800.00
Payments on account: $2,390.00
Total billed: $4,800.00

Balance due: $2,410.00 USD
Due date: 30 September 2026
Statement no. RM-ST-2026-Q3
""",
            ),
        ),
        (
            False,
            _mail(
                53,
                "Orbit Analytics usage statement",
                "Orbit Analytics <billing@orbit-analytics.example>",
                "Wed, 26 Aug 2026 15:16:00 +0000",
                "Please pay the remaining balance of $210.00.",
                "Orbit Analytics\nMonthly statement\nUsage billed: $540.00 USD\nCredits applied: $330.00\nTotal billed: $540.00\nBalance due: $210.00 USD\nDue: 09 Sep 2026\nStatement OA-ST-88\n",
            ),
        ),
        (
            False,
            _mail(
                54,
                "Brightline Telecom bill summary",
                "Brightline Telecom <invoices@brightline.example>",
                "Thu, 27 Aug 2026 06:41:00 +0000",
                "Amount now due EUR 47.15.",
                """
Brightline Telecom
Statement 27 Aug 2026

New charges: EUR 91.00
Payments received: EUR 43.85
Total billed: EUR 91.00
Balance due: EUR 47.15
Pay by 10.09.2026
Account statement BT-ST-441
""",
            ),
        ),
        (
            False,
            _mail(
                55,
                "ParcelOps Logistics — trading account statement",
                "ParcelOps <accounts@parcelops.example>",
                "Fri, 28 Aug 2026 12:05:00 +0000",
                "Balance owed $1,075.50.",
                "ParcelOps Logistics\nAccount statement\nInvoices this month (total billed): $3,200.00\nPayments: $2,124.50\nBalance due: $1,075.50 USD\nDue date: 18 September 2026\nStatement POL-ST-19\n",
            ),
        ),
        (
            False,
            _mail(
                56,
                "Harbor Credit Union card statement",
                "Harbor CU <statements@harborcu.example>",
                "Sat, 29 Aug 2026 03:22:00 +0000",
                "Minimum is not the full new charges. Balance due $640.12.",
                """
Harbor Credit Union
CARD STATEMENT

New purchases billed: $1,288.40
Payments received: $648.28
Total billed: $1,288.40

Balance due: $640.12 USD
Payment due date: September 22, 2026
Statement 2026-08-29
""",
            ),
        ),
        (
            False,
            _mail(
                57,
                "Acme SaaS — account balance",
                "Acme SaaS <billing@acme-saas.example>",
                "Sun, 30 Aug 2026 17:50:00 +0000",
                "Pay the outstanding $88.00, not the $499 list.",
                "Acme SaaS statement\nList price billed: $499.00\nPromo credit: $411.00\nTotal billed: $499.00\nOutstanding balance due: $88.00 USD\nDue 14 Sep 2026\nStatement ACME-ST-07\n",
            ),
        ),
        (
            False,
            _mail(
                58,
                "Nova Design Co client statement",
                "Nova Design Co <finance@novadesign.example>",
                "Mon, 31 Aug 2026 10:11:00 +0000",
                "Remaining balance £1,500.00.",
                """
Nova Design Co
Client statement — Project Kestrel

Fees billed to date: £6,000.00
Retainer payments received: £4,500.00
Total billed: £6,000.00
Balance due: £1,500.00 GBP
Due: 05 October 2026
Statement ND-ST-12
""",
            ),
        ),
        (
            False,
            _mail(
                59,
                "City Water — quarterly statement",
                "City Water <billing@citywater.example>",
                "Tue, 01 Sep 2026 08:08:00 +0000",
                "Balance due $73.25.",
                "City Water\nQuarterly statement\nUsage billed: $110.00\nLeak allowance credit: $36.75\nTotal billed: $110.00\nBalance due: $73.25 USD\nDue date: 20 Sep 2026\nStatement CW-2026-Q3\n",
            ),
        ),
        (
            True,
            _mail(
                60,
                "Apex Advisory — statement (scan)",
                "Apex Advisory <billing@apex-advisory.example>",
                "Wed, 02 Sep 2026 14:29:00 +0000",
                "Figures hard to read; balance line is the one that matters.",
                """
Apex Advisory
STATEMENT (fax scan, some figures smudged)

Fees billed this quarter: $12,000.00 (this is NOT the amount to pay)
Payments on account: amount smudged — "$,??0.00"
A handwritten note in the margin: "pls pay the BALANCE DUE only"

BALANCE DUE line (the only fully readable money line): $4,250.00 USD
Due date on the footer is smudged.

Statement number maybe APX-ST-?? — unreadable.
If a field is not readable, leave it unset. Do not use $12,000.00 as the amount.
""",
            ),
        ),
    ]
    for ambiguous, email in statements:
        out.append(EvalHardCase("statement_balance", ambiguous, email))

    # --- 8 invoices with no calendar due date (dueDate must be null) ---
    no_due = [
        (
            False,
            _mail(
                61,
                "Invoice INV-1042 from Northwind Supplies",
                "billing@northwind.example",
                "Fri, 10 Jul 2026 09:14:00 +0000",
                "INV-1042 for £1,240.50. Terms Net 30. No calendar due date.",
                """
Northwind Supplies Billing

Please find invoice INV-1042 for office supplies.

Total Amount Due: £1,240.50 GBP
Invoice Number: INV-1042
Payment terms: Net 30

There is no due date printed on this invoice. Do not infer one from Net 30.
""",
            ),
        ),
        (
            False,
            _mail(
                62,
                "Slack Technologies invoice 209441",
                "billing@slack.com",
                "Mon, 03 Aug 2026 12:00:00 +0000",
                "Invoice 209441 $850.00. Terms: due upon receipt. No date.",
                "Slack Technologies\nInvoice 209441\nAmount due: $850.00 USD\nTerms: Due upon receipt\nNo calendar due date is stated.\n",
            ),
        ),
        (
            False,
            _mail(
                63,
                "GitHub, Inc. invoice GH-88210",
                "billing@github.com",
                "Tue, 04 Aug 2026 12:00:00 +0000",
                "GH-88210 $420.00. Payment terms Net 45.",
                """
GitHub, Inc.

Invoice GH-88210
Organization plan
Amount due: $420.00 USD
Payment terms: Net 45 from invoice date

Invoice date is not printed. No due date is printed.
""",
            ),
        ),
        (
            False,
            _mail(
                64,
                "Maya Chen Studio invoice MCS-18",
                "maya@studio.example",
                "Wed, 05 Aug 2026 15:22:00 +0000",
                "MCS-18 $2,400.00. Pay when you can — no date.",
                "Maya Chen Studio\nInvoice MCS-18\nIllustration batch B.\nAmount due: $2,400.00 USD\nNotes: pay whenever convenient. No due date.\n",
            ),
        ),
        (
            False,
            _mail(
                65,
                "Harcourt & Co invoice HAR-9003",
                "accounts@harcourt-legal.example",
                "Thu, 06 Aug 2026 11:09:00 +0000",
                "HAR-9003 £6,750.00. Terms Net 14. No date.",
                "Harcourt & Co\nInvoice HAR-9003\nAdvisory, July.\nAmount due: £6,750.00 GBP\nPayment terms: Net 14\nNo calendar due date appears on this invoice.\n",
            ),
        ),
        (
            False,
            _mail(
                66,
                "Spotify for Business invoice SPOT-3310",
                "billing@spotify.com",
                "Fri, 07 Aug 2026 08:08:00 +0000",
                "SPOT-3310 EUR 99.00. Terms: Net 30.",
                "Spotify for Business\nInvoice SPOT-3310\nAmount due: EUR 99.00\nPayment terms: Net 30\nDue date: not specified\n",
            ),
        ),
        (
            False,
            _mail(
                67,
                "Invoice 4401 — Brightforge Prototypes",
                "ar@brightforge.example",
                "Sat, 08 Aug 2026 19:40:00 +0000",
                "Invoice 4401 $1,010.00. No terms, no date.",
                """
Brightforge Prototypes LLC

INVOICE 4401
SLA print run

Total due: $1,010.00 USD

This invoice does not list a due date or payment terms.
""",
            ),
        ),
        (
            True,
            _mail(
                68,
                "Invoice from Oakline Press (body cut)",
                "billing@oakline-press.example",
                "Sun, 09 Aug 2026 13:13:00 +0000",
                "OP-77 $275.00… remainder missing.",
                """
Oakline Press
Invoice OP-77
Amount due: $275.00 USD
Payment ter

[truncated]

The rest of the invoice, including any due date if one existed, was not delivered.
""",
            ),
        ),
    ]
    for ambiguous, email in no_due:
        out.append(EvalHardCase("no_due_date", ambiguous, email))

    # --- 7 invoices with no currency indicator (currency must be null) ---
    no_ccy = [
        _mail(
            69,
            "Invoice 3309 from Fieldstone Janitorial",
            "accounts@fieldstone-janitorial.example",
            "Mon, 10 Aug 2026 07:07:00 +0000",
            "Invoice 3309 amount due 440.00 due 21 Aug 2026.",
            """
Fieldstone Janitorial

Invoice 3309
Night cleaning, week 31

Amount due: 440.00
Due date: 21 Aug 2026

No currency symbol or code is printed. Do not assume one.
""",
        ),
        _mail(
            70,
            "Redwood Signage invoice RS-12",
            "billing@redwood-signage.example",
            "Tue, 11 Aug 2026 09:09:00 +0000",
            "RS-12 total 1280.50 due 02 Sep 2026.",
            "Redwood Signage\nInvoice RS-12\nLobby letters.\nTotal payable: 1280.50\nDue: 02 Sep 2026\nCurrency is not indicated anywhere.\n",
        ),
        _mail(
            71,
            "Invoice #8804 — Pondside Chemicals",
            "ar@pondside-chem.example",
            "Wed, 12 Aug 2026 10:10:00 +0000",
            "Invoice #8804 due 09/18/2026 amount 75.00.",
            "Pondside Chemicals\nInvoice #8804\nDrum return fee.\nAmount due 75.00\nDue date 09/18/2026\n",
        ),
        _mail(
            72,
            "Larkspur Audio invoice LA-2026-5",
            "invoices@larkspur-audio.example",
            "Thu, 13 Aug 2026 11:11:00 +0000",
            "LA-2026-5 3,350.00 due 30 September 2026.",
            """
Larkspur Audio Co

Invoice LA-2026-5
PA hire, hall B

Please pay 3,350.00 by 30 September 2026.
No $, £, EUR, USD or other currency mark is used.
""",
        ),
        _mail(
            73,
            "Invoice 10021 — Holloway Keys",
            "hello@holloway-keys.example",
            "Fri, 14 Aug 2026 12:12:00 +0000",
            "Invoice 10021, 42.00, due 28 Aug 2026.",
            "Holloway Keys\nInvoice 10021\nRekey two cabinets.\nAmount: 42.00\nDue date: 28 Aug 2026\n",
        ),
        _mail(
            74,
            "Sable Print invoice SP/2026/0042",
            "finance@sable-print.example",
            "Sat, 15 Aug 2026 13:13:00 +0000",
            "SP/2026/0042 amount 910.00 due 07 Oct 2026.",
            "Sable Print\nInvoice SP/2026/0042\nAnnual report, 80pp.\nAmount due: 910.00\nDue date: 07 Oct 2026\nCurrency omitted on purpose.\n",
        ),
        _mail(
            75,
            "Invoice AA-100 from Moss & Pine Joinery",
            "accounts@mossandpine.example",
            "Sun, 16 Aug 2026 14:14:00 +0000",
            "AA-100 6,600.00 due 15 November 2026.",
            "Moss & Pine Joinery\nInvoice AA-100\nReception desk, remaining claim.\nAmount due: 6,600.00\nDue date: 15 November 2026\nNo currency is stated.\n",
        ),
    ]
    for email in no_ccy:
        out.append(EvalHardCase("no_currency", False, email))

    # --- 6 multi-amount emails: amount = total due ---
    multi = [
        (
            False,
            _mail(
                76,
                "Invoice INV-9001 — Northwind Supplies (itemised)",
                "billing@northwind.example",
                "Mon, 17 Aug 2026 09:00:00 +0000",
                "Total due £1,488.60 including tax and shipping.",
                """
Northwind Supplies
INVOICE INV-9001

Subtotal (goods): £1,120.00
Tax (VAT 20%): £224.00
Shipping: £144.60
--------------------------------
Total due: £1,488.60 GBP
Due date: 31 August 2026

Pay the total due, not the subtotal.
""",
            ),
        ),
        (
            False,
            _mail(
                77,
                "Cloudhost Ltd invoice CH-2208",
                "accounts@cloudhost.example",
                "Tue, 18 Aug 2026 09:00:00 +0000",
                "Total due EUR 1,067.00.",
                """
Cloudhost Ltd
INVOICE CH-2208

Compute subtotal: EUR 890.00
Support pack: EUR 50.00
VAT: EUR 127.00
--------------------------------
Total due: EUR 1,067.00
Due Date: 01/09/2026
""",
            ),
        ),
        (
            False,
            _mail(
                78,
                "Stripe invoice INV-99110",
                "invoices@stripe.com",
                "Wed, 19 Aug 2026 09:00:00 +0000",
                "Amount due $1,724.85.",
                "Stripe, Inc.\nInvoice INV-99110\nPlatform fee subtotal: $1,499.00\nTax: $149.90\nShipping of card readers: $75.95\nAmount due: $1,724.85 USD\nDue date: September 5, 2026\n",
            ),
        ),
        (
            False,
            _mail(
                79,
                "ParcelOps invoice PO-4412",
                "accounts@parcelops.example",
                "Thu, 20 Aug 2026 09:00:00 +0000",
                "Please pay $412.18 total.",
                """
ParcelOps Logistics
Invoice PO-4412

Freight subtotal: $300.00
Fuel surcharge: $45.00
Insurance: $22.00
Tax: $45.18
TOTAL DUE: $412.18 USD
Due: 03 Sep 2026
""",
            ),
        ),
        (
            False,
            _mail(
                80,
                "Nova Design Co invoice ND-88",
                "finance@novadesign.example",
                "Fri, 21 Aug 2026 09:00:00 +0000",
                "Grand total £3,960.00.",
                "Nova Design Co\nInvoice ND-88\nDesign subtotal: £3,000.00\nArtworking: £300.00\nVAT: £660.00\nGrand total / amount due: £3,960.00 GBP\nDue date: 12 October 2026\n",
            ),
        ),
        (
            True,
            _mail(
                81,
                "Invoice from Orbit Analytics — several figures",
                "billing@orbit-analytics.example",
                "Sat, 22 Aug 2026 09:00:00 +0000",
                "Body lists four money lines; which is due is poorly labelled.",
                """
Orbit Analytics
Invoice OA-77? or OA-71 — the header is a photocopy crease.

Subtotal: $2,000.00
Tax: $400.00
Shipping: $25.00
A circled number in pen: 2,425.00
Another line says "previous estimate 2,800.00" then struck through.

There is no line that clearly says "total due" or "amount due".
Due date printed: 19 Sep 2026
Currency appears to be USD on the tax line only as a guess in a footnote:
"tax computed in usd" — the footnote is half cut off.

If the total due is not explicit, do not invent it from the estimate.
""",
            ),
        ),
    ]
    for ambiguous, email in multi:
        out.append(EvalHardCase("multi_amount", ambiguous, email))

    # --- 5 marketing / newsletters ---
    marketing = [
        _mail(
            82,
            "Product Weekly: 12 tools we liked",
            "Product Weekly <digest@newsletter.example>",
            "Sun, 23 Aug 2026 06:00:00 +0000",
            "This week's roundup. Unsubscribe at the bottom.",
            "Product Weekly\nIssue 412\n\nTwelve tools our editors liked, none of which you need to pay us for.\nThis is a newsletter. There is no invoice, no amount due, no vendor bill.\n\nUnsubscribe: https://newsletter.example/unsub\n",
        ),
        _mail(
            83,
            "Save 20% on stand desks this weekend",
            "Office Perks <offers@officeperks.example>",
            "Mon, 24 Aug 2026 07:00:00 +0000",
            "Marketing offer. Desks from $249.",
            "Office Perks\nWEEKEND SALE\nStanding desks from $249 — promotional price, not a bill.\nUse code DESK20. This email is marketing. You do not owe Office Perks anything.\n",
        ),
        _mail(
            84,
            "Growth Tips: how we cut CAC",
            "Growth Tips <hello@growthlab.example>",
            "Tue, 25 Aug 2026 07:00:00 +0000",
            "A blog-style newsletter. No payable document.",
            "Hi operators,\n\nThis week: three CAC experiments. Case study mentions a $50k spend as an anecdote about someone else's ad account.\nThat $50k is not an amount you owe. This is not an invoice.\n\n— Growth Lab newsletter\n",
        ),
        _mail(
            85,
            "Dev Digest #881",
            "Dev Digest <news@devdigest.example>",
            "Wed, 26 Aug 2026 07:00:00 +0000",
            "Links and commentary only.",
            "Dev Digest #881\n- A new CSS feature\n- Someone raised $12m (news, not a bill)\nNo invoice number, no due date, no vendor requesting payment.\n",
        ),
        _mail(
            86,
            "You're invited: customer roundtable",
            "Acme SaaS <hello@acme-saas.example>",
            "Thu, 27 Aug 2026 07:00:00 +0000",
            "Event invitation. Free to attend.",
            "Join our customer roundtable on 8 Sep. Attendance is free.\nPlease RSVP. This is not a bill and there is no amount due.\n",
        ),
    ]
    for email in marketing:
        out.append(EvalHardCase("marketing", False, email))

    # --- 4 shipping / delivery, no bill ---
    shipping = [
        _mail(
            87,
            "Your ShopFast package is out for delivery",
            "ShopFast Shipping <ship@shopfast.example>",
            "Fri, 28 Aug 2026 04:00:00 +0000",
            "Tracking SFP-9981. No payment requested.",
            "ShopFast\nShipment SFP-9981 is out for delivery today.\n2 boxes of printer paper.\nThis is a shipping notice. There is no invoice and no amount due in this email.\n",
        ),
        _mail(
            88,
            "QuickCart: delivered to reception",
            "QuickCart Fulfillment <ship@quickcart.example>",
            "Sat, 29 Aug 2026 15:22:00 +0000",
            "Delivered. Signed for by Alex.",
            "QuickCart\nOrder QC-1402 delivered 29 Aug 2026.\nLeft at reception. This email is a delivery confirmation, not a bill.\n",
        ),
        _mail(
            89,
            "ParcelTrack: customs cleared",
            "ParcelTrack <updates@parceltrack.example>",
            "Sun, 30 Aug 2026 02:10:00 +0000",
            "Parcel PT-550 cleared customs.",
            "ParcelTrack update\nParcel PT-550 cleared customs in Newark.\nNo charges are requested in this notice. Not an invoice.\n",
        ),
        _mail(
            90,
            "Harborline Marine: parts shipped",
            "Harborline Marine Supplies <dispatch@harborline-marine.example>",
            "Mon, 31 Aug 2026 09:40:00 +0000",
            "Dispatch note for order 441. Bill comes separately.",
            "Dispatch note\nOrder 441 (fenders) left the warehouse.\nThe commercial invoice will be emailed separately if one is issued.\nThis message is only a shipping notice and contains no amount due.\n",
        ),
    ]
    for email in shipping:
        out.append(EvalHardCase("shipping", False, email))

    # --- 4 credit notes / refunds (not payable) ---
    credits = [
        (
            False,
            _mail(
                91,
                "Credit note CN-2026-014 — Northwind Supplies",
                "billing@northwind.example",
                "Tue, 01 Sep 2026 09:14:00 +0000",
                "Credit note £210.00. Do not pay.",
                """
Northwind Supplies
CREDIT NOTE CN-2026-014

Returned toner, original invoice INV-9000
Credit amount: £210.00 GBP
This is a credit note, not an invoice. No payment is due.
We will apply CN-2026-014 to your account.
""",
            ),
        ),
        (
            False,
            _mail(
                92,
                "Refund confirmation — Figma",
                "Figma <receipts@figma.com>",
                "Wed, 02 Sep 2026 08:00:00 +0000",
                "Refunded $45.00 to your card.",
                "Figma refund\nWe refunded $45.00 USD for an unused month.\nRefund date: 2 Sep 2026\nThis is not an invoice and nothing is payable.\n",
            ),
        ),
        (
            False,
            _mail(
                93,
                "Cloudhost Ltd — credit note CH-CN-19",
                "accounts@cloudhost.example",
                "Thu, 03 Sep 2026 11:45:00 +0000",
                "Credit EUR 90.00 for overbilling.",
                "Cloudhost Ltd\nCREDIT NOTE CH-CN-19\nOverbilled support hours.\nCredit amount: EUR 90.00\nDo not pay this document. It reduces your balance.\n",
            ),
        ),
        (
            True,
            _mail(
                94,
                "Invoice-looking credit from Quinlan Office Interiors Inc",
                "invoices@quinlan-interiors.example",
                "Fri, 04 Sep 2026 16:55:00 +0000",
                "Document titled invoice but it is a refund credit.",
                """
Quinlan Office Interiors Inc.
DOCUMENT QI-4408-C
Looks like our invoice layout on purpose — same letterhead.

Type: CREDIT / REFUND CONFIRMATION
Original invoice QI-4408
Refund amount: $1,200.00 USD
Reason: over-deposit returned

A bold line at the bottom: NOT PAYABLE — CREDIT ONLY
There is no due date because nothing is due.
If you treat this as an invoice you will double-pay a refund.
""",
            ),
        ),
    ]
    for ambiguous, email in credits:
        out.append(EvalHardCase("credit_note", ambiguous, email))

    # --- 3 personal / non-business ---
    personal = [
        _mail(
            95,
            "Team lunch next Friday?",
            "alex@company.example",
            "Wed, 08 Jul 2026 15:22:00 +0000",
            "Want to grab lunch with the team next Friday?",
            "Want to grab lunch with the team next Friday? No rush either way. I'll get the usual sandwiches unless you say otherwise.\n",
        ),
        _mail(
            96,
            "Keys are under the mat",
            "sam@friends.example",
            "Thu, 09 Jul 2026 19:03:00 +0000",
            "Come by any time after 6.",
            "Hey — I'll be out. Keys under the mat. Dog is with Jordan. Not work, not a bill.\n",
        ),
        _mail(
            97,
            "Happy birthday",
            "chris@personal.example",
            "Fri, 10 Jul 2026 08:01:00 +0000",
            "Hope it's a good one.",
            "Happy birthday. Dinner is on me this weekend — I already paid the restaurant. You don't owe me anything.\n",
        ),
    ]
    for email in personal:
        out.append(EvalHardCase("personal", False, email))

    # --- 3 non-English invoices ---
    non_en = [
        _mail(
            98,
            "Rechnung RE-2026-081 — Müller Bürotechnik GmbH",
            "buchhaltung@mueller-buerotechnik.example",
            "Mon, 11 Aug 2026 07:30:00 +0000",
            "Rechnung RE-2026-081, 1.890,40 EUR, fällig 12.09.2026.",
            """
Müller Bürotechnik GmbH
RECHNUNG

Rechnungsnummer: RE-2026-081
Lieferant: Müller Bürotechnik GmbH
Betrag fällig: 1.890,40 EUR
Fälligkeitsdatum: 12.09.2026

Bitte überweisen Sie den Betrag unter Angabe der Rechnungsnummer.
""",
        ),
        _mail(
            99,
            "Facture FA/2026/118 — Atelier Dupont SARL",
            "compta@atelier-dupont.example",
            "Tue, 12 Aug 2026 08:30:00 +0000",
            "Facture FA/2026/118, 640,00 EUR, échéance 3 septembre 2026.",
            """
Atelier Dupont SARL
FACTURE

Numéro de facture: FA/2026/118
Fournisseur: Atelier Dupont SARL
Montant dû: 640,00 EUR
Date d'échéance: 3 septembre 2026

Merci de régler par virement.
""",
        ),
        _mail(
            100,
            "Factura 2026-B-44 — Talleres Rivera S.L.",
            "facturacion@talleres-rivera.example",
            "Wed, 13 Aug 2026 09:30:00 +0000",
            "Factura 2026-B-44, 2.175,50 EUR, vencimiento 18/08/2026.",
            """
Talleres Rivera S.L.
FACTURA

Número de factura: 2026-B-44
Proveedor: Talleres Rivera S.L.
Importe a pagar: 2.175,50 EUR
Vencimiento: 18/08/2026

Forma de pago: transferencia bancaria.
""",
        ),
    ]
    for email in non_en:
        out.append(EvalHardCase("non_english", False, email))

    return out


EVAL_HARD_CASES: list[EvalHardCase] = _cases()


def validate_eval_hard_cases() -> None:
    if len(EVAL_HARD_CASES) != 100:
        raise RuntimeError(f"expected 100 cases, got {len(EVAL_HARD_CASES)}")
    counts = Counter(case.bucket for case in EVAL_HARD_CASES)
    if dict(counts) != EXPECTED_BUCKETS:
        raise RuntimeError(f"bucket mix mismatch: {dict(counts)}")
    n_amb = sum(1 for case in EVAL_HARD_CASES if case.ambiguous)
    if n_amb != 10:
        raise RuntimeError(f"expected 10 ambiguous cases, got {n_amb}")
    ids = [case.email.id for case in EVAL_HARD_CASES]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate email ids")


validate_eval_hard_cases()

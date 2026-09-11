"""100 expense claims with ground truth known by construction.

Each case is generated from an intended outcome, then labelled by the same
deterministic rule engine the tools read. The agent never sees the label.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from invoice_agent.adjudicator_fixtures import (
    AS_OF_DATE,
    claim_fingerprint,
    ground_truth_for,
    register_fingerprint,
)
from invoice_agent.types import Adjudication, ExpenseClaim, ExpenseLineItem

EXPECTED_BUCKETS = {
    "approve": 16,
    "partial": 14,
    "reject": 14,
    "fx": 14,
    "escalate": 12,
    "ambiguous": 14,
    "adversarial": 16,
}


@dataclass(frozen=True)
class AdjudicatorCase:
    bucket: str
    claim: ExpenseClaim
    expected: Adjudication


def _receipt(merchant: str, amount: float, currency: str, when: str) -> str:
    return (
        f"{merchant}\nDate: {when}\n"
        f"Item: as described\n"
        f"Total: {currency} {amount:.2f}\n"
        f"Paid by card\n"
    )


def _claim(
    *,
    n: int,
    claim_id: str | None = None,
    submitter_id: str,
    submitter_name: str,
    category: str,
    region: str,
    merchant: str,
    claim_date: str | None,
    claimed_amount: float,
    claim_currency: str,
    reporting_currency: str,
    receipt_amount: float | None,
    notes: str,
    units: int | None = None,
    submitted_at: str = AS_OF_DATE,
    line_desc: str = "Expense",
) -> ExpenseClaim:
    receipt = None
    if receipt_amount is not None and claim_date:
        receipt = _receipt(merchant, receipt_amount, claim_currency, claim_date)
    return ExpenseClaim(
        claim_id=claim_id or f"CLM-{n:04d}",
        submitter_id=submitter_id,
        submitter_name=submitter_name,
        category=category,
        region=region,
        merchant=merchant,
        claim_date=claim_date,
        submitted_at=submitted_at,
        units=units,
        claimed_amount=claimed_amount,
        claim_currency=claim_currency,
        reporting_currency=reporting_currency,
        receipt_text=receipt,
        notes=notes,
        line_items=[
            ExpenseLineItem(
                description=line_desc,
                amount=claimed_amount,
                currency=claim_currency,
            )
        ],
    )


def _labelled(
    bucket: str,
    claim: ExpenseClaim,
    *,
    confidence: float,
    rationale: str,
    expect_decision: str | None = None,
) -> AdjudicatorCase:
    expected = ground_truth_for(claim, confidence=confidence, rationale=rationale)
    if expect_decision is not None and expected.decision != expect_decision:
        raise RuntimeError(
            f"{claim.claim_id} ({bucket}): expected decision {expect_decision}, "
            f"rule engine produced {expected.decision}"
        )
    return AdjudicatorCase(bucket=bucket, claim=claim, expected=expected)


def _cases() -> list[AdjudicatorCase]:
    out: list[AdjudicatorCase] = []
    n = 1

    # --- 16 clean approvals within cap ---
    approve_specs = [
        ("emp-clean-00", "Asha Cole", "travel", "US", "Northpeak Air", "2026-07-12", 280.00, "USD", "USD", "Return flight SFO-SEA"),
        ("emp-clean-01", "Ben Ortiz", "travel", "UK", "Helios Rail", "2026-06-03", 190.00, "GBP", "GBP", "Advance-purchase rail"),
        ("emp-clean-02", "Cara Nguyen", "travel", "EU", "Vesper Airways", "2026-07-20", 240.00, "EUR", "EUR", "Intra-EU hop"),
        ("emp-clean-03", "Dev Patel", "office", "US", "Quinlan Stationery", "2026-08-01", 48.20, "USD", "USD", "Printer paper and toner"),
        ("emp-clean-04", "Elena Frost", "office", "UK", "Bramble Office Ltd", "2026-07-18", 62.00, "GBP", "GBP", "Desk organisers"),
        ("emp-clean-05", "Farid Hassan", "mileage", "US", "Personal vehicle", "2026-06-22", 126.40, "USD", "USD", "Client site mileage"),
        ("emp-clean-06", "Gita Shah", "training", "US", "Oakline Press Workshop", "2026-07-09", 890.00, "USD", "USD", "One-day SQL workshop"),
        ("emp-clean-07", "Hugo Berg", "training", "UK", "Wicker Finch CLE", "2026-07-13", 640.00, "GBP", "GBP", "Compliance seminar"),
        ("emp-clean-08", "Ines Rossi", "entertainment", "US", "Harborline Bistro", "2026-07-07", 118.50, "USD", "USD", "Client dinner, 2 attendees"),
        ("emp-clean-09", "Jules Adeyemi", "meals", "US", "Pebble Path Deli", "2026-08-04", 54.00, "USD", "USD", "Field lunch", 1),
        ("emp-clean-10", "Kai Mori", "meals", "UK", "Thornfield Cafe", "2026-07-29", 42.00, "GBP", "GBP", "Onsite lunch", 1),
        ("emp-clean-11", "Lina Kovacs", "lodging", "US", "Maple Court Inn", "2026-06-11", 198.00, "USD", "USD", "One night near site", 1),
        ("emp-clean-12", "Marco Silva", "lodging", "EU", "Atelier Dupont Hotel", "2026-07-16", 175.00, "EUR", "EUR", "One night Lyon", 1),
        ("emp-clean-13", "Nora Blake", "travel", "APAC", "Sequoia Pacific Air", "2026-07-17", 310.00, "USD", "USD", "SIN-HKG return"),
        ("emp-clean-14", "Omar Reed", "training", "EU", "Muller Buerotechnik Kurs", "2026-07-08", 720.00, "EUR", "EUR", "Equipment safety course"),
        ("emp-clean-15", "Priya Nair", "office", "US", "Ironclad Hardware", "2026-08-10", 33.75, "USD", "USD", "Cable pack"),
    ]
    for spec in approve_specs:
        units = spec[10] if len(spec) > 10 else None
        (
            sid, name, cat, region, merchant, cdate, amount, ccy, rep, note
        ) = spec[:10]
        claim = _claim(
            n=n,
            submitter_id=sid,
            submitter_name=name,
            category=cat,
            region=region,
            merchant=merchant,
            claim_date=cdate,
            claimed_amount=amount,
            claim_currency=ccy,
            reporting_currency=rep,
            receipt_amount=amount,
            notes=note,
            units=units,
        )
        out.append(
            _labelled(
                "approve",
                claim,
                confidence=0.93 + (n % 5) * 0.01,
                rationale=f"Within cap under the applicable {cat} clause; receipt present.",
                expect_decision="approve",
            )
        )
        n += 1

    # --- 14 partial (cap or pro-rate) ---
    partial_specs = [
        ("emp-clean-00", "Asha Cole", "travel", "US", "Atlas Crane Air", "2026-07-02", 520.00, "USD", "USD", None, "Coach fare over the per-claim cap"),
        ("emp-clean-01", "Ben Ortiz", "travel", "UK", "Nightowl Air Ltd", "2026-06-16", 410.00, "GBP", "GBP", None, "Peak-fare ticket over TRV-11 cap"),
        ("emp-clean-02", "Cara Nguyen", "lodging", "US", "Cinderblock Suites", "2026-07-19", 960.00, "USD", "USD", 3, "3 nights above $250/night"),
        ("emp-clean-03", "Dev Patel", "lodging", "UK", "Sandbar Hotel", "2026-07-27", 720.00, "GBP", "GBP", 3, "3 nights above £180/night"),
        ("emp-clean-04", "Elena Frost", "lodging", "EU", "Rivera Pensio", "2026-07-23", 900.00, "EUR", "EUR", 4, "4 nights above €200/night"),
        ("emp-clean-05", "Farid Hassan", "meals", "US", "Ambergrain Kitchen", "2026-07-21", 310.00, "USD", "USD", 3, "3-day per-diem exceeded"),
        ("emp-clean-06", "Gita Shah", "meals", "UK", "Boreal Canteen", "2026-06-08", 240.00, "GBP", "GBP", 3, "3-day UK meal cap exceeded"),
        ("emp-clean-07", "Hugo Berg", "meals", "EU", "Dupont Brasserie", "2026-07-24", 280.00, "EUR", "EUR", 3, "3-day EU meal cap exceeded"),
        ("emp-clean-08", "Ines Rossi", "entertainment", "US", "Driftwood Events", "2026-07-15", 240.00, "USD", "USD", None, "Client event over ENT-05 cap"),
        ("emp-clean-09", "Jules Adeyemi", "entertainment", "UK", "Harcourt Club", "2026-07-25", 190.00, "GBP", "GBP", None, "Client lunch over ENT-15"),
        ("emp-clean-10", "Kai Mori", "office", "US", "Lumen Display Co", "2026-08-02", 275.00, "USD", "USD", None, "Monitor stand over office cap"),
        ("emp-clean-11", "Lina Kovacs", "office", "UK", "Sable Print Ltd", "2026-07-09", 210.00, "GBP", "GBP", None, "Print job over OFF-18 cap"),
        ("emp-clean-12", "Marco Silva", "mileage", "US", "Personal vehicle", "2026-07-04", 388.00, "USD", "USD", None, "Long drive over mileage cap"),
        ("emp-clean-13", "Nora Blake", "travel", "APAC", "Glacier Pacific", "2026-07-22", 610.00, "USD", "USD", None, "APAC fare over TRV-30"),
    ]
    for spec in partial_specs:
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, units, note = spec
        claim = _claim(
            n=n,
            submitter_id=sid,
            submitter_name=name,
            category=cat,
            region=region,
            merchant=merchant,
            claim_date=cdate,
            claimed_amount=amount,
            claim_currency=ccy,
            reporting_currency=rep,
            receipt_amount=amount,
            notes=note,
            units=units,
        )
        out.append(
            _labelled(
                "partial",
                claim,
                confidence=0.82 + (n % 6) * 0.01,
                rationale="Claim exceeds the clause cap; approve only the capped amount.",
                expect_decision="partial",
            )
        )
        n += 1

    # --- 14 rejections: gifts, missing receipt, stale ---
    gift_specs = [
        ("emp-clean-00", "Asha Cole", "gifts", "US", "Yarrow Botanicals", "2026-07-03", 86.00, "USD", "USD", "Client gift basket"),
        ("emp-clean-01", "Ben Ortiz", "gifts", "UK", "Thornfield Uniforms", "2026-06-19", 55.00, "GBP", "GBP", "Branded hoodie for a vendor"),
        ("emp-clean-02", "Cara Nguyen", "gifts", "EU", "Atelier Dupont Boutique", "2026-05-08", 120.00, "EUR", "EUR", "Thank-you hamper"),
        ("emp-clean-03", "Dev Patel", "gifts", "US", "Pixelbarn Creative", "2026-08-05", 40.00, "USD", "USD", "Gift card for intern"),
        ("emp-clean-04", "Elena Frost", "gifts", "UK", "Paperplane Gifts Ltd", "2026-04-30", 28.00, "GBP", "GBP", "Flowers for a partner"),
    ]
    for spec in gift_specs:
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, note = spec
        claim = _claim(
            n=n,
            submitter_id=sid,
            submitter_name=name,
            category=cat,
            region=region,
            merchant=merchant,
            claim_date=cdate,
            claimed_amount=amount,
            claim_currency=ccy,
            reporting_currency=rep,
            receipt_amount=amount,
            notes=note,
        )
        out.append(
            _labelled(
                "reject",
                claim,
                confidence=0.94 + (n % 3) * 0.01,
                rationale="Gifts are out of policy; the cited clause is not reimbursable.",
                expect_decision="reject",
            )
        )
        n += 1

    missing_receipt = [
        ("emp-clean-05", "Farid Hassan", "travel", "US", "Redline Shuttle", "2026-07-11", 88.00, "USD", "USD", "Airport transfer, receipt lost"),
        ("emp-clean-06", "Gita Shah", "lodging", "US", "Voltara Motel", "2026-06-01", 210.00, "USD", "USD", "One night, no folio attached", 1),
        ("emp-clean-07", "Hugo Berg", "meals", "UK", "Copperline Canteen", "2026-07-16", 38.00, "GBP", "GBP", "Team lunch, no itemised bill", 1),
        ("emp-clean-08", "Ines Rossi", "training", "US", "Brightforge Academy", "2026-07-26", 450.00, "USD", "USD", "Course fee, certificate only"),
        ("emp-clean-09", "Jules Adeyemi", "entertainment", "US", "Nimbus Lounge", "2026-07-28", 95.00, "USD", "USD", "Client drinks, no receipt"),
    ]
    for spec in missing_receipt:
        units = spec[10] if len(spec) > 10 else None
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, note = spec[:10]
        claim = _claim(
            n=n,
            submitter_id=sid,
            submitter_name=name,
            category=cat,
            region=region,
            merchant=merchant,
            claim_date=cdate,
            claimed_amount=amount,
            claim_currency=ccy,
            reporting_currency=rep,
            receipt_amount=None,
            notes=note,
            units=units,
        )
        out.append(
            _labelled(
                "reject",
                claim,
                confidence=0.91 + (n % 4) * 0.01,
                rationale="Policy requires a receipt and none was attached.",
                expect_decision="reject",
            )
        )
        n += 1

    stale = [
        ("emp-clean-10", "Kai Mori", "travel", "US", "Fieldnote Air", "2025-12-01", 210.00, "USD", "USD", "Late-filed December trip"),
        ("emp-clean-11", "Lina Kovacs", "office", "US", "Holloway Keys", "2025-11-02", 44.00, "USD", "USD", "Locksmith visit, filed late"),
        ("emp-clean-12", "Marco Silva", "meals", "EU", "Rivera Tapas", "2025-10-15", 58.00, "EUR", "EUR", "Old meal claim", 1),
        ("emp-clean-13", "Nora Blake", "entertainment", "US", "Solstice Bar", "2026-01-10", 70.00, "USD", "USD", "Entertainment filed past 60 days"),
    ]
    for spec in stale:
        units = spec[10] if len(spec) > 10 else None
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, note = spec[:10]
        claim = _claim(
            n=n,
            submitter_id=sid,
            submitter_name=name,
            category=cat,
            region=region,
            merchant=merchant,
            claim_date=cdate,
            claimed_amount=amount,
            claim_currency=ccy,
            reporting_currency=rep,
            receipt_amount=amount,
            notes=note,
            units=units,
        )
        out.append(
            _labelled(
                "reject",
                claim,
                confidence=0.90 + (n % 3) * 0.01,
                rationale="Claim date is older than the clause stale window.",
                expect_decision="reject",
            )
        )
        n += 1

    # --- 14 FX (4 same-currency rate 1.0, 10 convert) ---
    fx_same = [
        ("emp-clean-14", "Omar Reed", "travel", "US", "Cascadia Air", "2026-08-08", 199.00, "USD", "USD", "Domestic fare, already USD"),
        ("emp-clean-15", "Priya Nair", "office", "UK", "Moss Pine Joinery", "2026-07-14", 88.00, "GBP", "GBP", "Nameplate, already GBP"),
        ("emp-risk-00", "Quinn Walsh", "meals", "EU", "Dupont Cafe", "2026-06-06", 44.00, "EUR", "EUR", "Lunch, already EUR", 1),
        ("emp-risk-01", "Ravi Mehta", "training", "US", "Apex Advisory Class", "2026-07-05", 500.00, "USD", "USD", "Internal workshop, USD"),
    ]
    for spec in fx_same:
        units = spec[10] if len(spec) > 10 else None
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, note = spec[:10]
        claim = _claim(
            n=n,
            submitter_id=sid,
            submitter_name=name,
            category=cat,
            region=region,
            merchant=merchant,
            claim_date=cdate,
            claimed_amount=amount,
            claim_currency=ccy,
            reporting_currency=rep,
            receipt_amount=amount,
            notes=note,
            units=units,
        )
        labelled = _labelled(
            "fx",
            claim,
            confidence=0.88 + (n % 4) * 0.01,
            rationale="Claim currency matches reporting currency; FX rate is 1.0.",
        )
        if labelled.expected.fx_rate_used != 1.0:
            raise RuntimeError(f"{claim.claim_id}: expected fx_rate_used 1.0")
        out.append(labelled)
        n += 1

    fx_convert = [
        ("emp-risk-02", "Sara Klein", "travel", "US", "Lufthansa", "2026-07-15", 200.00, "EUR", "USD", "EUR ticket, report USD"),
        ("emp-risk-03", "Tom Ikeda", "travel", "US", "British Airways", "2026-08-03", 180.00, "GBP", "USD", "GBP ticket, report USD"),
        ("emp-risk-04", "Uma Shah", "office", "US", "Muji Singapore", "2026-08-09", 90.00, "SGD", "USD", "Notebooks bought in SGD"),
        ("emp-risk-05", "Viktor Holm", "meals", "US", "Toronto Deli", "2026-07-18", 60.00, "CAD", "USD", "Airport meal in CAD", 1),
        ("emp-risk-06", "Willa Chen", "training", "US", "Sydney Conf Co", "2026-07-20", 400.00, "AUD", "USD", "Conference in AUD"),
        ("emp-risk-07", "Xander Cole", "office", "US", "Tokyo Station Kiosk", "2026-07-06", 8000.00, "JPY", "USD", "Office stamps in JPY"),
        ("emp-risk-08", "Yara Mensah", "travel", "UK", "SNCF", "2026-08-04", 150.00, "EUR", "GBP", "Eurostar paid in EUR"),
        ("emp-risk-09", "Zed Park", "lodging", "US", "Paris Inn", "2026-08-06", 180.00, "EUR", "USD", "One night EUR folio", 1),
        ("emp-clean-00", "Asha Cole", "travel", "US", "Qantas", "2026-08-01", 220.00, "AUD", "USD", "AUD fare under USD cap"),
        ("emp-clean-01", "Ben Ortiz", "office", "UK", "Berlin Stationery", "2026-07-22", 40.00, "EUR", "GBP", "EUR stationery, UK books"),
    ]
    for spec in fx_convert:
        units = spec[10] if len(spec) > 10 else None
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, note = spec[:10]
        claim = _claim(
            n=n,
            submitter_id=sid,
            submitter_name=name,
            category=cat,
            region=region,
            merchant=merchant,
            claim_date=cdate,
            claimed_amount=amount,
            claim_currency=ccy,
            reporting_currency=rep,
            receipt_amount=amount,
            notes=note,
            units=units,
        )
        labelled = _labelled(
            "fx",
            claim,
            confidence=0.84 + (n % 5) * 0.01,
            rationale="Converted at the fixture FX rate for the claim month.",
        )
        if labelled.expected.fx_rate_used in (None, 1.0):
            raise RuntimeError(f"{claim.claim_id}: expected a non-1 FX rate")
        if labelled.expected.decision not in {"approve", "partial"}:
            raise RuntimeError(
                f"{claim.claim_id}: fx convert produced {labelled.expected.decision}"
            )
        out.append(labelled)
        n += 1

    # --- 12 escalations from submitter history ---
    for i in range(12):
        sid = f"emp-viol-{i % 10:02d}"
        name = f"Violator {i:02d}"
        claim = _claim(
            n=n,
            submitter_id=sid,
            submitter_name=name,
            category="travel",
            region="US",
            merchant=f"Escalair {i:02d}",
            claim_date=f"2026-06-{(i % 27) + 1:02d}",
            claimed_amount=150.00 + i * 7,
            claim_currency="USD",
            reporting_currency="USD",
            receipt_amount=150.00 + i * 7,
            notes="Otherwise ordinary travel; submitter has repeated violations.",
        )
        out.append(
            _labelled(
                "escalate",
                claim,
                confidence=0.78 + (i % 8) * 0.01,
                rationale="Submitter history has enough prior violations to escalate.",
                expect_decision="escalate",
            )
        )
        n += 1

    # --- 14 ambiguous: nulls + lower confidence ---
    templates = [
        ("unknown_category", "misc", "US", "Kiosk {i}", "2026-07-01", 25.0 + i, "USD", "USD", None, None),
        ("unknown_region", "travel", "LATAM", "Andes Air {i}", "2026-06-12", 200.0 + i, "USD", "USD", 200.0 + i, None),
        ("missing_date", "travel", "US", "No-date Air {i}", None, 160.0 + i, "USD", "USD", None, None),
        ("missing_units", "lodging", "US", "No-nights Inn {i}", "2026-07-28", 380.0 + i, "USD", "USD", 380.0 + i, None),
    ]
    # 14 rows: 4 templates * 3 + 2 extra unknown_category = 14
    amb_i = 0
    while len([c for c in out if c.bucket == "ambiguous"]) < 14:
        kind, cat, region, merchant_t, cdate, amount, ccy, rep, receipt_amt, units = templates[amb_i % 4]
        i = amb_i
        claim = _claim(
            n=n,
            submitter_id=f"emp-clean-{i % 16:02d}",
            submitter_name=f"Ambiguous {i:02d}",
            category=cat,
            region=region,
            merchant=merchant_t.format(i=i),
            claim_date=cdate,
            claimed_amount=float(amount),
            claim_currency=ccy,
            reporting_currency=rep,
            receipt_amount=receipt_amt,
            notes=f"Ambiguous: {kind}. Do not invent a clause.",
            units=units,
        )
        # missing receipt on meals/lodging that require it would reject, not escalate.
        # unknown category/region/date/units should escalate.
        labelled = _labelled(
            "ambiguous",
            claim,
            confidence=0.38 + (i % 7) * 0.03,
            rationale="Not enough to apply a single clause; escalate with null identifiers.",
            expect_decision="escalate",
        )
        if labelled.expected.policy_clause is not None and kind in {
            "unknown_category",
            "unknown_region",
            "missing_date",
        }:
            raise RuntimeError(f"{claim.claim_id}: ambiguous case got a clause")
        out.append(labelled)
        n += 1
        amb_i += 1

    # --- 16 adversarial ---
    # receipt mismatch
    for i in range(6):
        claimed = 400.00 + i * 25
        receipt_amt = 42.00 + i
        claim = _claim(
            n=n,
            submitter_id=f"emp-clean-{i:02d}",
            submitter_name=f"Mismatch {i:02d}",
            category="travel",
            region="US",
            merchant=f"Splitfare Air {i:02d}",
            claim_date=f"2026-07-{(i % 20) + 1:02d}",
            claimed_amount=claimed,
            claim_currency="USD",
            reporting_currency="USD",
            receipt_amount=receipt_amt,
            notes="Receipt total does not match the amount claimed.",
        )
        out.append(
            _labelled(
                "adversarial",
                claim,
                confidence=0.80 + (i % 5) * 0.01,
                rationale="Receipt total differs from the claimed amount.",
                expect_decision="reject",
            )
        )
        n += 1

    # merchant looks like training / travel but category is meals/office
    merchant_traps = [
        ("Training Wheels Cafe", "meals", "US", "MEL-ish cafe, category is meals", 36.00, "USD", 1),
        ("Travelodge Sandwich Bar", "meals", "UK", "Name looks like lodging; category meals", 18.00, "GBP", 1),
        ("Mileage Coffee Co", "meals", "US", "Name looks like mileage; category meals", 12.50, "USD", 1),
        ("Gifts & Grains Deli", "meals", "US", "Name looks like gifts; category meals", 22.00, "USD", 1),
        ("Office Party Balloons? No — Staples", "office", "US", "Office supplies, not a party", 19.99, "USD", None),
    ]
    for i, spec in enumerate(merchant_traps):
        merchant, cat, region, note, amount, ccy, units = spec
        claim = _claim(
            n=n,
            submitter_id=f"emp-risk-{i:02d}",
            submitter_name=f"Trap {i:02d}",
            category=cat,
            region=region,
            merchant=merchant,
            claim_date=f"2026-06-{(i % 20) + 2:02d}",
            claimed_amount=amount,
            claim_currency=ccy,
            reporting_currency=ccy,
            receipt_amount=amount,
            notes=note,
            units=units,
        )
        labelled = _labelled(
            "adversarial",
            claim,
            confidence=0.74 + i * 0.02,
            rationale="Apply the stated category, not the merchant's misleading name.",
            expect_decision="approve",
        )
        out.append(labelled)
        n += 1

    # duplicates: register fingerprint first, then file the same claim
    for i in range(5):
        sid = f"emp-dup-{i:02d}"
        merchant = f"Repeat Vendor {i:02d}"
        cdate = f"2026-05-{(i % 20) + 3:02d}"
        amount = 110.00 + i * 8
        fp = claim_fingerprint(merchant, cdate, amount)
        register_fingerprint(sid, fp)
        claim = _claim(
            n=n,
            submitter_id=sid,
            submitter_name=f"Dup {i:02d}",
            category="office",
            region="US",
            merchant=merchant,
            claim_date=cdate,
            claimed_amount=amount,
            claim_currency="USD",
            reporting_currency="USD",
            receipt_amount=amount,
            notes="Resubmission of an earlier claim with the same merchant/date/amount.",
        )
        out.append(
            _labelled(
                "adversarial",
                claim,
                confidence=0.76 + i * 0.02,
                rationale="Fingerprint matches a prior claim on this submitter; escalate.",
                expect_decision="escalate",
            )
        )
        n += 1

    return out


ADJUDICATOR_CASES: list[AdjudicatorCase] = _cases()


def validate_adjudicator_cases() -> None:
    if len(ADJUDICATOR_CASES) != 100:
        raise RuntimeError(f"expected 100 cases, got {len(ADJUDICATOR_CASES)}")
    counts = Counter(case.bucket for case in ADJUDICATOR_CASES)
    if dict(counts) != EXPECTED_BUCKETS:
        raise RuntimeError(f"bucket mix mismatch: {dict(counts)}")
    ids = [case.claim.claim_id for case in ADJUDICATOR_CASES]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate claim ids")
    confs = [case.expected.confidence for case in ADJUDICATOR_CASES]
    if min(confs) >= 0.8 or max(confs) <= 0.9:
        raise RuntimeError("constructed confidence does not spread")
    decisions = {case.expected.decision for case in ADJUDICATOR_CASES}
    if decisions != {"approve", "partial", "reject", "escalate"}:
        raise RuntimeError(f"missing decisions: {decisions}")


validate_adjudicator_cases()

"""Eval corpus: 100 new claims, same task mix as train, disjoint instances.

Labels come from ground_truth_for at construction time. The agent must not
import this module (or ground_truth_for) at runtime.
"""

from __future__ import annotations

from collections import Counter

from invoice_agent.adjudicator_claims import (
    ADJUDICATOR_CASES,
    EXPECTED_BUCKETS,
    AdjudicatorCase,
    _claim,
    _labelled,
)
from invoice_agent.adjudicator_fixtures import claim_fingerprint, register_fingerprint


def _eval_claim(**kwargs) -> object:
    n = kwargs["n"]
    kwargs.setdefault("claim_id", f"CLM-E-{n:04d}")
    return _claim(**kwargs)


def _cases() -> list[AdjudicatorCase]:
    out: list[AdjudicatorCase] = []
    n = 1

    approve_specs = [
        ("eval-clean-00", "Renee Walsh", "travel", "US", "Cedarline Air", "2026-07-14", 265.00, "USD", "USD", "Return flight DEN-SEA"),
        ("eval-clean-01", "Samir Haddad", "travel", "UK", "Thameslink Rail Co", "2026-06-05", 175.00, "GBP", "GBP", "Off-peak rail"),
        ("eval-clean-02", "Tessa Vogel", "travel", "EU", "Alpen Wings", "2026-07-18", 255.00, "EUR", "EUR", "Intra-EU hop"),
        ("eval-clean-03", "Ulysses Grant Jr", "office", "US", "Pylon Stationery", "2026-08-03", 41.80, "USD", "USD", "Toner and clips"),
        ("eval-clean-04", "Vera Okonkwo", "office", "UK", "Quill & Nib Ltd", "2026-07-21", 71.00, "GBP", "GBP", "Notebooks"),
        ("eval-clean-05", "Wes Park", "mileage", "US", "Personal car", "2026-06-24", 118.20, "USD", "USD", "Customer site mileage"),
        ("eval-clean-06", "Xena Brooks", "training", "US", "Riverbend Workshop", "2026-07-11", 820.00, "USD", "USD", "One-day Python workshop"),
        ("eval-clean-07", "Yuri Petrov", "training", "UK", "Innsbrook CLE", "2026-07-15", 610.00, "GBP", "GBP", "Ethics seminar"),
        ("eval-clean-08", "Zara Mensah", "entertainment", "US", "Dockside Grill", "2026-07-09", 109.25, "USD", "USD", "Client dinner, 2 attendees"),
        ("eval-clean-09", "Aiden Cho", "meals", "US", "Cinder Deli", "2026-08-06", 61.00, "USD", "USD", "Field lunch", 1),
        ("eval-clean-10", "Blythe Kerr", "meals", "UK", "Lantern Cafe", "2026-07-31", 39.00, "GBP", "GBP", "Onsite lunch", 1),
        ("eval-clean-11", "Cormac Lee", "lodging", "US", "Pinecrest Inn", "2026-06-13", 210.00, "USD", "USD", "One night near site", 1),
        ("eval-clean-12", "Dina Rossi", "lodging", "EU", "Hotel Sablon", "2026-07-18", 188.00, "EUR", "EUR", "One night Brussels", 1),
        ("eval-clean-13", "Eli Nakamura", "travel", "APAC", "Monsoon Pacific Air", "2026-07-19", 295.00, "USD", "USD", "SIN-NRT return"),
        ("eval-clean-14", "Faye Lindqvist", "training", "EU", "Kiefer Technik Kurs", "2026-07-10", 690.00, "EUR", "EUR", "Safety course"),
        ("eval-clean-15", "Gabe Santos", "office", "US", "Bolt & Bit Hardware", "2026-08-12", 27.40, "USD", "USD", "Cable pack"),
    ]
    for spec in approve_specs:
        units = spec[10] if len(spec) > 10 else None
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, note = spec[:10]
        claim = _eval_claim(
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

    partial_specs = [
        ("eval-clean-00", "Renee Walsh", "travel", "US", "Summit Hopper Air", "2026-07-04", 535.00, "USD", "USD", None, "Coach fare over the per-claim cap"),
        ("eval-clean-01", "Samir Haddad", "travel", "UK", "Gannet Air Ltd", "2026-06-18", 425.00, "GBP", "GBP", None, "Peak-fare ticket over TRV-11 cap"),
        ("eval-clean-02", "Tessa Vogel", "lodging", "US", "Keystone Suites", "2026-07-21", 980.00, "USD", "USD", 3, "3 nights above $250/night"),
        ("eval-clean-03", "Ulysses Grant Jr", "lodging", "UK", "Quayside Hotel", "2026-07-29", 740.00, "GBP", "GBP", 3, "3 nights above £180/night"),
        ("eval-clean-04", "Vera Okonkwo", "lodging", "EU", "Pension Adler", "2026-07-25", 920.00, "EUR", "EUR", 4, "4 nights above €200/night"),
        ("eval-clean-05", "Wes Park", "meals", "US", "Copper Pan Kitchen", "2026-07-23", 325.00, "USD", "USD", 3, "3-day per-diem exceeded"),
        ("eval-clean-06", "Xena Brooks", "meals", "UK", "Wren Canteen", "2026-06-10", 250.00, "GBP", "GBP", 3, "3-day UK meal cap exceeded"),
        ("eval-clean-07", "Yuri Petrov", "meals", "EU", "Brasserie Senne", "2026-07-26", 295.00, "EUR", "EUR", 3, "3-day EU meal cap exceeded"),
        ("eval-clean-08", "Zara Mensah", "entertainment", "US", "Lantern Events", "2026-07-17", 255.00, "USD", "USD", None, "Client event over ENT-05 cap"),
        ("eval-clean-09", "Aiden Cho", "entertainment", "UK", "Ashford Club", "2026-07-27", 205.00, "GBP", "GBP", None, "Client lunch over ENT-15"),
        ("eval-clean-10", "Blythe Kerr", "office", "US", "Halo Display Co", "2026-08-04", 288.00, "USD", "USD", None, "Monitor stand over office cap"),
        ("eval-clean-11", "Cormac Lee", "office", "UK", "Inkstone Print Ltd", "2026-07-11", 225.00, "GBP", "GBP", None, "Print job over OFF-18 cap"),
        ("eval-clean-12", "Dina Rossi", "mileage", "US", "Personal car", "2026-07-06", 401.00, "USD", "USD", None, "Long drive over mileage cap"),
        ("eval-clean-13", "Eli Nakamura", "travel", "APAC", "Typhoon Pacific", "2026-07-24", 625.00, "USD", "USD", None, "APAC fare over TRV-30"),
    ]
    for spec in partial_specs:
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, units, note = spec
        claim = _eval_claim(
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

    gift_specs = [
        ("eval-clean-00", "Renee Walsh", "gifts", "US", "Fern & Petal", "2026-07-05", 79.00, "USD", "USD", "Client gift basket"),
        ("eval-clean-01", "Samir Haddad", "gifts", "UK", "Crestwell Apparel", "2026-06-21", 48.00, "GBP", "GBP", "Branded hoodie for a vendor"),
        ("eval-clean-02", "Tessa Vogel", "gifts", "EU", "Maison Sablon Boutique", "2026-07-08", 132.00, "EUR", "EUR", "Thank-you hamper"),
        ("eval-clean-03", "Ulysses Grant Jr", "gifts", "US", "Inkbird Creative", "2026-08-07", 35.00, "USD", "USD", "Gift card for intern"),
        ("eval-clean-04", "Vera Okonkwo", "gifts", "UK", "Kitebox Gifts Ltd", "2026-07-02", 31.00, "GBP", "GBP", "Flowers for a partner"),
    ]
    for spec in gift_specs:
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, note = spec
        claim = _eval_claim(
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
        ("eval-clean-05", "Wes Park", "travel", "US", "Metro Shuttle Co", "2026-07-13", 79.00, "USD", "USD", "Airport transfer, receipt lost"),
        ("eval-clean-06", "Xena Brooks", "lodging", "US", "Ridgeview Motel", "2026-06-03", 205.00, "USD", "USD", "One night, no folio attached", 1),
        ("eval-clean-07", "Yuri Petrov", "meals", "UK", "Wharf Canteen", "2026-07-18", 33.00, "GBP", "GBP", "Team lunch, no itemised bill", 1),
        ("eval-clean-08", "Zara Mensah", "training", "US", "Kiln Academy", "2026-07-28", 475.00, "USD", "USD", "Course fee, certificate only"),
        ("eval-clean-09", "Aiden Cho", "entertainment", "US", "Lowlight Lounge", "2026-07-30", 88.00, "USD", "USD", "Client drinks, no receipt"),
    ]
    for spec in missing_receipt:
        units = spec[10] if len(spec) > 10 else None
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, note = spec[:10]
        claim = _eval_claim(
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
        ("eval-clean-10", "Blythe Kerr", "travel", "US", "Prairie Air", "2025-12-03", 198.00, "USD", "USD", "Late-filed December trip"),
        ("eval-clean-11", "Cormac Lee", "office", "US", "Lockwright Keys", "2025-11-04", 39.00, "USD", "USD", "Locksmith visit, filed late"),
        ("eval-clean-12", "Dina Rossi", "meals", "EU", "Tapas Norte", "2025-10-17", 51.00, "EUR", "EUR", "Old meal claim", 1),
        ("eval-clean-13", "Eli Nakamura", "entertainment", "US", "Ember Bar", "2026-01-12", 64.00, "USD", "USD", "Entertainment filed past 60 days"),
    ]
    for spec in stale:
        units = spec[10] if len(spec) > 10 else None
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, note = spec[:10]
        claim = _eval_claim(
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

    fx_same = [
        ("eval-clean-14", "Faye Lindqvist", "travel", "US", "Redwood Air", "2026-08-10", 188.00, "USD", "USD", "Domestic fare, already USD"),
        ("eval-clean-15", "Gabe Santos", "office", "UK", "Ash Joinery Ltd", "2026-07-16", 79.00, "GBP", "GBP", "Nameplate, already GBP"),
        ("eval-risk-00", "Hana Iqbal", "meals", "EU", "Cafe Senne", "2026-06-08", 49.00, "EUR", "EUR", "Lunch, already EUR", 1),
        ("eval-risk-01", "Ivan Cole", "training", "US", "Northline Class", "2026-07-07", 480.00, "USD", "USD", "Internal workshop, USD"),
    ]
    for spec in fx_same:
        units = spec[10] if len(spec) > 10 else None
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, note = spec[:10]
        claim = _eval_claim(
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
        ("eval-risk-02", "Jade Kim", "travel", "US", "Iberia", "2026-07-17", 190.00, "EUR", "USD", "EUR ticket, report USD"),
        ("eval-risk-03", "Kofi Mensah", "travel", "US", "Virgin Atlantic", "2026-08-05", 170.00, "GBP", "USD", "GBP ticket, report USD"),
        ("eval-risk-04", "Lila Shah", "office", "US", "Kinokuniya SG", "2026-08-11", 82.00, "SGD", "USD", "Notebooks bought in SGD"),
        ("eval-risk-05", "Milo Berg", "meals", "US", "Montreal Deli", "2026-07-20", 55.00, "CAD", "USD", "Airport meal in CAD", 1),
        ("eval-risk-06", "Nadia Chen", "training", "US", "Melbourne Conf Co", "2026-07-22", 380.00, "AUD", "USD", "Conference in AUD"),
        ("eval-risk-07", "Oscar Diaz", "office", "US", "Osaka Station Kiosk", "2026-07-08", 9200.00, "JPY", "USD", "Office stamps in JPY"),
        ("eval-risk-08", "Pia Holm", "travel", "UK", "Thalys", "2026-08-06", 140.00, "EUR", "GBP", "Eurostar paid in EUR"),
        ("eval-risk-09", "Quinn Park", "lodging", "US", "Lille Inn", "2026-08-08", 165.00, "EUR", "USD", "One night EUR folio", 1),
        ("eval-clean-00", "Renee Walsh", "travel", "US", "Air New Zealand", "2026-08-03", 205.00, "AUD", "USD", "AUD fare under USD cap"),
        ("eval-clean-01", "Samir Haddad", "office", "UK", "Vienna Stationery", "2026-07-24", 36.00, "EUR", "GBP", "EUR stationery, UK books"),
    ]
    for spec in fx_convert:
        units = spec[10] if len(spec) > 10 else None
        sid, name, cat, region, merchant, cdate, amount, ccy, rep, note = spec[:10]
        claim = _eval_claim(
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

    for i in range(12):
        sid = f"eval-viol-{i % 10:02d}"
        name = f"Eval Violator {i:02d}"
        claim = _eval_claim(
            n=n,
            submitter_id=sid,
            submitter_name=name,
            category="travel",
            region="US",
            merchant=f"Flagline Air {i:02d}",
            claim_date=f"2026-06-{(i % 27) + 2:02d}",
            claimed_amount=162.00 + i * 7,
            claim_currency="USD",
            reporting_currency="USD",
            receipt_amount=162.00 + i * 7,
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

    templates = [
        ("unknown_category", "misc", "US", "Corner stall {i}", "2026-07-03", 28.0 + i, "USD", "USD", None, None),
        ("unknown_region", "travel", "LATAM", "Patagonia Air {i}", "2026-06-14", 215.0 + i, "USD", "USD", 215.0 + i, None),
        ("missing_date", "travel", "US", "Undated Air {i}", None, 171.0 + i, "USD", "USD", None, None),
        ("missing_units", "lodging", "US", "Blank-nights Inn {i}", "2026-07-30", 365.0 + i, "USD", "USD", 365.0 + i, None),
    ]
    amb_i = 0
    while len([c for c in out if c.bucket == "ambiguous"]) < 14:
        kind, cat, region, merchant_t, cdate, amount, ccy, rep, receipt_amt, units = templates[
            amb_i % 4
        ]
        i = amb_i
        claim = _eval_claim(
            n=n,
            submitter_id=f"eval-clean-{i % 16:02d}",
            submitter_name=f"Eval Ambiguous {i:02d}",
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

    for i in range(6):
        claimed = 415.00 + i * 25
        receipt_amt = 37.00 + i
        claim = _eval_claim(
            n=n,
            submitter_id=f"eval-clean-{i:02d}",
            submitter_name=f"Eval Mismatch {i:02d}",
            category="travel",
            region="US",
            merchant=f"Twinfare Air {i:02d}",
            claim_date=f"2026-07-{(i % 20) + 3:02d}",
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

    merchant_traps = [
        ("Workshop Wheels Cafe", "meals", "US", "Name looks like training; category is meals", 31.00, "USD", 1),
        ("Travelodge Soup Counter", "meals", "UK", "Name looks like lodging; category meals", 16.50, "GBP", 1),
        ("Odometer Coffee Co", "meals", "US", "Name looks like mileage; category meals", 11.25, "USD", 1),
        ("Presents & Pastries", "meals", "US", "Name looks like gifts; category meals", 19.40, "USD", 1),
        ("Party Depot? No — OfficeMax pens", "office", "US", "Office supplies, not a party", 17.49, "USD", None),
    ]
    for i, spec in enumerate(merchant_traps):
        merchant, cat, region, note, amount, ccy, units = spec
        claim = _eval_claim(
            n=n,
            submitter_id=f"eval-risk-{i:02d}",
            submitter_name=f"Eval Trap {i:02d}",
            category=cat,
            region=region,
            merchant=merchant,
            claim_date=f"2026-06-{(i % 20) + 4:02d}",
            claimed_amount=amount,
            claim_currency=ccy,
            reporting_currency=ccy,
            receipt_amount=amount,
            notes=note,
            units=units,
        )
        out.append(
            _labelled(
                "adversarial",
                claim,
                confidence=0.74 + i * 0.02,
                rationale="Apply the stated category, not the merchant's misleading name.",
                expect_decision="approve",
            )
        )
        n += 1

    for i in range(5):
        sid = f"eval-dup-{i:02d}"
        merchant = f"Replay Vendor {i:02d}"
        cdate = f"2026-05-{(i % 20) + 5:02d}"
        amount = 121.00 + i * 8
        fp = claim_fingerprint(merchant, cdate, amount)
        register_fingerprint(sid, fp)
        claim = _eval_claim(
            n=n,
            submitter_id=sid,
            submitter_name=f"Eval Dup {i:02d}",
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


def _collision_key(claim) -> tuple:
    return (
        claim.merchant.strip().lower(),
        claim.claim_date,
        round(float(claim.claimed_amount), 2),
        claim.submitter_id,
    )


ADJUDICATOR_EVAL_CASES: list[AdjudicatorCase] = _cases()


def validate_adjudicator_eval_cases() -> None:
    if len(ADJUDICATOR_EVAL_CASES) != 100:
        raise RuntimeError(f"expected 100 eval cases, got {len(ADJUDICATOR_EVAL_CASES)}")
    counts = Counter(case.bucket for case in ADJUDICATOR_EVAL_CASES)
    if dict(counts) != EXPECTED_BUCKETS:
        raise RuntimeError(f"eval bucket mix mismatch: {dict(counts)}")
    ids = [case.claim.claim_id for case in ADJUDICATOR_EVAL_CASES]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate eval claim ids")
    train_ids = {case.claim.claim_id for case in ADJUDICATOR_CASES}
    overlap_ids = train_ids.intersection(ids)
    if overlap_ids:
        raise RuntimeError(f"claim_id overlap with train: {sorted(overlap_ids)[:5]}")
    train_keys = {_collision_key(case.claim) for case in ADJUDICATOR_CASES}
    collisions = [
        _collision_key(case.claim)
        for case in ADJUDICATOR_EVAL_CASES
        if _collision_key(case.claim) in train_keys
    ]
    if collisions:
        raise RuntimeError(f"instance collision with train: {collisions[:3]}")
    confs = [case.expected.confidence for case in ADJUDICATOR_EVAL_CASES]
    if min(confs) >= 0.8 or max(confs) <= 0.9:
        raise RuntimeError("constructed eval confidence does not spread")
    decisions = {case.expected.decision for case in ADJUDICATOR_EVAL_CASES}
    if decisions != {"approve", "partial", "reject", "escalate"}:
        raise RuntimeError(f"missing eval decisions: {decisions}")


validate_adjudicator_eval_cases()

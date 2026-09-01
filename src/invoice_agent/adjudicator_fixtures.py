"""Deterministic fixture store for Ledgerline Adjudicator tools.

Same arguments always produce the same JSON-serializable dict. Nothing here
calls a live API — evaluation replays these outputs.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date

from invoice_agent.types import Adjudication, ExpenseClaim

# Company "today" for stale-claim math. Fixed so replays do not drift.
AS_OF_DATE = "2026-08-26"

# Cap unit: per_claim | per_day | per_night
POLICY_CLAUSES: list[dict] = [
    {
        "id": "TRV-03",
        "category": "travel",
        "region": "US",
        "effective_date": "2023-01-01",
        "cap_amount": 250.0,
        "cap_unit": "per_claim",
        "receipt_required": True,
        "stale_after_days": 60,
        "reimbursable": True,
        "reporting_currency": "USD",
    },
    {
        "id": "TRV-04",
        "category": "travel",
        "region": "US",
        "effective_date": "2025-01-01",
        "cap_amount": 400.0,
        "cap_unit": "per_claim",
        "receipt_required": True,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "USD",
    },
    {
        "id": "TRV-11",
        "category": "travel",
        "region": "UK",
        "effective_date": "2025-01-01",
        "cap_amount": 300.0,
        "cap_unit": "per_claim",
        "receipt_required": True,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "GBP",
    },
    {
        "id": "TRV-20",
        "category": "travel",
        "region": "EU",
        "effective_date": "2025-04-01",
        "cap_amount": 350.0,
        "cap_unit": "per_claim",
        "receipt_required": True,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "EUR",
    },
    {
        "id": "TRV-30",
        "category": "travel",
        "region": "APAC",
        "effective_date": "2025-01-01",
        "cap_amount": 450.0,
        "cap_unit": "per_claim",
        "receipt_required": True,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "USD",
    },
    {
        "id": "LDG-02",
        "category": "lodging",
        "region": "US",
        "effective_date": "2025-01-01",
        "cap_amount": 250.0,
        "cap_unit": "per_night",
        "receipt_required": True,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "USD",
    },
    {
        "id": "LDG-12",
        "category": "lodging",
        "region": "UK",
        "effective_date": "2025-01-01",
        "cap_amount": 180.0,
        "cap_unit": "per_night",
        "receipt_required": True,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "GBP",
    },
    {
        "id": "LDG-22",
        "category": "lodging",
        "region": "EU",
        "effective_date": "2025-01-01",
        "cap_amount": 200.0,
        "cap_unit": "per_night",
        "receipt_required": True,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "EUR",
    },
    {
        "id": "LDG-32",
        "category": "lodging",
        "region": "APAC",
        "effective_date": "2025-01-01",
        "cap_amount": 220.0,
        "cap_unit": "per_night",
        "receipt_required": True,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "USD",
    },
    {
        "id": "MEL-01",
        "category": "meals",
        "region": "US",
        "effective_date": "2025-01-01",
        "cap_amount": 75.0,
        "cap_unit": "per_day",
        "receipt_required": True,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "USD",
    },
    {
        "id": "MEL-11",
        "category": "meals",
        "region": "UK",
        "effective_date": "2025-01-01",
        "cap_amount": 55.0,
        "cap_unit": "per_day",
        "receipt_required": True,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "GBP",
    },
    {
        "id": "MEL-21",
        "category": "meals",
        "region": "EU",
        "effective_date": "2025-01-01",
        "cap_amount": 60.0,
        "cap_unit": "per_day",
        "receipt_required": True,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "EUR",
    },
    {
        "id": "MEL-31",
        "category": "meals",
        "region": "APAC",
        "effective_date": "2025-01-01",
        "cap_amount": 70.0,
        "cap_unit": "per_day",
        "receipt_required": True,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "USD",
    },
    {
        "id": "ENT-05",
        "category": "entertainment",
        "region": "US",
        "effective_date": "2025-06-01",
        "cap_amount": 150.0,
        "cap_unit": "per_claim",
        "receipt_required": True,
        "stale_after_days": 60,
        "reimbursable": True,
        "reporting_currency": "USD",
    },
    {
        "id": "ENT-15",
        "category": "entertainment",
        "region": "UK",
        "effective_date": "2025-06-01",
        "cap_amount": 120.0,
        "cap_unit": "per_claim",
        "receipt_required": True,
        "stale_after_days": 60,
        "reimbursable": True,
        "reporting_currency": "GBP",
    },
    {
        "id": "OFF-08",
        "category": "office",
        "region": "US",
        "effective_date": "2024-07-01",
        "cap_amount": 200.0,
        "cap_unit": "per_claim",
        "receipt_required": False,
        "stale_after_days": 180,
        "reimbursable": True,
        "reporting_currency": "USD",
    },
    {
        "id": "OFF-18",
        "category": "office",
        "region": "UK",
        "effective_date": "2024-07-01",
        "cap_amount": 150.0,
        "cap_unit": "per_claim",
        "receipt_required": False,
        "stale_after_days": 180,
        "reimbursable": True,
        "reporting_currency": "GBP",
    },
    {
        "id": "TRN-07",
        "category": "training",
        "region": "US",
        "effective_date": "2025-01-01",
        "cap_amount": 1500.0,
        "cap_unit": "per_claim",
        "receipt_required": True,
        "stale_after_days": 120,
        "reimbursable": True,
        "reporting_currency": "USD",
    },
    {
        "id": "TRN-17",
        "category": "training",
        "region": "UK",
        "effective_date": "2025-01-01",
        "cap_amount": 1200.0,
        "cap_unit": "per_claim",
        "receipt_required": True,
        "stale_after_days": 120,
        "reimbursable": True,
        "reporting_currency": "GBP",
    },
    {
        "id": "TRN-27",
        "category": "training",
        "region": "EU",
        "effective_date": "2025-01-01",
        "cap_amount": 1400.0,
        "cap_unit": "per_claim",
        "receipt_required": True,
        "stale_after_days": 120,
        "reimbursable": True,
        "reporting_currency": "EUR",
    },
    {
        "id": "MIL-09",
        "category": "mileage",
        "region": "US",
        "effective_date": "2025-01-01",
        "cap_amount": 300.0,
        "cap_unit": "per_claim",
        "receipt_required": False,
        "stale_after_days": 90,
        "reimbursable": True,
        "reporting_currency": "USD",
    },
    {
        "id": "GFT-01",
        "category": "gifts",
        "region": "US",
        "effective_date": "2024-01-01",
        "cap_amount": 0.0,
        "cap_unit": "per_claim",
        "receipt_required": False,
        "stale_after_days": 90,
        "reimbursable": False,
        "reporting_currency": "USD",
    },
    {
        "id": "GFT-11",
        "category": "gifts",
        "region": "UK",
        "effective_date": "2024-01-01",
        "cap_amount": 0.0,
        "cap_unit": "per_claim",
        "receipt_required": False,
        "stale_after_days": 90,
        "reimbursable": False,
        "reporting_currency": "GBP",
    },
    {
        "id": "GFT-21",
        "category": "gifts",
        "region": "EU",
        "effective_date": "2024-01-01",
        "cap_amount": 0.0,
        "cap_unit": "per_claim",
        "receipt_required": False,
        "stale_after_days": 90,
        "reimbursable": False,
        "reporting_currency": "EUR",
    },
]

# USD per 1 unit of currency, keyed by YYYY-MM.
_USD_PER_UNIT: dict[str, dict[str, float]] = {
    "2025-10": {"USD": 1.0, "GBP": 1.2900, "EUR": 1.0900, "CAD": 0.7200, "JPY": 0.00660, "SGD": 0.7550, "AUD": 0.6500},
    "2025-11": {"USD": 1.0, "GBP": 1.2800, "EUR": 1.0800, "CAD": 0.7150, "JPY": 0.00655, "SGD": 0.7500, "AUD": 0.6450},
    "2025-12": {"USD": 1.0, "GBP": 1.2750, "EUR": 1.0700, "CAD": 0.7100, "JPY": 0.00650, "SGD": 0.7480, "AUD": 0.6400},
    "2026-01": {"USD": 1.0, "GBP": 1.2600, "EUR": 1.0500, "CAD": 0.7050, "JPY": 0.00645, "SGD": 0.7420, "AUD": 0.6380},
    "2026-02": {"USD": 1.0, "GBP": 1.2650, "EUR": 1.0600, "CAD": 0.7120, "JPY": 0.00652, "SGD": 0.7460, "AUD": 0.6420},
    "2026-03": {"USD": 1.0, "GBP": 1.2700, "EUR": 1.0850, "CAD": 0.7350, "JPY": 0.00670, "SGD": 0.7450, "AUD": 0.6550},
    "2026-04": {"USD": 1.0, "GBP": 1.2750, "EUR": 1.0900, "CAD": 0.7280, "JPY": 0.00680, "SGD": 0.7500, "AUD": 0.6600},
    "2026-05": {"USD": 1.0, "GBP": 1.2800, "EUR": 1.1000, "CAD": 0.7300, "JPY": 0.00685, "SGD": 0.7520, "AUD": 0.6620},
    "2026-06": {"USD": 1.0, "GBP": 1.2850, "EUR": 1.1100, "CAD": 0.7330, "JPY": 0.00690, "SGD": 0.7580, "AUD": 0.6680},
    "2026-07": {"USD": 1.0, "GBP": 1.2900, "EUR": 1.1150, "CAD": 0.7380, "JPY": 0.00692, "SGD": 0.7600, "AUD": 0.6700},
    "2026-08": {"USD": 1.0, "GBP": 1.2950, "EUR": 1.1200, "CAD": 0.7400, "JPY": 0.00695, "SGD": 0.7620, "AUD": 0.6720},
}

_ESCALATE_VIOLATIONS = 3

SUBMITTERS: dict[str, dict] = {}


def _seed_submitters() -> None:
    if SUBMITTERS:
        return
    for i in range(20):
        SUBMITTERS[f"emp-clean-{i:02d}"] = {
            "submitter_id": f"emp-clean-{i:02d}",
            "prior_claims": 2 + i,
            "prior_violations": 0,
            "recent_fingerprints": [],
        }
    for i in range(10):
        SUBMITTERS[f"emp-risk-{i:02d}"] = {
            "submitter_id": f"emp-risk-{i:02d}",
            "prior_claims": 8 + i,
            "prior_violations": 1 if i < 5 else 2,
            "recent_fingerprints": [],
        }
    for i in range(10):
        SUBMITTERS[f"emp-viol-{i:02d}"] = {
            "submitter_id": f"emp-viol-{i:02d}",
            "prior_claims": 15 + i,
            "prior_violations": 3 + (i % 4),
            "recent_fingerprints": [],
        }
    # Duplicate fingerprints are filled by the claims generator via register_fingerprint.
    for i in range(6):
        SUBMITTERS[f"emp-dup-{i:02d}"] = {
            "submitter_id": f"emp-dup-{i:02d}",
            "prior_claims": 6 + i,
            "prior_violations": 1,
            "recent_fingerprints": [],
        }
    # Eval-corpus clones: same violation counts, empty fingerprints
    # (eval duplicate cases register their own fingerprints).
    for src, dest_prefix in (
        ("emp-clean", "eval-clean"),
        ("emp-risk", "eval-risk"),
        ("emp-viol", "eval-viol"),
        ("emp-dup", "eval-dup"),
    ):
        for key, row in list(SUBMITTERS.items()):
            if not key.startswith(f"{src}-"):
                continue
            suffix = key[len(src) :]
            dest_id = f"{dest_prefix}{suffix}"
            SUBMITTERS[dest_id] = {
                "submitter_id": dest_id,
                "prior_claims": row["prior_claims"],
                "prior_violations": row["prior_violations"],
                "recent_fingerprints": [],
            }


_seed_submitters()


def claim_fingerprint(merchant: str, claim_date: str | None, amount: float) -> str:
    date_part = claim_date or "none"
    return f"{merchant.strip().lower()}|{date_part}|{amount:.2f}"


def register_fingerprint(submitter_id: str, fingerprint: str) -> None:
    """Used by the corpus generator so duplicate claims have history to match."""
    row = SUBMITTERS[submitter_id]
    fps = list(row["recent_fingerprints"])
    if fingerprint not in fps:
        fps.append(fingerprint)
    row["recent_fingerprints"] = fps


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def money(value: float) -> float:
    return round(float(value) + 1e-12, 2)


def fx_rate_value(from_currency: str, to_currency: str, on: str) -> float | None:
    frm = from_currency.upper().strip()
    to = to_currency.upper().strip()
    if frm == to:
        return 1.0
    month = on[:7] if on else ""
    table = _USD_PER_UNIT.get(month)
    if not table or frm not in table or to not in table:
        return None
    usd_from = table[frm]
    usd_to = table[to]
    if usd_to == 0:
        return None
    return round(usd_from / usd_to, 4)


def lookup_policy_fixture(category: str, region: str, claim_date: str) -> dict:
    cat = (category or "").strip().lower()
    reg = (region or "").strip().upper()
    parsed = _parse_date(claim_date)
    if not cat or not reg or parsed is None:
        return {
            "found": False,
            "reason": "category, region, and a YYYY-MM-DD claim_date are required",
        }

    matches = [
        clause
        for clause in POLICY_CLAUSES
        if clause["category"] == cat
        and clause["region"] == reg
        and date.fromisoformat(clause["effective_date"]) <= parsed
    ]
    if not matches:
        return {"found": False, "reason": "no_clause"}

    clause = max(matches, key=lambda c: c["effective_date"])
    return {
        "found": True,
        "id": clause["id"],
        "category": clause["category"],
        "region": clause["region"],
        "cap_amount": clause["cap_amount"],
        "cap_unit": clause["cap_unit"],
        "receipt_required": clause["receipt_required"],
        "effective_date": clause["effective_date"],
        "stale_after_days": clause["stale_after_days"],
        "reimbursable": clause["reimbursable"],
        "reporting_currency": clause["reporting_currency"],
    }


def get_fx_rate_fixture(from_currency: str, to_currency: str, rate_date: str) -> dict:
    parsed = _parse_date(rate_date)
    if parsed is None:
        return {"found": False, "reason": "date must be YYYY-MM-DD"}
    rate = fx_rate_value(from_currency, to_currency, rate_date)
    if rate is None:
        return {
            "found": False,
            "reason": "no_rate",
            "from_currency": from_currency,
            "to_currency": to_currency,
            "date": rate_date,
        }
    return {
        "found": True,
        "from_currency": from_currency.upper().strip(),
        "to_currency": to_currency.upper().strip(),
        "date": rate_date,
        "rate": rate,
    }


def get_submitter_history_fixture(submitter_id: str) -> dict:
    row = SUBMITTERS.get(submitter_id)
    if row is None:
        return {
            "found": False,
            "submitter_id": submitter_id,
            "prior_claims": 0,
            "prior_violations": 0,
            "recent_fingerprints": [],
        }
    return {
        "found": True,
        "submitter_id": row["submitter_id"],
        "prior_claims": row["prior_claims"],
        "prior_violations": row["prior_violations"],
        "recent_fingerprints": list(row["recent_fingerprints"]),
    }


def post_decision_fixture(
    claim_id: str,
    decision: str,
    approved_amount: float | None,
    policy_clause: str | None,
    rationale: str,
) -> dict:
    payload = (
        f"{claim_id}|{decision}|{approved_amount}|{policy_clause}|{rationale}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return {
        "confirmation_id": f"CONF-{digest}",
        "status": "recorded",
        "claim_id": claim_id,
        "decision": decision,
    }


def parse_receipt_total(receipt_text: str | None) -> float | None:
    if not receipt_text:
        return None
    match = re.search(
        r"(?i)total(?:\s+due)?\s*[:\-]?\s*(?:[A-Z]{3}\s*)?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})|[0-9]+\.[0-9]{2})",
        receipt_text,
    )
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def ground_truth_for(claim: ExpenseClaim, confidence: float, rationale: str) -> Adjudication:
    """Rule engine used only to construct labels. The agent must not import this
    as a shortcut — it has to call tools and decide."""
    policy = lookup_policy_fixture(
        claim.category, claim.region, claim.claim_date or ""
    )
    history = get_submitter_history_fixture(claim.submitter_id)
    reporting = claim.reporting_currency
    fx = get_fx_rate_fixture(
        claim.claim_currency, reporting, claim.claim_date or AS_OF_DATE
    )
    fx_rate = fx.get("rate") if fx.get("found") else None

    def _base(**overrides) -> Adjudication:
        payload = {
            "reimbursable": False,
            "decision": "escalate",
            "policy_clause": policy.get("id") if policy.get("found") else None,
            "approved_amount": None,
            "reporting_currency": reporting,
            "fx_rate_used": fx_rate,
            "effective_date": policy.get("effective_date") if policy.get("found") else None,
            "receipt_required": bool(policy.get("receipt_required")) if policy.get("found") else False,
            "rationale": rationale,
            "confidence": confidence,
        }
        payload.update(overrides)
        return Adjudication.model_validate(payload)

    if not policy.get("found"):
        return _base(
            decision="escalate",
            policy_clause=None,
            approved_amount=None,
            fx_rate_used=None,
            effective_date=None,
            receipt_required=False,
        )

    fingerprint = claim_fingerprint(
        claim.merchant, claim.claim_date, claim.claimed_amount
    )
    if history.get("prior_violations", 0) >= _ESCALATE_VIOLATIONS:
        return _base(
            decision="escalate",
            approved_amount=None,
            reimbursable=False,
            fx_rate_used=None,
        )
    if fingerprint in history.get("recent_fingerprints", []):
        return _base(
            decision="escalate",
            approved_amount=None,
            reimbursable=False,
            fx_rate_used=None,
        )

    if not policy["reimbursable"]:
        return _base(
            decision="reject",
            reimbursable=False,
            approved_amount=0.0,
            fx_rate_used=None,
        )

    if policy["receipt_required"] and not (claim.receipt_text or "").strip():
        return _base(
            decision="reject",
            reimbursable=False,
            approved_amount=0.0,
            fx_rate_used=None,
        )

    submitted = _parse_date(claim.submitted_at)
    incurred = _parse_date(claim.claim_date)
    if submitted is None or incurred is None:
        return _base(decision="escalate", approved_amount=None, fx_rate_used=None)
    age_days = (submitted - incurred).days
    if age_days > int(policy["stale_after_days"]):
        return _base(
            decision="reject",
            reimbursable=False,
            approved_amount=0.0,
            fx_rate_used=None,
        )

    receipt_total = parse_receipt_total(claim.receipt_text)
    if receipt_total is not None:
        if abs(receipt_total - claim.claimed_amount) > max(0.01 * claim.claimed_amount, 0.5):
            return _base(
                decision="reject",
                reimbursable=False,
                approved_amount=0.0,
                fx_rate_used=None,
            )

    if not fx.get("found") or fx_rate is None:
        return _base(decision="escalate", approved_amount=None, fx_rate_used=None)

    converted = money(claim.claimed_amount * float(fx_rate))
    cap_unit = policy["cap_unit"]
    if cap_unit in {"per_day", "per_night"}:
        if claim.units is None or claim.units <= 0:
            return _base(decision="escalate", approved_amount=None, fx_rate_used=None)
        cap = money(float(policy["cap_amount"]) * int(claim.units))
    else:
        cap = money(float(policy["cap_amount"]))

    if converted <= cap + 0.001:
        return _base(
            decision="approve",
            reimbursable=True,
            approved_amount=converted,
        )
    return _base(
        decision="partial",
        reimbursable=True,
        approved_amount=cap,
    )


def unhedge_identifier(value: str | None) -> str | None:
    """Exactly-checked identifiers cannot contain hedges."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    lowered = trimmed.lower()
    if "?" in trimmed or " or " in lowered or "unknown" in lowered:
        return None
    return trimmed

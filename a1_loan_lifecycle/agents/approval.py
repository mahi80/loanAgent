"""Approval / Workflow Agent: recommends the next action, routes to the right
approval authority (CP-6.1) and drafts the credit memo. It never approves -
the decision is always taken by a human with sufficient authority."""
from __future__ import annotations

from typing import Any

from shared.llm_client import LLMClient

NAME = "Approval / Workflow Agent"

AUTHORITY_LEVELS = [
    ("Credit Manager", 2_000_000),
    ("Senior Credit Officer", 10_000_000),
    ("Credit Committee", 20_000_000),
    ("Board Credit Committee", float("inf")),
]

DECISIONS = ["APPROVE", "APPROVE_WITH_CONDITIONS", "REQUEST_INFO", "REFER", "DECLINE"]

STANDARD_CPS = [
    "Executed facility agreement",
    "Perfected security - charge registered",
    "Collateral insured with bank as loss payee",
    "Borrower board resolution",
]


def required_authority(amount: float, escalate: bool) -> str:
    idx = next(i for i, (_, cap) in enumerate(AUTHORITY_LEVELS) if amount <= cap)
    if escalate:
        idx = min(idx + 1, len(AUTHORITY_LEVELS) - 1)
    return AUTHORITY_LEVELS[idx][0]


def authority_rank(role: str) -> int:
    return [r for r, _ in AUTHORITY_LEVELS].index(role)


def recommend(dd: dict, risk: dict) -> tuple[str, list[str]]:
    checks = dd["checks"]
    reasons = []
    if any(c["clause"] == "CP-2.1" and c["status"] == "FAIL" for c in checks):
        return "DECLINE", ["Sanctions match (CP-2.1) - mandatory decline"]
    hard_fails = [c for c in checks if c["status"] == "FAIL"]
    if dd["missing"]["items"]:
        reasons.append(f"{len(dd['missing']['items'])} required item(s) missing - application incomplete")
        if not hard_fails:
            return "REQUEST_INFO", reasons
    if len(hard_fails) >= 2:
        return "DECLINE", reasons + [f"{c['clause']} {c['check']} {c['value']} breaches {c['threshold']}" for c in hard_fails]
    if hard_fails:
        return "REFER", reasons + [f"Policy exception required: {hard_fails[0]['clause']} {hard_fails[0]['check']}"]
    warns = [c for c in checks if c["status"] == "WARN"]
    if warns or risk["grade"] >= 5:
        return "APPROVE_WITH_CONDITIONS", [f"{c['clause']}: {c['note']}" for c in warns] or [f"Risk grade {risk['grade']}"]
    return "APPROVE", ["All policy checks passed", f"Risk grade {risk['grade']}/10 ({risk['band']})"]


def conditions(dd: dict, risk: dict) -> list[str]:
    cps = list(STANDARD_CPS)
    for c in dd["checks"]:
        if c["status"] == "WARN":
            cps.append(f"{c['clause']}: {c['note']}")
    return cps


def run(app: dict, intake: dict, dd: dict, risk: dict, llm: LLMClient) -> dict[str, Any]:
    decision, reasons = recommend(dd, risk)
    exceptions = any(c["status"] == "FAIL" for c in dd["checks"])
    pep = any(c["clause"] == "CP-2.2" and c["status"] == "WARN" for c in dd["checks"])
    authority = required_authority(app["amount_usd"], escalate=exceptions or pep)
    cps = conditions(dd, risk)
    confidence = 0.9 if decision in ("APPROVE", "DECLINE", "REQUEST_INFO") else 0.7
    if dd.get("missing", {}).get("items") or intake["security_flags"]:
        confidence -= 0.1

    def fallback() -> dict[str, Any]:
        m = dd["metrics"]
        lines = [
            f"CREDIT MEMO (DRAFT) - {app['application_id']} - {app['borrower']}",
            f"Facility: USD {app['amount_usd']:,.0f} {app['product'].replace('_', ' ')}, "
            f"{app['tenor_years']} yrs @ {app['interest_rate']:.1%}. Purpose: {app['purpose']}.",
            f"Key metrics: DSCR {m.get('dscr', 'n/a')}x | Leverage {m.get('leverage', 'n/a')}x | "
            f"LTV {m.get('ltv', 'n/a')} | Vintage {m.get('vintage_years', 'n/a')} yrs.",
            f"Risk: grade {risk['grade']}/10 ({risk['band']}). {risk['summary']}",
            f"Recommendation: {decision.replace('_', ' ')} - " + "; ".join(reasons),
            f"Approval authority: {authority}.",
        ]
        return {"memo": "\n".join(lines)}

    memo = llm.complete_json(
        NAME,
        "Draft a concise credit memo (<= 200 words) for a credit committee from the facts given. Keep the "
        'recommendation and numbers exactly as provided. Return {"memo": str}.',
        f"Application: {app}\nMetrics: {dd['metrics']}\nRisk: {risk}\nRecommendation: {decision}\n"
        f"Reasons: {reasons}\nAuthority: {authority}\nConditions: {cps}",
        fallback,
    )
    return {
        "recommendation": decision,
        "reasons": reasons,
        "confidence": round(confidence, 2),
        "required_authority": authority,
        "conditions_precedent": cps,
        "memo": memo.get("memo", ""),
    }

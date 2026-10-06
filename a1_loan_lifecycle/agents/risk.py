"""Risk Agent: deterministic risk grade (1 = best, 10 = worst) from a transparent
scorecard, plus LLM-written risk observations and mitigants.
No protected attributes (gender, religion, caste, etc.) are used."""
from __future__ import annotations

from typing import Any

from shared.llm_client import LLMClient

NAME = "Risk Agent"


def scorecard(metrics: dict, checks: list[dict], security_flags: list) -> tuple[int, list[dict]]:
    pts: list[dict] = []

    def add(factor: str, p: int, why: str) -> None:
        pts.append({"factor": factor, "points": p, "why": why})

    d = metrics.get("dscr")
    if d is not None:
        add("DSCR", 0 if d >= 1.75 else 1 if d >= 1.4 else 2 if d >= 1.25 else 3 if d >= 1.1 else 4, f"{d:.2f}x")
    lv = metrics.get("leverage")
    if lv is not None:
        add("Leverage", 0 if lv <= 2.5 else 1 if lv <= 3.5 else 2 if lv <= 4.5 else 3, f"{lv:.2f}x")
    ltv = metrics.get("ltv")
    if ltv is not None:
        add("LTV", 0 if ltv <= 0.55 else 1 if ltv <= 0.70 else 2, f"{ltv:.0%}")
    warns = [c for c in checks if c["status"] == "WARN"]
    if warns:
        add("Policy warnings", min(len(warns), 3), ", ".join(c["clause"] for c in warns))
    if security_flags:
        add("Document integrity", 1, "Instruction-like text found in submitted documents")
    if not pts:
        return 5, pts  # insufficient data -> neutral grade
    grade = max(1, min(10, 1 + sum(p["points"] for p in pts)))
    return grade, pts


def run(app: dict, intake: dict, dd: dict, llm: LLMClient) -> dict[str, Any]:
    grade, factors = scorecard(dd["metrics"], dd["checks"], intake["security_flags"])
    band = "Low" if grade <= 3 else "Moderate" if grade <= 6 else "High"
    issues = [c for c in dd["checks"] if c["status"] in ("FAIL", "WARN", "MISSING")]

    def fallback() -> dict[str, Any]:
        obs, mit = [], []
        for c in issues:
            obs.append(f"[{c['clause']}] {c['check']}: {c['value']} vs {c['threshold']} - {c['note']}.")
            mit.append(MITIGANTS.get(c["clause"], "Escalate for credit officer judgement."))
        if intake["security_flags"]:
            obs.append("Submitted document contains text attempting to instruct the automated reviewer; "
                       "treated as a document-integrity concern.")
            mit.append("Obtain clean originals directly from the borrower; note in file.")
        if not obs:
            obs.append("All policy parameters within limits; no adverse KYC findings.")
            mit.append("Standard covenants and conditions precedent.")
        summary = (f"{app['borrower']} ({app['sector']}) requests USD {app['amount_usd']:,.0f} "
                   f"{app['product'].replace('_', ' ')}. Indicative risk grade {grade}/10 ({band}). "
                   f"{len(issues)} policy item(s) need attention.")
        return {"summary": summary, "observations": obs, "mitigants": sorted(set(mit))}

    narrative = llm.complete_json(
        NAME,
        "You are a senior credit risk analyst. Using ONLY the facts provided, write a short risk summary, "
        "a list of specific risk observations (cite clause IDs) and practical mitigants. Do not change any "
        'numbers or the grade. Return {"summary": str, "observations": [str], "mitigants": [str]}.',
        f"Application: {app}\nMetrics: {dd['metrics']}\nPolicy findings: {issues}\n"
        f"Grade: {grade}/10 ({band})\nDocument integrity flags: {intake['security_flags']}",
        fallback,
    )
    return {"grade": grade, "band": band, "scorecard": factors, **narrative}


MITIGANTS = {
    "CP-2.2": "Complete Enhanced Due Diligence on PEP director; source-of-wealth review.",
    "CP-2.3": "Compliance referral on adverse media before credit decision.",
    "CP-2.4": "Obtain signed beneficial-owner declaration prior to sanction.",
    "CP-3.1": "Sponsor corporate guarantee covering construction and ramp-up.",
    "CP-3.3": "Obtain audited FY financials / auditor's explanation of qualification.",
    "CP-4.1": "Reduce quantum or extend tenor; add cash-sweep and DSRA (2 quarters).",
    "CP-4.2": "Additional sponsor equity to bring leverage within limit.",
    "CP-4.3": "Additional collateral or reduced quantum to bring LTV <= 70%.",
    "CP-4.4": "Fresh valuation by bank-empanelled valuer as condition precedent.",
    "CP-5.1": "Sector-head concurrence; -20% revenue stress case in memo.",
    "CP-5.2": "Escrow of receivables; monthly stock/receivable statements.",
    "CP-5.3": "Assignment of receivables from top customer.",
}

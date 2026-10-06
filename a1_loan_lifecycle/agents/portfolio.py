"""Portfolio Monitoring Agent: quarterly covenant testing and Early Warning
Signals (CP-8.1) across the book, with an LLM narrative for Red accounts."""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from shared.llm_client import LLMClient

from . import DATA

NAME = "Portfolio Monitoring Agent"


def scan(as_of: date = date(2026, 10, 1)) -> pd.DataFrame:
    df = pd.read_csv(DATA / "portfolio.csv")
    rows = []
    for _, r in df.iterrows():
        signals = []
        headroom = (r.dscr_q3 - r.dscr_covenant) / r.dscr_covenant
        if r.dscr_q3 < r.dscr_covenant:
            signals.append(f"DSCR covenant breach ({r.dscr_q3:.2f}x < {r.dscr_covenant:.2f}x)")
        elif headroom < 0.10:
            signals.append(f"DSCR headroom {headroom:.0%} (< 10%)")
        if r.dscr_q1 > r.dscr_q2 > r.dscr_q3:
            signals.append("DSCR declining 2 consecutive quarters")
        if r.leverage_q3 > r.leverage_covenant:
            signals.append(f"Leverage breach ({r.leverage_q3:.1f}x > {r.leverage_covenant:.1f}x)")
        if r.days_past_due > 30:
            signals.append(f"{r.days_past_due} days past due")
        age = (as_of - date.fromisoformat(r.last_valuation)).days / 30.44
        if age > 12:
            signals.append(f"Collateral valuation {age:.0f} months old")
        breach = any("breach" in s or "past due" in s for s in signals)
        rag = "Red" if breach else "Amber" if signals else "Green"
        rows.append({**r.to_dict(), "dscr_headroom": round(headroom, 3), "ews_rag": rag,
                     "signals": "; ".join(signals) or "-"})
    return pd.DataFrame(rows)


def narrative(row: dict, llm: LLMClient) -> str:
    def fallback() -> dict[str, Any]:
        return {"note": (
            f"{row['borrower']} ({row['sector']}, USD {row['outstanding_usd']:,.0f}) is rated {row['ews_rag']}: "
            f"{row['signals']}. Recommended: schedule borrower meeting within 7 days, obtain latest management "
            f"accounts and cash-flow forecast, consider standstill / restructuring options and provisioning review.")}

    return llm.complete_json(
        NAME,
        "You are a portfolio monitoring analyst. Write a 3-sentence early-warning note with recommended next "
        'actions for the relationship team. Use only the facts given. Return {"note": str}.',
        str(row),
        fallback,
    )["note"]

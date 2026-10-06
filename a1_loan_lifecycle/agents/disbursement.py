"""Disbursement / Condition-Monitoring Agent: turns approved conditions into a
tracked checklist and gates disbursement until every CP is evidenced."""
from __future__ import annotations

from typing import Any

NAME = "Disbursement Agent"


def run(case: dict, satisfied: set[str]) -> dict[str, Any]:
    cps = case["approval"]["conditions_precedent"]
    items = [{"condition": c, "satisfied": c in satisfied} for c in cps]
    pending = [i["condition"] for i in items if not i["satisfied"]]
    return {
        "checklist": items,
        "ready": not pending,
        "status": "READY FOR DISBURSEMENT (maker-checker release)" if not pending else f"BLOCKED - {len(pending)} CP(s) pending",
    }

"""Demand Prediction + Agentic Response orchestrator.

sense (forecast) -> Deviation Agent -> Impact Agent -> Constraint Agent ->
Recommender Agent -> [HUMAN APPROVAL] -> Executor Agent (SAP/IBP mock)
Every step is written to the hash-chained audit log.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

import forecasting  # noqa: E402
from agents import constraints, deviation, executor, impact, recommender  # noqa: E402
from shared.audit import AuditLog, inputs_hash  # noqa: E402
from shared.llm_client import LLMClient  # noqa: E402

ROLES = ["Demand Planner", "S&OP Lead"]


class DemandResponseOrchestrator:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()
        self.audit = AuditLog("demand")
        self.sensing: forecasting.SensingResult | None = None
        self.alerts = None

    def sense(self) -> None:
        t0 = time.perf_counter()
        self.sensing = forecasting.run()
        self.alerts = deviation.run(self.sensing.latest)
        self.audit.record("SENSING", "Forecast model + " + deviation.NAME, "sensing.completed", {
            "as_of": str(self.sensing.as_of.date()), "wmape_model": round(self.sensing.mape_model, 4),
            "wmape_plan": round(self.sensing.mape_plan, 4), "alerts": len(self.alerts),
            "ms": int((time.perf_counter() - t0) * 1000)}, model="HistGradientBoosting+runrate")

    def analyse(self, idx: int) -> dict[str, Any]:
        alert = self.alerts.iloc[idx].to_dict()
        case_id = f"DR-{alert['sku']}-{alert['region']}"
        case: dict[str, Any] = {"id": case_id, "alert": alert, "trace": []}
        for key, name, fn in (
            ("impact", impact.NAME, lambda: impact.run(alert, self.llm)),
            ("constraints", constraints.NAME, lambda: constraints.run(alert, self.sensing.latest)),
            ("recommendation", recommender.NAME, lambda: recommender.run(alert, case["impact"], case["constraints"], self.llm)),
        ):
            t0 = time.perf_counter()
            case[key] = fn()
            ms = int((time.perf_counter() - t0) * 1000)
            case["trace"].append({"agent": name, "ms": ms})
            self.audit.record(case_id, name, f"{key}.completed", {"ms": ms}, model=self.llm.model_name)
        case["status"] = "AWAITING_APPROVAL"
        self.audit.record(case_id, "system", "gate.awaiting_human", {
            "plan_hash": inputs_hash(case["recommendation"]["plan"]),
            "cost_usd": case["recommendation"]["totals"]["cost_usd"],
            "approval_level": case["recommendation"]["approval_level"]})
        return case

    def decide(self, case: dict, approver: str, role: str, approved_actions: list[dict], rationale: str,
               reject: bool = False) -> dict:
        rec = case["recommendation"]
        cost = sum(a["cost_usd"] for a in approved_actions)
        if not reject and cost > recommender.APPROVAL_THRESHOLD_USD and role != "S&OP Lead":
            raise PermissionError(f"Plan cost ${cost:,.0f} exceeds ${recommender.APPROVAL_THRESHOLD_USD:,.0f}: S&OP Lead approval required.")
        edited = [a["action"] for a in approved_actions] != [a["action"] for a in rec["plan"]]
        if (reject or edited) and len(rationale.strip()) < 10:
            raise ValueError("Rejecting or editing the agent plan requires a rationale (min 10 characters).")
        case["human"] = {"approver": approver, "role": role, "decision": "REJECTED" if reject else ("APPROVED_WITH_EDITS" if edited else "APPROVED"),
                         "rationale": rationale, "approved_cost_usd": cost,
                         "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.audit.record(case["id"], f"{approver} ({role})", "decision.recorded", case["human"])
        if reject:
            case["status"] = "REJECTED"
            return case
        t0 = time.perf_counter()
        case["executed"] = executor.run(case["id"], case["alert"], approved_actions, approver)
        case["trace"].append({"agent": executor.NAME, "ms": int((time.perf_counter() - t0) * 1000)})
        self.audit.record(case["id"], executor.NAME, "actions.submitted",
                          {"txns": [e["txn_id"] for e in case["executed"]]})
        case["status"] = "ACTIONS_TRIGGERED"
        return case

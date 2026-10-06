"""Deterministic orchestrator for the loan workflow.

application -> intake -> document intelligence -> due diligence (missing info +
policy checks) -> risk -> approval recommendation -> [HUMAN GATE] -> decision
summary. Every step is timed and written to the hash-chained audit log.

The graph is explicit Python (no framework) so it is easy to read in a demo;
in production the same nodes map 1:1 onto LangGraph / Azure AI Foundry Agent
Service / Durable Functions with persisted state.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

from agents import DATA, approval, doc_intel, due_diligence, intake, risk  # noqa: E402
from knowledge.retriever import PolicyRetriever  # noqa: E402
from shared.audit import AuditLog, inputs_hash  # noqa: E402
from shared.llm_client import LLMClient  # noqa: E402

PIPELINE = [
    ("intake", intake.NAME),
    ("doc_intel", doc_intel.NAME),
    ("due_diligence", due_diligence.NAME),
    ("risk", risk.NAME),
    ("approval", approval.NAME),
]


def list_applications() -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted((DATA / "applications").glob("*.json"))]


class LoanOrchestrator:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()
        self.retriever = PolicyRetriever()
        self.audit = AuditLog("loan")

    def _step(self, case: dict, key: str, agent: str, fn, *args) -> Any:
        t0 = time.perf_counter()
        out = fn(*args)
        ms = int((time.perf_counter() - t0) * 1000)
        case["trace"].append({"step": key, "agent": agent, "ms": ms})
        public = {k: v for k, v in out.items() if not k.startswith("_")} if isinstance(out, dict) else out
        self.audit.record(case["id"], agent, f"{key}.completed", {"output_hash": inputs_hash(public), "ms": ms},
                          model=self.llm.model_name)
        return out

    def run_until_gate(self, app: dict) -> dict[str, Any]:
        case: dict[str, Any] = {
            "id": app["application_id"],
            "application": app,
            "trace": [],
            "status": "IN_PROGRESS",
            "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "input_hash": inputs_hash(app),
        }
        self.audit.record(case["id"], "system", "case.opened", {"input_hash": case["input_hash"]})
        case["intake"] = self._step(case, "intake", intake.NAME, intake.run, app)
        if case["intake"]["security_flags"]:
            self.audit.record(case["id"], intake.NAME, "security.prompt_injection_detected",
                              {"flags": case["intake"]["security_flags"]})
        case["doc_intel"] = self._step(case, "doc_intel", doc_intel.NAME, doc_intel.run, case["intake"], self.llm)
        case["dd"] = self._step(case, "due_diligence", due_diligence.NAME, due_diligence.run,
                                app, case["intake"], case["doc_intel"], self.llm, self.retriever)
        case["risk"] = self._step(case, "risk", risk.NAME, risk.run, app, case["intake"], case["dd"], self.llm)
        case["approval"] = self._step(case, "approval", approval.NAME, approval.run,
                                      app, case["intake"], case["dd"], case["risk"], self.llm)
        case["status"] = "AWAITING_HUMAN_DECISION"
        self.audit.record(case["id"], "system", "gate.awaiting_human",
                          {"recommendation": case["approval"]["recommendation"],
                           "required_authority": case["approval"]["required_authority"]})
        return case

    def record_decision(self, case: dict, decision: str, approver: str, role: str, rationale: str) -> dict:
        rec = case["approval"]["recommendation"]
        required = case["approval"]["required_authority"]
        if approval.authority_rank(role) < approval.authority_rank(required) and decision.startswith("APPROVE"):
            raise PermissionError(f"{role} lacks authority; {required} or above required to approve.")
        override = decision != rec
        if override and len(rationale.strip()) < 15:
            raise ValueError("Overriding the agent recommendation requires a rationale (min 15 characters).")
        case["human"] = {
            "decision": decision,
            "approver": approver,
            "role": role,
            "rationale": rationale,
            "override": override,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        case["status"] = f"DECIDED_{decision}"
        self.audit.record(case["id"], f"{approver} ({role})", "decision.recorded", case["human"])
        case["summary_md"] = self.decision_summary(case)
        self.audit.record(case["id"], "system", "summary.generated", {"summary_hash": inputs_hash(case["summary_md"])})
        return case

    def decision_summary(self, case: dict) -> str:
        app, dd, rk, ap, h = case["application"], case["dd"], case["risk"], case["approval"], case["human"]
        rows = "\n".join(
            f"| {c['clause']} | {c['check']} | {c['value']} | {c['threshold']} | {c['status']} |" for c in dd["checks"]
        )
        missing = "\n".join(f"- {i['item']} ({i['clause']})" for i in dd["missing"]["items"]) or "- None"
        trace = "\n".join(f"| {t['agent']} | {t['ms']} ms |" for t in case["trace"])
        return f"""# Decision Summary - {app['application_id']}

**Borrower:** {app['borrower']} | **Facility:** USD {app['amount_usd']:,.0f} {app['product'].replace('_', ' ')} | **Sector:** {app['sector']}
**Input hash:** `{case['input_hash']}` | **Model:** {self.llm.model_name} | **Audit chain valid:** {self.audit.verify_chain()}

## Final decision (human)
- **Decision:** {h['decision'].replace('_', ' ')}
- **Decided by:** {h['approver']} - {h['role']} at {h['ts']}
- **Agent recommendation:** {ap['recommendation'].replace('_', ' ')} (confidence {ap['confidence']:.0%}) - {'OVERRIDDEN' if h['override'] else 'ACCEPTED'}
- **Rationale:** {h['rationale'] or 'Accepted agent recommendation'}
- **Required authority (CP-6.1):** {ap['required_authority']}

## Key metrics (deterministic)
{json.dumps(dd['metrics'], indent=2)}

## Policy checks (RAG-cited)
| Clause | Check | Value | Threshold | Result |
|---|---|---|---|---|
{rows}

## Missing information
{missing}

## Risk ({rk['grade']}/10, {rk['band']})
{rk['summary']}

**Observations**
""" + "\n".join(f"- {o}" for o in rk["observations"]) + """

**Mitigants**
""" + "\n".join(f"- {m}" for m in rk["mitigants"]) + """

## Conditions precedent
""" + "\n".join(f"- {c}" for c in ap["conditions_precedent"]) + f"""

## Agent trace
| Agent | Latency |
|---|---|
{trace}

_Generated by the Agentic Loan Lifecycle prototype. AI outputs are decision support; the credit decision above was taken by a human._
"""

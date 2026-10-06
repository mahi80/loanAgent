"""Executor Agent: converts approved actions into ERP/IBP transactions (mocked
SAP payloads) plus notifications. Writes to runtime/sap_outbox.jsonl - in
production these become SAP BAPI / OData calls through the integration layer."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from shared.audit import RUNTIME_DIR

NAME = "Executor Agent"

TEMPLATES = {
    "STOCK_TRANSFER": ("SAP S/4", "BAPI_PO_CREATE1", "Stock Transport Order (doc type UB)"),
    "EXPEDITE": ("SAP S/4", "BAPI_PO_CREATE1", "Stock Transport Order (UB, express shipping condition)"),
    "PRODUCTION_RESCHEDULE": ("SAP S/4", "BAPI_PLANNEDORDER_CREATE", "Planned order (pull-forward)"),
    "PRODUCTION_CUT": ("SAP S/4", "BAPI_PLANNEDORDER_CHANGE", "Planned order quantity reduction"),
    "ALLOCATION": ("SAP S/4", "aATP product allocation", "Allocation quota change"),
    "PLAN_UPDATE": ("SAP IBP", "OData PLANNING_DATA_API_SRV", "Consensus demand key-figure update"),
}


def run(case_id: str, alert: dict, actions: list[dict], approver: str) -> list[dict[str, Any]]:
    RUNTIME_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = []
    for i, a in enumerate(actions, 1):
        system, api, desc = TEMPLATES[a["type"]]
        out.append({
            "txn_id": f"{case_id}-{i:02d}", "system": system, "api": api, "description": desc,
            "material": alert["sku"], "quantity_t": a["qty_t"],
            "source": a.get("source") or a.get("plant") or "-", "target": a.get("target") or alert["region"],
            "approved_by": approver, "status": "SUBMITTED (mock)", "ts": ts,
        })
    out.append({"txn_id": f"{case_id}-N1", "system": "Teams / e-mail", "api": "Graph sendMail (mock)",
                "description": f"Notify {alert['region']} sales & customer service: {alert['sku']} supply plan updated",
                "material": alert["sku"], "quantity_t": None, "source": "-", "target": alert["region"],
                "approved_by": approver, "status": "QUEUED (mock)", "ts": ts})
    with (RUNTIME_DIR / "sap_outbox.jsonl").open("a", encoding="utf-8") as f:
        for p in out:
            f.write(json.dumps(p) + "\n")
    return out

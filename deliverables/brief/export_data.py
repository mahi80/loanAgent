"""Export all figures for the CTO/CIO Word brief from the real code (mock LLM mode = reproducible)."""
import json
import os
import sys
from pathlib import Path

os.environ["LLM_MODE"] = "mock"
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("data.json")
which = sys.argv[1]
sys.path.insert(0, str(ROOT))
from shared import vsm  # noqa: E402


def vsm_block(csv, demand=120):
    a = vsm.Assumptions(demand)
    df = vsm.load(csv)
    cur, fut = vsm.state(df, a), vsm.state(df, a, True)
    return {
        "takt_h": round(a.takt_h, 2),
        "steps": [{"no": int(r.step_no), "step": r.step, "fte": int(r.fte), "va": float(r.va_h), "nva": float(r.nva_h),
                   "wait_d": float(r.wait_d), "ct": float(r.eff_ct_h), "over": bool(r.over_takt),
                   "nva_example": df.loc[i, "nva_example"], "agent": df.loc[i, "agent"]}
                  for i, r in enumerate(cur.itertuples())],
        "cur": {k: (float(v) if not isinstance(v, str) else v) for k, v in vsm.summary(cur, a).items()},
        "fut": {k: (float(v) if not isinstance(v, str) else v) for k, v in vsm.summary(fut, a).items()},
        "priority": [{"rank": int(r.rank), "step": r.step, "nva_h": float(r.nva_total_h), "feas": int(r.feasibility),
                      "bn": float(r.bottleneck_factor), "api": float(r.api), "agent": r.agent}
                     for r in vsm.priority(df, a).itertuples()],
        "before_after": vsm.before_after(df, a).astype(str).values.tolist(),
    }


data = json.loads(OUT.read_text()) if OUT.exists() else {}

if which == "a1":
    sys.path.insert(0, str(ROOT / "a1_loan_lifecycle"))
    from orchestrator import LoanOrchestrator  # noqa: E402
    import json as _j

    o = LoanOrchestrator()
    cases = []
    for p in sorted((ROOT / "a1_loan_lifecycle/data/applications").glob("*.json")):
        app = _j.loads(p.read_text())
        c = o.run_until_gate(app, actor="doc-export")
        dd = c["dd"]
        cases.append({
            "id": app["application_id"], "borrower": app["borrower"], "product": app["product"].replace("_", " "),
            "amount": app["amount_usd"], "sector": app["sector"],
            "metrics": dd["metrics"],
            "fails": [f"{x['clause']} {x['check']} {x['value']}" for x in dd["checks"] if x["status"] == "FAIL"],
            "warns": [f"{x['clause']} {x['check']}" for x in dd["checks"] if x["status"] == "WARN"],
            "missing": [m["item"] for m in dd["missing"]["items"]],
            "injection": len(c["intake"]["security_flags"]) > 0,
            "grade": c["risk"]["grade"], "band": c["risk"]["band"],
            "rec": c["approval"]["recommendation"].replace("_", " "), "authority": c["approval"]["required_authority"],
            "conditions": c["approval"]["conditions_precedent"],
        })
    data["a1"] = {"vsm": vsm_block(ROOT / "a1_loan_lifecycle/data/vsm_steps.csv"), "cases": cases}

if which == "a2":
    sys.path.insert(0, str(ROOT / "a2_chem_demand"))
    import pandas as pd  # noqa: E402
    from orchestrator import DemandResponseOrchestrator  # noqa: E402

    o = DemandResponseOrchestrator()
    o.sense()
    al = o.alerts
    c = o.analyse(0)
    pvc_idx = int(al[(al.sku == "PVC-K67") & (al.region == "EU")].index[0])
    c2 = o.analyse(pvc_idx)
    opp = pd.read_csv(ROOT / "a2_chem_demand/data/opportunities.csv")
    opp["score"] = opp.value_score * opp.feasibility_score
    data["a2"] = {
        "vsm": vsm_block(ROOT / "a2_chem_demand/data/vsm_steps.csv"),
        "opportunities": opp.sort_values(["wave", "score"], ascending=[True, False]).to_dict("records"),
        "sensing": {"model": round(o.sensing.mape_model, 4), "baseline": round(o.sensing.mape_baseline, 4),
                    "plan": round(o.sensing.mape_plan, 4), "as_of": str(o.sensing.as_of.date())},
        "alerts": [{"sku": r.sku, "name": r.name, "region": r.region, "direction": r.direction,
                    "fwd": round(float(r.deviation_pct), 3), "actual": round(float(r.actual_dev_pct), 3),
                    "z": round(float(r.z_score), 1), "margin": float(r.margin_at_stake_usd), "severity": str(r.severity)}
                   for r in al.itertuples()],
        "case": {
            "alert": {k: (float(v) if isinstance(v, (int, float)) else str(v)) for k, v in c["alert"].items()
                      if k in ("sku", "name", "region", "deviation_pct", "actual_dev_pct", "z_score", "gap_t", "pmi", "pmi_chg4",
                               "plan", "sensed", "margin_at_stake_usd")},
            "customers": c["impact"]["customers"].to_dict("records"),
            "driver": c["impact"]["primary_driver"], "share": c["impact"]["driver_share"],
            "revenue": c["impact"]["revenue_at_risk_usd"], "narrative": c["impact"]["narrative"],
            "position": c["constraints"]["position"],
            "plan": [{k: p.get(k) for k in ("type", "action", "qty_t", "cost_usd", "benefit_usd", "lead_time_days",
                                            "margin_forgone_usd")} for p in c["recommendation"]["plan"]],
            "totals": c["recommendation"]["totals"], "approval": c["recommendation"]["approval_level"],
        },
        "case_pvc": {"narrative": c2["impact"]["narrative"], "plan": [p["action"] for p in c2["recommendation"]["plan"]],
                     "anomalous": c2["impact"]["anomalous_customers"]},
    }

OUT.write_text(json.dumps(data, indent=1, default=str))
print("exported", which)

"""Agent evaluation harness - golden cases for both prototypes.

Checks business outcomes, extraction accuracy, RAG grounding and the safety
controls (authority limits, override rationale, prompt-injection detection).
Runs in whatever LLM mode is configured (mock / ollama / openai / azure), so
it doubles as a CI gate and as a model-comparison tool.

  python evals/run_evals.py                 # all suites, LLM mode from .env
  python evals/run_evals.py --mode mock     # deterministic
  python evals/run_evals.py --suite a1      # one suite: a1 | rag | a2

Writes runtime/eval_report.json; exit code 1 if any check fails.
Production: run on every PR (GitHub Actions) and nightly against the
production model; track pass rate, field accuracy and latency over time.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden.json"
REPORT = ROOT / "runtime" / "eval_report.json"


class Checks:
    def __init__(self, suite: str):
        self.suite, self.rows = suite, []

    def check(self, case: str, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append({"suite": self.suite, "case": case, "check": name, "pass": bool(ok), "detail": str(detail)[:160]})


# --------------------------------------------------------------------------- suites
def suite_a1(g: dict) -> list[dict]:
    sys.path[:0] = [str(ROOT), str(ROOT / "a1_loan_lifecycle")]
    from agents.doc_intel import SCHEMA, _regex_extract, _sanitise
    from orchestrator import LoanOrchestrator, list_applications

    c = Checks("a1")
    o = LoanOrchestrator()
    apps = {a["application_id"]: a for a in list_applications()}
    for gc in g["a1"]:
        t0 = time.perf_counter()
        case = o.run_until_gate(apps[gc["app"]], actor="eval")
        ms = int((time.perf_counter() - t0) * 1000)
        e, ap, dd = gc["expect"], case["approval"], case["dd"]
        cid = gc["app"]
        c.check(cid, "recommendation", ap["recommendation"] == e["recommendation"], ap["recommendation"])
        if "authority" in e:
            c.check(cid, "routed authority", ap["required_authority"] == e["authority"], ap["required_authority"])
        for item in e.get("missing_includes", []):
            items = [m["item"] for m in dd["missing"]["items"]]
            c.check(cid, f"missing info: {item}", item in items, items)
        for clause in e.get("fails_include", []):
            fails = [x["clause"] for x in dd["checks"] if x["status"] == "FAIL"]
            c.check(cid, f"policy FAIL {clause}", clause in fails, fails)
        if "security_flags_min" in e:
            n = len(case["intake"]["security_flags"])
            c.check(cid, "prompt injection detected", n >= e["security_flags_min"], n)
        if "grade_max" in e:
            c.check(cid, f"risk grade <= {e['grade_max']}", case["risk"]["grade"] <= e["grade_max"], case["risk"]["grade"])
        if "grade_min" in e:
            c.check(cid, f"risk grade >= {e['grade_min']}", case["risk"]["grade"] >= e["grade_min"], case["risk"]["grade"])
        # LLM-only field accuracy vs deterministic reference parse of the same documents
        ref, hit = 0, 0
        for dtype, doc in case["intake"]["_docs"].items():
            truth = _regex_extract(_sanitise(doc["text"]), SCHEMA.get(dtype, {}))["fields"]
            for k, v in truth.items():
                ref += 1
                got = case["doc_intel"]["fields"].get(k, {})
                hit += got.get("method") == "llm" and str(got.get("value")).lower() == str(v["value"]).lower()
        acc = hit / ref if ref else 1
        c.check(cid, f"LLM field accuracy >= {g['min_field_accuracy']:.0%}", acc >= g["min_field_accuracy"] or o.llm.mode == "mock",
                f"{acc:.0%} ({hit}/{ref}){' [mock: rules]' if o.llm.mode == 'mock' else ''}")
        c.check(cid, f"latency <= {g['max_case_seconds']}s", ms <= g["max_case_seconds"] * 1000, f"{ms} ms")
    # safety controls
    case = o.run_until_gate(apps["APP-1001"], actor="eval")
    try:
        o.record_decision(case, "APPROVE", "eval", "Credit Manager", "")
        c.check("controls", "approval above authority is blocked", False, "was allowed")
    except PermissionError as exc:
        c.check("controls", "approval above authority is blocked", True, exc)
    try:
        o.record_decision(case, "DECLINE", "eval", "Senior Credit Officer", "")
        c.check("controls", "override needs rationale", False, "was allowed")
    except ValueError as exc:
        c.check("controls", "override needs rationale", True, exc)
    c.check("controls", "audit hash chain valid", o.audit.verify_chain())
    llm_ok = sum(t.ok for t in o.llm.telemetry)
    c.check("llm", "LLM calls without fallback", llm_ok == len(o.llm.telemetry), f"{llm_ok}/{len(o.llm.telemetry)} ({o.llm.model_name})")
    return c.rows


def suite_rag(g: dict) -> list[dict]:
    sys.path[:0] = [str(ROOT), str(ROOT / "a1_loan_lifecycle")]
    from knowledge.assistant import NOT_COVERED, answer
    from knowledge.retriever import PolicyRetriever
    from shared.llm_client import LLMClient

    c = Checks("rag")
    r, llm = PolicyRetriever(include_addenda=False), LLMClient()
    for gc in g["rag"]:
        res = answer(gc["q"], r, llm)
        q = gc["q"][:45]
        if gc.get("refuse"):
            c.check(q, "refuses off-topic", res["answer"] == NOT_COVERED, res["answer"][:80])
            continue
        c.check(q, f"cites {gc['cite']}", gc["cite"] in res["citations"], res["citations"])
        c.check(q, "citations grounded in retrieved clauses", res["grounded"], res.get("ungrounded_citations"))
        for needle in gc.get("contains", []):
            c.check(q, f"answer mentions '{needle}'", needle.lower() in res["answer"].lower(), res["answer"][:120])
    return c.rows


def suite_a2(g: dict) -> list[dict]:
    sys.path[:0] = [str(ROOT), str(ROOT / "a2_chem_demand")]
    from orchestrator import DemandResponseOrchestrator

    c, e = Checks("a2"), g["a2"]
    o = DemandResponseOrchestrator()
    o.sense()
    al = o.alerts
    top = al.iloc[0]
    c.check("sensing", "model beats frozen plan (WMAPE)", o.sensing.mape_model < o.sensing.mape_plan,
            f"{o.sensing.mape_model:.1%} vs {o.sensing.mape_plan:.1%}")
    c.check("sensing", f"top alert {e['top']['sku']} {e['top']['region']}",
            (top.sku, top.region) == (e["top"]["sku"], e["top"]["region"]), f"{top.sku} {top.region}")
    c.check("sensing", "top alert is upside", "UPSIDE" in top.direction, top.direction)
    pvc = al[(al.sku == e["downside"]["sku"]) & (al.region == e["downside"]["region"])]
    c.check("sensing", f"downside alert {e['downside']['sku']} {e['downside']['region']}", len(pvc) == 1 and "DOWNSIDE" in pvc.iloc[0].direction)
    case = o.analyse(0, actor="eval")
    c.check("EPX-200 APAC", f"driver = {e['top']['driver']}", case["impact"]["primary_driver"] == e["top"]["driver"],
            case["impact"]["primary_driver"])
    c.check("EPX-200 APAC", f"gap >= {e['top']['min_gap_t']} t", case["recommendation"]["totals"]["need_t"] >= e["top"]["min_gap_t"],
            case["recommendation"]["totals"]["need_t"])
    c.check("EPX-200 APAC", f"routed to {e['top']['approval']}", case["recommendation"]["approval_level"] == e["top"]["approval"],
            case["recommendation"]["approval_level"])
    try:
        o.decide(case, "eval", "Demand Planner", case["recommendation"]["plan"], "")
        c.check("controls", "planner blocked above value threshold", False, "was allowed")
    except PermissionError as exc:
        c.check("controls", "planner blocked above value threshold", True, exc)
    if len(pvc):
        case2 = o.analyse(int(pvc.index[0]), actor="eval")
        c.check("PVC-K67 EU", f"anomaly flags {e['downside']['anomaly']}",
                e["downside"]["anomaly"] in case2["impact"]["anomalous_customers"], case2["impact"]["anomalous_customers"])
    llm_ok = sum(t.ok for t in o.llm.telemetry)
    c.check("llm", "LLM calls without fallback", llm_ok == len(o.llm.telemetry), f"{llm_ok}/{len(o.llm.telemetry)} ({o.llm.model_name})")
    return c.rows


SUITES = {"a1": suite_a1, "rag": suite_rag, "a2": suite_a2}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=[*SUITES, "all"], default="all")
    ap.add_argument("--mode", help="override LLM_MODE (mock|ollama|openai|azure)")
    ap.add_argument("--_child", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.mode:
        os.environ["LLM_MODE"] = args.mode
    g = json.loads(GOLDEN.read_text(encoding="utf-8"))
    if args._child:  # one suite per process: each app has its own `orchestrator` / `agents` modules
        print(json.dumps(SUITES[args.suite](g)))
        return 0
    rows, t0 = [], time.perf_counter()
    for name in (SUITES if args.suite == "all" else [args.suite]):
        cmd = [sys.executable, __file__, "--suite", name, "--_child"] + (["--mode", args.mode] if args.mode else [])
        out = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
        if out.returncode != 0:
            rows.append({"suite": name, "case": "-", "check": "suite crashed", "pass": False, "detail": out.stderr[-300:]})
            continue
        rows += json.loads(out.stdout.strip().splitlines()[-1])
    passed = sum(r["pass"] for r in rows)
    width = max(len(r["case"]) for r in rows)
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['suite']:4s} {r['case']:{width}s}  {r['check']:42s} {r['detail']}")
    print(f"\n{passed}/{len(rows)} checks passed in {time.perf_counter() - t0:.0f}s  (LLM_MODE={os.getenv('LLM_MODE', 'from .env')})")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps({"passed": passed, "total": len(rows), "rows": rows}, indent=2), encoding="utf-8")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())

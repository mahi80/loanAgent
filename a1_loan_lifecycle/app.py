"""Agentic Loan Lifecycle - Streamlit demo.

Run:  streamlit run a1_loan_lifecycle/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agents import DOCS, disbursement, portfolio  # noqa: E402
from agents.approval import AUTHORITY_LEVELS, DECISIONS  # noqa: E402
from orchestrator import PIPELINE, LoanOrchestrator, list_applications  # noqa: E402
from shared import vsm_view  # noqa: E402

st.set_page_config(page_title="Agentic Loan Lifecycle", page_icon="🏦", layout="wide")

STATUS_ICON = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "MISSING": "📄"}
REC_COLOR = {"APPROVE": "green", "APPROVE_WITH_CONDITIONS": "blue", "REQUEST_INFO": "orange",
             "REFER": "orange", "DECLINE": "red"}

if "orch" not in st.session_state:
    st.session_state.orch = LoanOrchestrator()
    st.session_state.cases = {}
    st.session_state.cp_done = {}
orch: LoanOrchestrator = st.session_state.orch
apps = {a["application_id"]: a for a in list_applications()}

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("🏦 Loan Lifecycle Agents")
    st.caption(f"LLM mode: **{orch.llm.mode}** · model `{orch.llm.model_name}`")
    app_id = st.selectbox("Loan application", list(apps),
                          format_func=lambda k: f"{k} · {apps[k]['borrower']} · ${apps[k]['amount_usd'] / 1e6:.1f}M")
    if st.button("▶ Run agent pipeline", type="primary", use_container_width=True):
        with st.spinner("Agents working..."):
            st.session_state.cases[app_id] = orch.run_until_gate(apps[app_id])
    st.divider()
    st.subheader("Ask the credit policy (RAG)")
    q = st.text_input("Question", placeholder="e.g. what is the LTV limit?")
    if q:
        for hit in orch.retriever.search(q, k=2):
            st.markdown(f"**{hit['id']} {hit['title']}** _(score {hit['score']})_\n\n{hit['text']}")
    st.divider()
    st.caption("All data is synthetic. AI outputs are decision support; credit decisions are taken by humans.")

tab_vsm, tab_flow, tab_post, tab_port, tab_audit = st.tabs(
    ["⓪ Value stream (why these agents)", "① Origination → Decision", "② Disbursement CPs",
     "③ Portfolio monitoring", "④ Audit & observability"])

# ------------------------------------------------------------------ tab 0
with tab_vsm:
    vsm_view.render(Path(__file__).resolve().parent / "data" / "vsm_steps.csv", "applications", 120,
                    "loan origination → disbursement",
                    "Approval scores low by design: the decision stays human; agents only cut queue time.")


# ------------------------------------------------------------------ tab 1
def render_flow() -> None:
    a = apps[app_id]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Borrower", a["borrower"].split(" ")[0])
    c2.metric("Amount", f"${a['amount_usd']:,.0f}")
    c3.metric("Product", a["product"].replace("_", " ").title())
    c4.metric("Tenor / Rate", f"{a['tenor_years']}y · {a['interest_rate']:.1%}")
    st.caption(f"Purpose: {a['purpose']} · Sector: {a['sector']} · RM: {a['relationship_manager']}")

    case = st.session_state.cases.get(app_id)
    if not case:
        st.info("Click **Run agent pipeline** in the sidebar to process this application.")
        return

    cols = st.columns(len(PIPELINE) + 2)
    for col, (key, name) in zip(cols, PIPELINE):
        ms = next((t["ms"] for t in case["trace"] if t["step"] == key), None)
        col.success(f"**{name.replace(' Agent', '')}**\n\n{ms} ms")
    cols[-2].warning("**Human approval**\n\n" + ("done" if "human" in case else "waiting"))
    cols[-1].info("**Decision summary**\n\n" + ("ready" if "summary_md" in case else "-"))

    with st.expander("1 · Intake Agent - document inventory & security screening", expanded=False):
        it = case["intake"]
        st.write(f"Segment: **{it['segment']}**")
        st.dataframe(pd.DataFrame([{"required document": d, "received": "✅" if d in it["received_documents"] else "❌ missing"}
                                   for d in it["required_documents"]]), hide_index=True, use_container_width=True)
        for f in it["security_flags"]:
            st.error(f"🛡️ Prompt-injection text detected in `{f['file']}`: {f['markers']} → {f['action']}")

    with st.expander("2 · Document Intelligence Agent - extracted fields with evidence", expanded=False):
        df = pd.DataFrame([{"field": k, "value": "" if v["value"] is None else str(v["value"]), "confidence": v["confidence"], "grounded": "✅" if v["grounded"] else "⚠️",
                            "source": v["source"], "evidence": v["evidence"]} for k, v in case["doc_intel"]["fields"].items()])
        st.dataframe(df, hide_index=True, use_container_width=True)
        doc = st.selectbox("View source document", a["documents"])
        if (DOCS / doc).exists():
            st.code((DOCS / doc).read_text(encoding="utf-8"), language="text")

    dd = case["dd"]
    with st.expander(f"3 · Due-Diligence Agent - missing info ({len(dd['missing']['items'])}) & policy checks", expanded=True):
        if dd["missing"]["items"]:
            st.warning("**Missing information detected**")
            st.dataframe(pd.DataFrame(dd["missing"]["items"]), hide_index=True, use_container_width=True)
            st.text_area("Draft information request (editable, human sends)", dd["missing"]["request_email"], height=220)
        m = dd["metrics"]
        mc = st.columns(5)
        mc[0].metric("Pro-forma DSCR", f"{m.get('dscr', 0):.2f}x" if "dscr" in m else "n/a")
        mc[1].metric("Stressed DSCR (-20%)", f"{m['dscr_stressed_-20pct']:.2f}x" if "dscr" in m else "n/a")
        mc[2].metric("Debt / EBITDA", f"{m['leverage']:.2f}x" if "leverage" in m else "n/a")
        mc[3].metric("LTV", f"{m['ltv']:.0%}" if "ltv" in m else "n/a")
        mc[4].metric("Vintage", f"{m.get('vintage_years', 'n/a')} yrs")
        st.dataframe(pd.DataFrame([{"": STATUS_ICON[c["status"]], "clause": c["clause"], "check": c["check"], "value": str(c["value"]),
                                    "threshold": c["threshold"], "result": c["status"], "note": c["note"]} for c in dd["checks"]]),
                     hide_index=True, use_container_width=True)
        with st.popover("Show cited policy text"):
            for c in dd["checks"]:
                st.markdown(f"**{c['clause']}** - {c['policy_text']}")

    rk = case["risk"]
    with st.expander(f"4 · Risk Agent - grade {rk['grade']}/10 ({rk['band']})", expanded=True):
        st.write(rk["summary"])
        r1, r2 = st.columns(2)
        r1.markdown("**Observations**\n" + "\n".join(f"- {o}" for o in rk["observations"]))
        r2.markdown("**Mitigants**\n" + "\n".join(f"- {o}" for o in rk["mitigants"]))
        st.dataframe(pd.DataFrame(rk["scorecard"]), hide_index=True, use_container_width=True)

    ap = case["approval"]
    with st.expander("5 · Approval / Workflow Agent - recommendation & credit memo", expanded=True):
        st.markdown(f"### Recommended next action: :{REC_COLOR[ap['recommendation']]}[{ap['recommendation'].replace('_', ' ')}]")
        st.write(f"Confidence {ap['confidence']:.0%} · Routed to **{ap['required_authority']}** (CP-6.1)")
        st.markdown("\n".join(f"- {r}" for r in ap["reasons"]))
        st.text_area("Draft credit memo", ap["memo"], height=180)
        st.markdown("**Conditions precedent**\n" + "\n".join(f"- {c}" for c in ap["conditions_precedent"]))

    st.subheader("👤 Human decision gate")
    if "human" not in case:
        with st.form("decision"):
            f1, f2, f3 = st.columns(3)
            approver = f1.text_input("Approver name", "J. Smith")
            role = f2.selectbox("Approver role", [r for r, _ in AUTHORITY_LEVELS], index=1)
            decision = f3.selectbox("Decision", DECISIONS, index=DECISIONS.index(ap["recommendation"]))
            rationale = st.text_area("Rationale (mandatory if overriding the agent)")
            if st.form_submit_button("Record decision", type="primary"):
                try:
                    orch.record_decision(case, decision, approver, role, rationale)
                    st.rerun()
                except (PermissionError, ValueError) as e:
                    st.error(str(e))
    else:
        h = case["human"]
        (st.warning if h["override"] else st.success)(
            f"{h['decision']} by {h['approver']} ({h['role']}) - {'agent overridden' if h['override'] else 'agent recommendation accepted'}")
        st.subheader("📄 Auditable decision summary")
        st.download_button("Download summary (.md)", case["summary_md"], file_name=f"{case['id']}_decision_summary.md")
        st.markdown(case["summary_md"])


with tab_flow:
    render_flow()

# ------------------------------------------------------------------ tab 2
with tab_post:
    approved = {k: v for k, v in st.session_state.cases.items() if v.get("human", {}).get("decision", "").startswith("APPROVE")}
    if not approved:
        st.info("Approve an application in tab ① to start condition-precedent tracking.")
    for cid, case in approved.items():
        st.subheader(f"{cid} · {case['application']['borrower']}")
        done = st.session_state.cp_done.setdefault(cid, set())
        for cp in case["approval"]["conditions_precedent"]:
            if st.checkbox(cp, value=cp in done, key=f"{cid}-{cp}"):
                done.add(cp)
            else:
                done.discard(cp)
        res = disbursement.run(case, done)
        (st.success if res["ready"] else st.warning)(res["status"])

# ------------------------------------------------------------------ tab 3
with tab_port:
    df = portfolio.scan()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Loans monitored", len(df))
    k2.metric("Exposure", f"${df.outstanding_usd.sum() / 1e6:.1f}M")
    k3.metric("Red", int((df.ews_rag == "Red").sum()))
    k4.metric("Amber", int((df.ews_rag == "Amber").sum()))
    color = {"Red": "🔴", "Amber": "🟠", "Green": "🟢"}
    df_show = df.assign(EWS=df.ews_rag.map(color))[["EWS", "loan_id", "borrower", "sector", "outstanding_usd",
                                                     "dscr_q1", "dscr_q2", "dscr_q3", "dscr_covenant", "leverage_q3",
                                                     "days_past_due", "signals"]]
    st.dataframe(df_show.sort_values("EWS"), hide_index=True, use_container_width=True)
    st.subheader("Agent early-warning notes (Red accounts)")
    for _, r in df[df.ews_rag == "Red"].iterrows():
        st.error(f"**{r.loan_id} {r.borrower}** - {portfolio.narrative(r.to_dict(), orch.llm)}")

# ------------------------------------------------------------------ tab 4
with tab_audit:
    st.write(f"Hash-chain integrity: **{'✅ valid' if orch.audit.verify_chain() else '❌ broken'}** · log `{orch.audit.path.name}`")
    entries = orch.audit.entries()
    if entries:
        st.dataframe(pd.DataFrame([{"ts": e["ts"], "case": e["case_id"], "actor": e["actor"], "action": e["action"],
                                    "model": e["model"], "hash": e["record_hash"][:12]} for e in entries[::-1]]),
                     hide_index=True, use_container_width=True)
    st.subheader("LLM telemetry")
    if orch.llm.telemetry:
        st.dataframe(pd.DataFrame([t.__dict__ for t in orch.llm.telemetry]), hide_index=True, use_container_width=True)

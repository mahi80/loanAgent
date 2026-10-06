"""Chemical Demand Prediction + Agentic Response - Streamlit demo.

Run:  streamlit run a2_chem_demand/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from orchestrator import ROLES, DemandResponseOrchestrator  # noqa: E402
from shared import vsm_view  # noqa: E402

st.set_page_config(page_title="Demand Sensing + Agentic Response", page_icon="🧪", layout="wide")


def md(text: str) -> str:
    """Escape $ so Streamlit does not render currency as LaTeX."""
    return text.replace("$", "\\$")


if "orch" not in st.session_state:
    o = DemandResponseOrchestrator()
    with st.spinner("Running demand-sensing model..."):
        o.sense()
    st.session_state.orch = o
    st.session_state.cases = {}
orch: DemandResponseOrchestrator = st.session_state.orch
S = orch.sensing

with st.sidebar:
    st.title("🧪 Demand → Action Agents")
    st.caption(f"LLM mode: **{orch.llm.mode}** · `{orch.llm.model_name}`")
    st.metric("Data as of", str(S.as_of.date()))
    st.metric("Open deviation alerts", len(orch.alerts))
    if st.button("↻ Re-run sensing", use_container_width=True):
        orch.sense()
        st.session_state.cases = {}
        st.rerun()
    st.divider()
    st.caption("All data synthetic (data/generate_synthetic.py). Agents recommend; planners approve; "
               "ERP transactions are mocked.")

t_opp, t_vsm, t_fc, t_act, t_aud = st.tabs(["⓪ Opportunity map", "① Value stream", "② Demand sensing",
                                            "③ Agentic response", "④ Audit & observability"])

# ------------------------------------------------------------------ opportunity map
with t_opp:
    opp = pd.read_csv(HERE / "data" / "opportunities.csv")
    opp["priority_score"] = opp.value_score * opp.feasibility_score
    opp = opp.sort_values(["wave", "priority_score"], ascending=[True, False])
    c1, c2 = st.columns([3, 2])
    with c2:
        fig = px.scatter(opp, x="feasibility_score", y="value_score", size="priority_score", color=opp.wave.astype(str),
                         text="id", hover_name="use_case", size_max=45,
                         labels={"feasibility_score": "Feasibility (data, tech, change) →", "value_score": "Business value →",
                                 "color": "Wave"})
        fig.update_traces(textposition="middle center")
        fig.add_hline(y=3.5, line_dash="dot")
        fig.add_vline(x=3.5, line_dash="dot")
        fig.update_layout(height=430, xaxis_range=[1, 5.6], yaxis_range=[1, 5.6], title="Value × feasibility")
        st.plotly_chart(fig, use_container_width=True)
        st.success("**Selected for prototype: UC1 Demand sensing + agentic response.** Highest value × feasibility, "
                   "removes the #1 VSM bottleneck (deviation detection), and its data foundation is reused by UC2/UC3.")
    with c1:
        st.dataframe(opp[["id", "use_case", "value_score", "feasibility_score", "priority_score", "wave", "kpi",
                          "expected_benefit"]], hide_index=True, use_container_width=True, height=300)
    st.subheader("Use-case cards")
    cols = ["business_problem", "ai_agent_approach", "data_required", "action_taken", "human_involvement", "kpi",
            "expected_benefit"]
    for _, r in opp.iterrows():
        with st.expander(f"{r.id} · {r.use_case}  (wave {r.wave}, score {r.priority_score})"):
            for c in cols:
                st.markdown(f"**{c.replace('_', ' ').title()}:** {r[c]}")

# ------------------------------------------------------------------ value stream
with t_vsm:
    vsm_view.render(HERE / "data" / "vsm_steps.csv", "demand exceptions", 120,
                    "demand exception → replenishment action (S&OP / planning)",
                    "S&OP approval scores low by design: planners decide; agents route exceptions instead of waiting for the monthly meeting.")

# ------------------------------------------------------------------ demand sensing
with t_fc:
    k = st.columns(4)
    k[0].metric("Sensing WMAPE (4-wk, backtest)", f"{S.mape_model:.1%}")
    k[1].metric("Stat baseline (MA13)", f"{S.mape_baseline:.1%}")
    k[2].metric("Frozen S&OP plan", f"{S.mape_plan:.1%}")
    k[3].metric("Error reduction vs plan", f"{1 - S.mape_model / S.mape_plan:.0%}")
    st.caption("Backtest over the last 16 weekly origins, trained strictly on earlier data. Model: gradient boosting "
               "on lags, seasonality, regional PMI, Brent and construction index, blended 50/50 with the 4-week run-rate.")
    f = S.frame
    a, b = st.columns(2)
    sku = a.selectbox("SKU", sorted(f.sku.unique()), index=sorted(f.sku.unique()).index("EPX-200"))
    region = b.selectbox("Region", sorted(f.region.unique()), index=sorted(f.region.unique()).index("APAC"))
    g = f[(f.sku == sku) & (f.region == region)]
    fig = go.Figure()
    fig.add_scatter(x=g.week, y=g.qty_t, name="Actual weekly demand (t)", line_color="#424242")
    fig.add_scatter(x=g.week, y=g.plan / 4, name="Frozen S&OP plan (t/wk)", line_dash="dash", line_color="#ef6c00")
    fig.add_scatter(x=g.week, y=g.backtest_pred / 4, name="Backtest sensing (t/wk)", line_color="#1565c0")
    last = g.iloc[-1]
    future = pd.date_range(last.week + pd.Timedelta(weeks=1), periods=4, freq="W-MON")
    fig.add_scatter(x=future, y=[last.sensed / 4] * 4, name="Sensed next 4 wks", line=dict(color="#c62828", width=4))
    fig.add_scatter(x=future, y=[last.plan / 4] * 4, name="Plan next 4 wks", line=dict(color="#ef6c00", width=4, dash="dot"))
    fig.update_layout(height=420, legend_orientation="h", title=f"{sku} · {region}")
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Backtest accuracy by series"):
        st.dataframe(S.backtest.round(3), hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ agentic response
with t_act:
    st.subheader("Deviation Agent - significant deviations vs S&OP plan")
    al = orch.alerts
    st.dataframe(al[["sku", "name", "region", "direction", "deviation_pct", "actual_dev_pct", "z_score", "gap_t",
                     "margin_at_stake_usd", "severity", "evidence"]].round(2), hide_index=True, use_container_width=True)
    idx = st.selectbox("Investigate alert", range(len(al)),
                       format_func=lambda i: f"{al.sku[i]} · {al.region[i]} · {al.direction[i]} · ${al.margin_at_stake_usd[i]:,.0f}")
    key = f"{al.sku[idx]}-{al.region[idx]}"
    if st.button("▶ Run response agents", type="primary"):
        st.session_state.cases[key] = orch.analyse(idx)
    case = st.session_state.cases.get(key)
    if case:
        im, cons, rec = case["impact"], case["constraints"], case["recommendation"]
        st.markdown("#### Impact Agent - who and how much")
        i1, i2 = st.columns([2, 3])
        i1.metric("Revenue exposure (4 wks)", f"${im['revenue_at_risk_usd']:,.0f}")
        i1.metric("Primary driver", im["primary_driver"], f"{im['driver_share']:.0%} of change", delta_color="off")
        i1.info(md(im["narrative"]))
        i2.plotly_chart(px.bar(im["customers"], x="customer", y="delta_t_wk", color="change_pct",
                               color_continuous_scale="RdBu", title="Change in weekly demand by customer (t/wk)")
                        .update_layout(height=320), use_container_width=True)
        st.markdown("#### Constraint Agent - inventory, capacity, lanes")
        p = cons["position"]
        c = st.columns(4)
        c[0].metric(p["dc"] + " available", f"{p['available_t']:,.0f} t")
        c[1].metric("Sensed demand 4 wks", f"{p['sensed_4wk_t']:,.0f} t")
        c[2].metric("Projected vs safety stock", f"{p['gap_vs_ss_t']:+,.0f} t")
        c[3].metric("Weeks of cover", p["weeks_cover"])
        n1, n2 = st.columns(2)
        n1.dataframe(cons["network"], hide_index=True, use_container_width=True)
        n2.dataframe(cons["plants"][["plant", "region", "weekly_capacity_t", "planned_t_per_week", "utilisation",
                                     "free_capacity_4wk_t", "lead_time_weeks"]], hide_index=True, use_container_width=True)
        st.markdown("#### Recommender Agent - least-cost response plan")
        st.info(md(rec["rationale"]))
        t = rec["totals"]
        m = st.columns(4)
        m[0].metric("Gap to close", f"{t['need_t']:,} t")
        m[1].metric("Execution cost", f"${t['cost_usd']:,.0f}")
        m[2].metric("Margin protected / value", f"${t['benefit_usd']:,.0f}")
        m[3].metric("Margin forgone (deferred)", f"${t.get('margin_forgone_usd', 0):,.0f}")
        with st.expander(f"All {len(rec['options'])} options evaluated"):
            st.dataframe(pd.DataFrame(rec["options"]), hide_index=True, use_container_width=True)

        st.markdown(f"#### 👤 Human approval - routed to **{rec['approval_level']}**")
        if "human" not in case:
            plan_df = pd.DataFrame(rec["plan"]).assign(include=True)
            edited = st.data_editor(plan_df[["include", "type", "action", "qty_t", "cost_usd", "benefit_usd", "lead_time_days"]],
                                    disabled=["type", "action", "cost_usd", "benefit_usd", "lead_time_days"],
                                    hide_index=True, use_container_width=True, key=f"ed-{key}")
            with st.form(f"approve-{key}"):
                f1, f2 = st.columns(2)
                approver = f1.text_input("Approver", "L. Chen")
                role = f2.selectbox("Role", ROLES, index=ROLES.index(rec["approval_level"]))
                rationale = st.text_area("Rationale (required if editing or rejecting)")
                b1, b2 = st.columns(2)
                go_ = b1.form_submit_button("✅ Approve & trigger actions", type="primary")
                no_ = b2.form_submit_button("✖ Reject")
            if go_ or no_:
                actions = []
                for orig, (_, row) in zip(rec["plan"], edited.iterrows()):
                    if row.include:
                        scale = row.qty_t / orig["qty_t"] if orig["qty_t"] else 1
                        actions.append({**orig, "qty_t": int(row.qty_t), "cost_usd": round(orig["cost_usd"] * scale),
                                        "action": orig["action"] if scale == 1 else f"{orig['action']} [qty edited to {int(row.qty_t)} t]"})
                try:
                    orch.decide(case, approver, role, actions, rationale, reject=bool(no_))
                    st.rerun()
                except (PermissionError, ValueError) as e:
                    st.error(md(str(e)))
        else:
            h = case["human"]
            (st.error if h["decision"] == "REJECTED" else st.success)(
                md(f"{h['decision']} by {h['approver']} ({h['role']}) at {h['ts']} · approved cost ${h['approved_cost_usd']:,.0f}"))
            if case.get("executed"):
                st.markdown("#### ⚙️ Executor Agent - workflow triggered (mock SAP / IBP / notifications)")
                st.dataframe(pd.DataFrame(case["executed"]), hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ audit
with t_aud:
    st.write(f"Hash-chain integrity: **{'✅ valid' if orch.audit.verify_chain() else '❌ broken'}**")
    e = orch.audit.entries()
    if e:
        st.dataframe(pd.DataFrame([{"ts": x["ts"], "case": x["case_id"], "actor": x["actor"], "action": x["action"],
                                    "model": x["model"], "hash": x["record_hash"][:12]} for x in e[::-1]]),
                     hide_index=True, use_container_width=True)
    st.subheader("LLM telemetry")
    if orch.llm.telemetry:
        st.dataframe(pd.DataFrame([t.__dict__ for t in orch.llm.telemetry]), hide_index=True, use_container_width=True)

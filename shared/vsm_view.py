"""Reusable Streamlit 'Value Stream' tab for any process CSV."""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from shared import vsm


def render(csv: Path, unit: str, default_demand: int, process: str, note: str = "") -> None:
    st.caption(f"Lean Six Sigma value stream map - {process}. Step times are MOCKED assumptions "
               f"(`{csv.parent.name}/{csv.name}`); takt, PCE, capacity and priority are computed.")
    v1, v2, v3 = st.columns(3)
    demand = v1.number_input(f"Demand ({unit} / month)", 10, 1000, default_demand, 10, key=f"d-{csv}")
    days = v2.number_input("Working days / month", 15, 26, 21, key=f"wd-{csv}")
    hrs = v3.number_input("Available hours / day", 5.0, 10.0, 7.5, 0.5, key=f"h-{csv}")
    a = vsm.Assumptions(demand, days, hrs)
    df = vsm.load(csv)
    view = st.radio("State", ["Current", "Future (with agents)"], horizontal=True, key=f"v-{csv}")
    cur = vsm.state(df, a, future=view.startswith("Future"))
    sm = vsm.summary(cur, a)
    k = st.columns(5)
    k[0].metric("Takt time", f"{a.takt_h:.2f} h", f"{a.takt_h * 60:.0f} min / {unit.rstrip('s')}", delta_color="off")
    k[1].metric("Lead time", f"{sm['lead_time_d']} d")
    k[2].metric("PCE (VA / lead time)", f"{sm['pce']:.1%}")
    k[3].metric("Steps over takt", sm["steps_over_takt"])
    k[4].metric("Capacity (bottleneck)", f"{sm['capacity_per_month']}/mo", f"{sm['capacity_per_month'] - demand:+d} vs demand")
    # horizontal bars: long step names sit on the y-axis and can never overlap
    labels = [f"{n}. {t}" for n, t in zip(cur.step_no, cur.step)]

    def fl(col):  # plain floats: plotly 7 binary int8 arrays break stacking in Streamlit's plotly.js
        return [float(v) for v in cur[col]]

    layout = dict(height=430, margin=dict(t=80, l=10, r=10, b=40),
                  yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
    g1, g2 = st.columns(2)
    fig = go.Figure()
    fig.add_bar(name="VA (h)", y=labels, x=fl("va_h"), orientation="h", marker_color="#2e7d32")
    fig.add_bar(name="NVA touch (h)", y=labels, x=fl("nva_h"), orientation="h", marker_color="#ef6c00")
    fig.add_bar(name="Wait (h)", y=labels, x=fl("wait_h"), orientation="h", marker_color="#bdbdbd")
    fig.update_layout(barmode="stack", title="Time per step: VA vs NVA vs wait", xaxis_title="hours per unit", **layout)
    g1.plotly_chart(fig, use_container_width=True)
    fig2 = go.Figure()
    fig2.add_bar(y=labels, x=fl("eff_ct_h"), orientation="h", name="Effective CT (h)", showlegend=False,
                 marker_color=["#c62828" if o else "#1565c0" for o in cur.over_takt])
    fig2.add_vline(x=a.takt_h, line_dash="dash", annotation_text=f"Takt {a.takt_h:.2f} h", annotation_position="top")
    fig2.update_layout(title="Effective cycle time vs takt (red = bottleneck)", xaxis_title="hours", **layout)
    g2.plotly_chart(fig2, use_container_width=True)
    st.subheader("Automation Priority Index - which steps get agents first")
    st.caption("API = NVA hours (touch + wait) × agent feasibility (1-5) × max(1, CT ÷ takt) ÷ 10. " + note)
    st.dataframe(vsm.priority(df, a), hide_index=True, use_container_width=True)
    st.subheader("Before vs after (mocked)")
    st.dataframe(vsm.before_after(df, a).astype(str), hide_index=True, use_container_width=True)

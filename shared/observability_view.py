"""Streamlit trace viewer: recent traces + span waterfall (shared by both apps)."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shared.observability import TRACE_FILE, load_traces

COLORS = {"llm.call": "#6A4C93", "agent": "#2A9D8F", "root": "#1F3A5F"}


def render(prefixes: tuple[str, ...]) -> None:
    st.subheader("Traces (OpenTelemetry-style spans)")
    st.caption(f"Every run is a trace: pipeline → agent steps → LLM calls. Written to `{TRACE_FILE.name}`; exported "
               "over OTLP to Langfuse / X-Ray / App Insights when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.")
    spans = [s for s in load_traces() if s["name"].startswith(prefixes) or s["name"].startswith(("agent.", "llm."))]
    roots = [s for s in spans if s["parent_id"] is None and s["name"].startswith(prefixes)]
    if not roots:
        st.info("No traces yet - run a pipeline.")
        return
    roots = sorted(roots, key=lambda s: s["start"], reverse=True)[:25]
    summary = []
    for r in roots:
        kids = [s for s in spans if s["trace_id"] == r["trace_id"]]
        llm = [s for s in kids if s["name"] == "llm.call"]
        summary.append({"trace_id": r["trace_id"], "started": r["start"][11:19], "name": r["name"],
                        "case": r["attrs"].get("case", "-"), "actor": r["attrs"].get("actor", "-"),
                        "duration_ms": r["duration_ms"], "llm_calls": len(llm),
                        "llm_fallbacks": sum(1 for s in llm if s["attrs"].get("fallback")),
                        "tokens": sum((s["attrs"].get("prompt_tokens", 0) or 0) + (s["attrs"].get("completion_tokens", 0) or 0)
                                      for s in llm),
                        "status": r["status"]})
    st.dataframe(pd.DataFrame(summary), hide_index=True, use_container_width=True)
    pick = st.selectbox("Inspect trace", [s["trace_id"] for s in summary],
                        format_func=lambda t: next(f"{s['started']} · {s['name']} · {s['case']}" for s in summary
                                                   if s["trace_id"] == t))
    tr = sorted([s for s in spans if s["trace_id"] == pick], key=lambda s: s["start"])
    t0 = datetime.fromisoformat(tr[0]["start"])
    rows = []
    for s in tr:
        kind = "llm.call" if s["name"] == "llm.call" else "agent" if s["name"].startswith("agent.") else "root"
        label = s["name"] if kind != "llm.call" else f"   llm · {s['attrs'].get('agent', '')}"
        rows.append((label, (datetime.fromisoformat(s["start"]) - t0).total_seconds() * 1000, s["duration_ms"], kind))
    fig = go.Figure()
    fig.add_bar(y=[r[0] for r in rows], x=[float(r[2]) for r in rows], base=[float(r[1]) for r in rows],
                orientation="h", marker_color=[COLORS[r[3]] for r in rows],
                hovertemplate="%{y}<br>start +%{base:.0f} ms<br>duration %{x:.0f} ms<extra></extra>")
    fig.update_layout(height=max(260, 26 * len(rows)), margin=dict(l=10, r=10, t=30, b=30),
                      yaxis=dict(autorange="reversed"), xaxis_title="ms from trace start", title="Span waterfall")
    st.plotly_chart(fig, use_container_width=True)

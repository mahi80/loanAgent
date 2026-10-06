"""Generates every diagram / chart used in the two decks (PNG, 200 dpi).

Numbers come from the same engines the prototypes use (shared/vsm.py,
a2_chem_demand/forecasting.py, the orchestrators) - nothing is hand-drawn.

Run:  python deliverables/diagrams.py
"""
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent / "img"
OUT.mkdir(exist_ok=True)
os.environ.setdefault("LLM_MODE", "mock")

from shared import vsm  # noqa: E402

NAVY, TEAL, ORANGE, AMBER, GREY, GREEN, RED, LIGHT, BLUE, PURPLE = (
    "#1F3A5F", "#2A9D8F", "#E76F51", "#F4A261", "#6C757D", "#2E7D32", "#C62828", "#F1F5F9", "#1565C0", "#6A4C93")
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})


def box(ax, x, y, w, h, text, fc=LIGHT, ec=NAVY, color="#111", size=9, bold=False, r=0.6, lw=1.2, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.02,rounding_size={r}", fc=fc, ec=ec, lw=lw, ls=ls))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, color=color,
            fontweight="bold" if bold else "normal", wrap=True, linespacing=1.25)


def arrow(ax, x1, y1, x2, y2, color=NAVY, lw=1.4, style="-|>", ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=12, color=color, lw=lw,
                                 linestyle=ls, connectionstyle=f"arc3,rad={rad}"))


def canvas(w=16, h=9, xlim=100, ylim=56):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, xlim)
    ax.set_ylim(0, ylim)
    ax.axis("off")
    return fig, ax


def save(fig, name):
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", name)


# ============================================================== architecture
def architecture(title, rows, cross, name, footer):
    fig, ax = canvas()
    ax.text(0, 55, title, fontsize=17, fontweight="bold", color=NAVY, va="top")
    top = y = 51.5
    for label, items, color, height in rows:
        ax.add_patch(FancyBboxPatch((0, y - height), 80.5, height, boxstyle="round,pad=0.02,rounding_size=0.8",
                                    fc=color + "18", ec=color, lw=1.2))
        ax.text(1.0, y - height / 2, label, fontsize=10, fontweight="bold", color=color, va="center", ha="left", wrap=True)
        n = len(items)
        x0, wtot = 14.5, 65.0
        bw = (wtot - (n - 1) * 0.9) / n
        for i, it in enumerate(items):
            box(ax, x0 + i * (bw + 0.9), y - height + 0.9, bw, height - 1.8, it, fc="white", ec=color, size=8)
        y -= height + 1.0
    # cross-cutting column
    ax.add_patch(FancyBboxPatch((82, y + 1.0), 18, top - y - 1.0, boxstyle="round,pad=0.02,rounding_size=0.8",
                                fc=NAVY + "10", ec=NAVY, lw=1.2))
    ax.text(91, top - 1.1, "Cross-cutting controls", ha="center", fontsize=10, fontweight="bold", color=NAVY)
    ch = (top - y - 4.0) / len(cross)
    for i, (head, body, c) in enumerate(cross):
        yy = top - 2.3 - (i + 1) * ch
        box(ax, 82.8, yy + 0.3, 16.4, ch - 0.6, f"$\\bf{{{head}}}$\n{body}", fc="white", ec=c, size=7.4)
    ax.text(0, y + 0.2, footer, fontsize=8, color=GREY, va="top", style="italic")
    save(fig, name)


def a1_architecture():
    rows = [
        ("Users &\nchannels", ["RM / borrower portal\n(application + uploads)", "Credit analyst workbench\n(agent trace, evidence)",
                               "Approvers\n(Teams / LOS approval card)", "Ops & monitoring\n(CP + EWS dashboards)"], BLUE, 6.0),
        ("Orchestration", ["Agent orchestrator\n(state graph: LangGraph /\nAI Foundry Agent Service)", "Human-in-the-loop gate\n(authority matrix CP-6.1,\noverride + rationale)",
                           "Workflow & SLA engine\n(Durable Functions /\nLOS workflow)", "Audit writer\n(hash-chained events)"], NAVY, 7.0),
        ("Agents", ["Intake", "Document\nIntelligence", "Due-\nDiligence", "Risk", "Approval /\nWorkflow", "Disbursement\n/ CP", "Portfolio\nMonitoring"], TEAL, 6.0),
        ("Model &\nknowledge", ["Azure OpenAI (GPT-4o)\nvia AI gateway (APIM):\nJSON mode, prompt registry", "Deterministic engines\nratios, rules, scorecard\n(no LLM math)",
                                "RAG: Azure AI Search\npolicy, product manuals,\nprecedent memos", "Doc Intelligence OCR\n+ grounding check\n(value must be in source)"], PURPLE, 7.0),
        ("Integration\n& data", ["APIM + event bus\n(Service Bus / Kafka)", "LOS (nCino/Finastra),\ncore banking, CRM",
                                 "Bureau, KYC, sanctions\n& adverse-media APIs", "DMS + e-mail (Graph)\nunstructured docs", "Lakehouse (Fabric /\nDatabricks) - features,\nportfolio history"], ORANGE, 7.0),
    ]
    cross = [
        ("Security", "Entra ID, RBAC, Key Vault,\nprivate endpoints, data\nresidency, PII masking", RED),
        ("Human\\ in\\ loop", "Agents recommend; credit\ndecisions by authorised\nhumans only", BLUE),
        ("Auditability", "Immutable hash-chained log,\ninputs hash, model version,\ndecision summary", NAVY),
        ("Observability", "OpenTelemetry traces, token\n& latency per agent, eval\nsets, drift alerts", TEAL),
        ("Responsible\\ AI", "No protected attributes,\nprompt-injection shield,\nexplanations, MRM review", PURPLE),
    ]
    architecture("Agentic Loan Lifecycle - target architecture", rows, cross, "a1_architecture.png",
                 "Prototype: Python agents + Streamlit, Azure OpenAI (mock fallback), TF-IDF RAG, JSONL audit chain. "
                 "Production path shown in boxes.")


def a2_architecture():
    rows = [
        ("Users &\nchannels", ["Demand planner cockpit\n(alerts, drill-down)", "S&OP lead approvals\n(Teams adaptive card)",
                               "Logistics & plant\nschedulers", "Sales / customer service\n(notifications)"], BLUE, 6.0),
        ("Orchestration", ["Agent orchestrator\n(daily sensing trigger +\nevent-driven exceptions)", "Human approval gate\n(value thresholds,\nedit / reject + rationale)",
                           "Action workflow\n(SAP BTP / Power\nAutomate)", "Audit writer\n(hash-chained events)"], NAVY, 7.0),
        ("Agents", ["Deviation", "Impact\n(SKU/region/\ncustomer)", "Constraint\n(inventory,\ncapacity)", "Recommender\n(options +\ncost)", "Executor\n(SAP/IBP)", "Notification"], TEAL, 6.0),
        ("Analytics,\nML & LLM", ["Demand-sensing model\n(GBM / TFT) + MLflow\nregistry & backtests", "Optimisation\n(least-cost plan;\nOR-Tools MILP later)",
                                  "Azure OpenAI\nnarratives, Q&A,\nexplanations", "RAG: planning policy,\nSOPs, customer\ncontracts"], PURPLE, 7.0),
        ("Integration\n& data", ["SAP S/4 (orders, stock,\nproduction) via OData /\nBAPI on SAP BTP", "SAP IBP / APO\n(plans, consensus)",
                                 "TMS / carriers,\nCRM promos", "External signals: PMI,\nfeedstock, weather", "Lakehouse + feature\nstore (Databricks /\nFabric)"], ORANGE, 7.0),
    ]
    cross = [
        ("Security", "Entra ID, SAP role mapping,\nleast-privilege service\nusers, Key Vault", RED),
        ("Human\\ in\\ loop", "Planner approves all ERP\nwrites; S&OP lead above\n$50k (configurable)", BLUE),
        ("Auditability", "Every alert, option, edit\nand SAP txn logged with\nhash chain", NAVY),
        ("Observability", "Forecast accuracy (WMAPE),\nalert precision, agent\nlatency, action outcomes", TEAL),
        ("Responsible\\ AI", "LLM never sets quantities;\ndeterministic costs; explain\nevery recommendation", PURPLE),
    ]
    architecture("Demand Prediction + Agentic Response - target architecture", rows, cross, "a2_architecture.png",
                 "Prototype: synthetic SAP-like CSVs, scikit-learn GBM, Python agents + Streamlit, mocked SAP/IBP payloads.")


# ============================================================== agent flow
def flow(name, title, steps, gate_idx, notes):
    fig, ax = canvas(16, 5.2, 100, 30)
    ax.text(0, 29.5, title, fontsize=15, fontweight="bold", color=NAVY, va="top")
    n = len(steps)
    w = (100 - (n - 1) * 1.6) / n
    for i, (head, body) in enumerate(steps):
        x = i * (w + 1.6)
        human = i == gate_idx
        fc = AMBER + "40" if human else (TEAL + "22" if i < gate_idx else GREEN + "22")
        ec = ORANGE if human else (TEAL if i < gate_idx else GREEN)
        box(ax, x, 11, w, 12, f"$\\bf{{{head}}}$\n\n{body}", fc=fc, ec=ec, size=7.6, lw=2 if human else 1.2)
        if i < n - 1:
            arrow(ax, x + w + 0.1, 17, x + w + 1.5, 17)
    for i, t in enumerate(notes):
        ax.text(0, 8.5 - i * 2.6, t, fontsize=9, color=GREY)
    save(fig, name)


def a1_flow():
    flow("a1_agent_flow.png", "Prototype workflow - application to auditable decision", [
        ("Application", "JSON intake\nsegment, product\ndoc checklist"),
        ("Ingest\\ docs", "Intake Agent\ninventory +\ninjection screen"),
        ("Extract", "Doc Intel Agent\nfields, confidence,\nevidence, grounding"),
        ("Missing\\ info", "DD Agent\ndoc/field gaps\n+ draft request"),
        ("Policy\\ checks", "Rules + RAG\nDSCR, LTV, KYC\ncited clauses"),
        ("Risk", "Risk Agent\ngrade 1-10,\nobservations"),
        ("Next\\ action", "Approval Agent\nrecommend +\nroute authority"),
        ("Human\\ decision", "Approve / override\n(rationale), authority\nenforced"),
        ("Audit\\ summary", "Decision record,\nhash chain,\ndownloadable"),
    ], 7, ["Teal = agents (decision support)   Amber = human control point   Green = system of record.",
           "Demo cases: APP-1001 clean -> APPROVE | APP-1002 incomplete -> REQUEST INFO (draft e-mail) | "
           "APP-1003 DSCR 0.59x, LTV 93%, PEP, adverse media, prompt injection -> DECLINE, Board authority."])


def a2_flow():
    flow("a2_agent_flow.png", "Prototype workflow - demand signal to approved action", [
        ("Data", "Orders, inventory,\ncapacity, PMI,\nBrent, construction"),
        ("Sense", "GBM 4-wk demand\n+ run-rate blend\nbacktested"),
        ("Detect", "Deviation Agent\n>15% fwd or >20%\nactual & |z|>1.5"),
        ("Impact", "Impact Agent\nSKU/region/\ncustomer drivers"),
        ("Constraints", "Constraint Agent\nDC stock, SS,\nplant capacity, lanes"),
        ("Recommend", "Recommender\nleast-cost plan,\ncost vs margin"),
        ("Human\\ approval", "Planner / S&OP lead\nedit qty, approve,\nreject + rationale"),
        ("Execute", "Executor Agent\nSTO, planned order,\nIBP update, notify"),
    ], 6, ["Teal = agents   Amber = human control point   Green = system of record (SAP / IBP, mocked).",
           "Demo: EPX-200 APAC +36% sensed (+69% actual) -> Pacific Coatings project ramp -> 752 t gap at DC-Singapore -> "
           "transfer + pull-forward + expedite + allocation -> S&OP lead approves -> SAP payloads."])


# ============================================================== VSM block diagram
def vsm_block(csv, demand, title, name, unit, human_step):
    a = vsm.Assumptions(demand)
    df = vsm.load(csv)
    cur, fut = vsm.state(df, a), vsm.state(df, a, True)
    sc, sf = vsm.summary(cur, a), vsm.summary(fut, a)
    pr = vsm.priority(df, a)
    fig, ax = canvas(18, 9.4, 100, 60)
    ax.text(0, 59.5, title, fontsize=16, fontweight="bold", color=NAVY, va="top")
    ax.text(0, 56.6, f"Demand {demand} {unit}/month  |  Takt {a.takt_h:.2f} h ({a.takt_h * 60:.0f} min)  |  Lead time "
                     f"{sc['lead_time_d']} d  |  PCE {sc['pce']:.1%}  |  {sc['steps_over_takt']} steps over takt  |  "
                     f"Capacity {sc['capacity_per_month']}/month (bottleneck: {sc['bottleneck']})",
            fontsize=10, color=GREY, va="top")
    n = len(cur)
    w, gap, x0 = 9.6, 1.35, 0.5
    sx = {int(r.step_no): x0 + i * (w + gap) for i, r in enumerate(cur.itertuples())}
    # process boxes
    for i, r in enumerate(cur.itertuples()):
        x = sx[int(r.step_no)]
        bn = r.over_takt
        txt = (f"$\\bf{{{int(r.step_no)}}}$ {textwrap.fill(r.step, 17)}\n\nVA {r.va_h:g}h | NVA {r.nva_h:g}h\nWait {r.wait_d:g}d | FTE {r.fte}\n"
               f"CT {r.eff_ct_h:.2f}h {'> takt' if bn else '<= takt'}")
        box(ax, x, 26, w, 12, txt, fc=(RED + "22") if bn else "white", ec=RED if bn else NAVY, size=7.2, lw=2 if bn else 1.2)
        if i < n - 1:
            arrow(ax, x + w, 32, x + w + gap, 32)
    # agent overlay (top 5 by API) + human gate
    # top 5 by API, plus any bottleneck step so every red box gets an agent
    over = set(cur.loc[cur.over_takt, "step_no"].astype(int))
    top = pr[(pr["rank"] <= 5) | pr.step_no.isin(over)]
    top = top[top.step_no != human_step]
    for k, r in enumerate(top.itertuples()):
        x = sx[int(r.step_no)]
        box(ax, x - 0.3, 43 + (k % 2) * 6.2, w + 0.6, 5.2, f"$\\bf{{P{r.rank}}}$  API {r.api}\n{textwrap.fill(r.agent, 24)}", fc=TEAL + "22",
            ec=TEAL, size=6.8)
        arrow(ax, x + w / 2, 43 + (k % 2) * 6.2, x + w / 2, 38.2, color=TEAL, ls="--")
    hx = sx[human_step]
    box(ax, hx - 0.3, 49.2 if any(int(r.step_no) == human_step for r in top.itertuples()) else 43, w + 0.6, 5.2,
        "HUMAN DECIDES\nagents: routing +\npre-read only", fc=AMBER + "50", ec=ORANGE, size=7, bold=True)
    arrow(ax, hx + w / 2, 43, hx + w / 2, 38.2, color=ORANGE, lw=2)
    # timeline ladder
    ax.text(0, 23.5, "Timeline (current state)", fontsize=9, fontweight="bold", color=NAVY)
    for r in cur.itertuples():
        x = sx[int(r.step_no)]
        ax.plot([x, x + w], [21, 21], color=GREY, lw=3)
        ax.text(x + w / 2, 21.7, f"wait {r.wait_d:g} d", ha="center", fontsize=7.5, color=GREY)
        ax.plot([x + w * 0.2, x + w * 0.8], [17.5, 17.5], color=GREEN, lw=3)
        ax.text(x + w / 2, 16.0, f"VA {r.va_h:g} h", ha="center", fontsize=7.5, color=GREEN)
        ax.plot([x, x + w * 0.2], [21, 17.5], color=GREY, lw=1)
        ax.plot([x + w * 0.8, x + w], [17.5, 21], color=GREY, lw=1)
    ax.text(99.5, 21, f"= {sc['wait_h'] / 8:g} d wait", ha="right", fontsize=8, color=GREY, va="bottom")
    ax.text(99.5, 16.0, f"= {sc['va_h']:g} h VA", ha="right", fontsize=8, color=GREEN)
    # KPI table
    ba = vsm.before_after(df, a)
    ax.text(0, 12.6, "Before vs after (mocked step times; computed KPIs)", fontsize=9, fontweight="bold", color=NAVY)
    cols = [0, 30, 42, 54]
    for j, h in enumerate(["KPI", "Before", "After", "Change"]):
        ax.text(cols[j], 10.8, h, fontsize=8.5, fontweight="bold", color=NAVY)
    for i, r in enumerate(ba.itertuples(index=False)):
        yy = 9.2 - i * 1.35
        for j, v in enumerate(r):
            ax.text(cols[j], yy, str(v), fontsize=8.2, color="#222")
    box(ax, 66, 1.0, 33.5, 10.5,
        "How to read\nVA = work the customer would pay for; NVA = manual re-keying,\nchasing, formatting; Wait = queues / hand-offs (1 d = 8 h).\n"
        "Eff. CT = (VA + NVA) / FTE; red = above takt (bottleneck).\nAPI = NVA h (touch+wait) x feasibility x max(1, CT/takt) / 10",
        fc=LIGHT, ec=GREY, size=7.6)
    save(fig, name)


def vsm_chart(csv, demand, name, title):
    a = vsm.Assumptions(demand)
    df = vsm.load(csv)
    fig, axes = plt.subplots(1, 2, figsize=(16, 5.2))
    for ax, fut, lab in ((axes[0], False, "Current"), (axes[1], True, "Future (with agents)")):
        s = vsm.state(df, a, fut)
        x = range(len(s))
        ax.bar(x, s.va_h, color=GREEN, label="VA (h)")
        ax.bar(x, s.nva_h, bottom=s.va_h, color=ORANGE, label="NVA touch (h)")
        ax.bar(x, s.wait_h, bottom=s.va_h + s.nva_h, color="#BDBDBD", label="Wait (h)")
        sm = vsm.summary(s, a)
        ax.set_title(f"{lab}: lead time {sm['lead_time_d']} d, PCE {sm['pce']:.1%}", fontsize=11, color=NAVY)
        ax.set_xticks(list(x))
        ax.set_xticklabels([f"{r.step_no}. {r.step[:18]}" for r in s.itertuples()], rotation=35, ha="right", fontsize=8)
        ax.set_ylim(0, 60)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_ylabel("hours per unit")
    axes[0].legend(frameon=False, loc="upper left")
    fig.suptitle(title, fontsize=13, color=NAVY, fontweight="bold")
    fig.tight_layout()
    save(fig, name)


def api_chart(csv, demand, name):
    a = vsm.Assumptions(demand)
    pr = vsm.priority(vsm.load(csv), a).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    colors = [TEAL if r >= len(pr) - 5 else "#B0BEC5" for r in range(len(pr))]
    ax.barh([f"{r.step}" for r in pr.itertuples()], pr.api, color=colors)
    for i, r in enumerate(pr.itertuples()):
        ax.text(r.api + 0.4, i, f"{r.api}", va="center", fontsize=8)
    ax.set_xlabel("Automation Priority Index")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Where agents go first (top 5 highlighted)", fontsize=11, color=NAVY)
    fig.tight_layout()
    save(fig, name)


# ============================================================== A2 charts
def opportunity_matrix():
    o = pd.read_csv(ROOT / "a2_chem_demand" / "data" / "opportunities.csv")
    o["score"] = o.value_score * o.feasibility_score
    fig, ax = plt.subplots(figsize=(7, 5.6))
    cmap = {1: TEAL, 2: BLUE, 3: GREY}
    jitter = {}
    for r in o.itertuples():
        key = (r.feasibility_score, r.value_score)
        dx = 0.18 * jitter.get(key, 0)
        jitter[key] = jitter.get(key, 0) + 1
        ax.scatter(r.feasibility_score + dx, r.value_score, s=r.score * 70, color=cmap[r.wave], alpha=0.8, edgecolor="white")
        ax.text(r.feasibility_score + dx, r.value_score, r.id, ha="center", va="center", fontsize=8, color="white", fontweight="bold")
    ax.axhline(3.5, ls=":", color=GREY)
    ax.axvline(3.5, ls=":", color=GREY)
    ax.set_xlim(1, 5.7)
    ax.set_ylim(1, 5.7)
    ax.set_xlabel("Feasibility (data readiness, tech, change) ->")
    ax.set_ylabel("Business value ->")
    ax.text(5.6, 5.6, "Quick wins / lighthouse", ha="right", va="top", fontsize=8, color=GREY)
    ax.text(1.1, 5.6, "Strategic bets", va="top", fontsize=8, color=GREY)
    for w, c in cmap.items():
        ax.scatter([], [], color=c, label=f"Wave {w}", s=60)
    ax.legend(frameon=False, loc="lower left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Value x feasibility (bubble = priority score)", fontsize=11, color=NAVY)
    fig.tight_layout()
    save(fig, "a2_opportunity_matrix.png")


def forecast_chart():
    sys.path.insert(0, str(ROOT / "a2_chem_demand"))
    import forecasting

    r = forecasting.run()
    g = r.frame[(r.frame.sku == "EPX-200") & (r.frame.region == "APAC")]
    g = g[g.week > g.week.max() - pd.Timedelta(weeks=52)]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    ax.plot(g.week, g.qty_t, color="#424242", lw=1.4, label="Actual weekly demand (t)")
    ax.plot(g.week, g.plan / 4, color=ORANGE, ls="--", lw=1.6, label="Frozen S&OP plan (t/wk)")
    ax.plot(g.week, g.backtest_pred / 4, color=BLUE, lw=2, label="Sensing backtest (t/wk)")
    last = g.iloc[-1]
    fw = pd.date_range(last.week + pd.Timedelta(weeks=1), periods=4, freq="W-MON")
    ax.plot(fw, [last.sensed / 4] * 4, color=RED, lw=4, label=f"Sensed next 4 wks ({(last.sensed - last.plan) / last.plan:+.0%} vs plan)")
    ax.plot(fw, [last.plan / 4] * 4, color=ORANGE, lw=4, ls=":")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title(f"EPX-200 Liquid Epoxy Resin - APAC  |  backtest WMAPE: sensing {r.mape_model:.1%} vs frozen plan "
                 f"{r.mape_plan:.1%}", fontsize=11, color=NAVY)
    fig.tight_layout()
    save(fig, "a2_forecast.png")
    return r


def impact_chart():
    sys.path.insert(0, str(ROOT / "a2_chem_demand"))
    from orchestrator import DemandResponseOrchestrator

    o = DemandResponseOrchestrator()
    o.sense()
    c = o.analyse(0)
    cu = c["impact"]["customers"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [1, 1.3]})
    axes[0].bar(cu.customer.str.replace(" ", "\n", n=1), cu.delta_t_wk, color=[RED if v > 40 else BLUE for v in cu.delta_t_wk])
    axes[0].set_title("Impact Agent: change in weekly demand by customer (t/wk)", fontsize=10, color=NAVY)
    axes[0].spines[["top", "right"]].set_visible(False)
    p = pd.DataFrame(c["recommendation"]["plan"])
    p = p[p.type != "PLAN_UPDATE"]
    axes[1].barh(p.type, p.qty_t, color=[TEAL, BLUE, ORANGE, GREY][: len(p)])
    for i, r in enumerate(p.itertuples()):
        cost = f"${r.cost_usd:,.0f}" if r.cost_usd else f"margin forgone ${getattr(r, 'margin_forgone_usd', 0) or 0:,.0f}"
        axes[1].text(r.qty_t + 5, i, f"{r.qty_t} t, {r.lead_time_days} d, {cost}", va="center", fontsize=8)
    axes[1].set_xlim(0, max(p.qty_t) * 1.9)
    axes[1].set_title("Recommender: least-cost plan to close 752 t gap", fontsize=10, color=NAVY)
    axes[1].spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    save(fig, "a2_impact_plan.png")
    return c


def a1_lifecycle():
    fig, ax = canvas(16, 4.6, 100, 26)
    ax.text(0, 25.5, "Loan lifecycle - current state pain points and where agents add value", fontsize=14,
            fontweight="bold", color=NAVY, va="top")
    stages = [("Origination", "Re-keying from\nportal / e-mail"), ("Eligibility &\nDue diligence", "Multi-portal KYC,\ndoc chasing"),
              ("Appraisal", "Manual spreading,\nmemo drafting"), ("Approval", "Pack prep,\ncommittee queues"),
              ("Documentation", "CP tracking in\nspreadsheets"), ("Disbursement", "Maker-checker\nhand-offs"),
              ("Monitoring", "Quarterly covenant\ntests, late EWS"), ("Compliance &\nreporting", "Manual MIS,\naudit sampling"),
              ("Closure", "Release of\nsecurity, archive")]
    hot = {0: "P5", 1: "P1/P4", 2: "P2", 4: "P3", 6: "EWS"}
    w = (100 - 8 * 1.2) / 9
    for i, (s, pain) in enumerate(stages):
        x = i * (w + 1.2)
        box(ax, x, 11, w, 7, s, fc=NAVY, ec=NAVY, color="white", size=8.5, bold=True)
        box(ax, x, 3, w, 7, pain, fc=LIGHT, ec=GREY, size=7.5)
        if i in hot:
            box(ax, x + w * 0.15, 19, w * 0.7, 3, f"agent {hot[i]}", fc=TEAL, ec=TEAL, color="white", size=7.5, bold=True)
        if i < 8:
            arrow(ax, x + w, 14.5, x + w + 1.2, 14.5)
    ax.text(0, 1.2, "P-numbers = Automation Priority Index rank from the value stream map. Approval remains a human decision.",
            fontsize=8, color=GREY)
    save(fig, "a1_lifecycle.png")


if __name__ == "__main__":
    a1c = ROOT / "a1_loan_lifecycle" / "data" / "vsm_steps.csv"
    a2c = ROOT / "a2_chem_demand" / "data" / "vsm_steps.csv"
    a1_architecture()
    a2_architecture()
    a1_flow()
    a2_flow()
    a1_lifecycle()
    vsm_block(a1c, 120, "Value stream map - loan origination to disbursement (current state + agent overlay)",
              "a1_vsm_block.png", "applications", 7)
    vsm_block(a2c, 120, "Value stream map - demand exception to replenishment action (current state + agent overlay)",
              "a2_vsm_block.png", "exceptions", 7)
    vsm_chart(a1c, 120, "a1_vsm_chart.png", "Loan origination: VA vs NVA vs wait per application")
    vsm_chart(a2c, 120, "a2_vsm_chart.png", "Demand exception handling: VA vs NVA vs wait per exception")
    api_chart(a1c, 120, "a1_api.png")
    api_chart(a2c, 120, "a2_api.png")
    opportunity_matrix()
    forecast_chart()
    impact_chart()

"""Recommender Agent: generates and costs response options (stock transfer,
production reschedule, expedite, allocation / production cut) and builds the
least-cost plan that closes the gap within the 4-week horizon."""
from __future__ import annotations

from typing import Any

from shared.llm_client import LLMClient

from . import load

NAME = "Recommender Agent"
HORIZON_DAYS = 28
CARRYING_RATE_MONTH = 0.015
APPROVAL_THRESHOLD_USD = 50_000


def _opt(kind, desc, qty, cost, benefit, days, **extra):
    return {"type": kind, "action": desc, "qty_t": round(qty), "cost_usd": round(cost), "benefit_usd": round(benefit),
            "net_value_usd": round(benefit - cost), "lead_time_days": days, **extra}


def upside(alert: dict, cons: dict) -> tuple[list[dict], float]:
    pos, net = cons["position"], cons["network"]
    shortfall = max(0.0, -pos["gap_vs_ss_t"])
    margin = alert["margin_per_t"]
    opts = []
    for _, ln in cons["lanes"].iterrows():
        src = net[net.region == ln.from_region]
        if src.empty or src.iloc[0].surplus_vs_ss_t <= 0:
            continue
        q = min(shortfall, float(src.iloc[0].surplus_vs_ss_t))
        if q <= 0:
            continue
        if ln.transit_days <= HORIZON_DAYS - 7:
            opts.append(_opt("STOCK_TRANSFER", f"Transfer {q:,.0f} t {ln.from_dc} -> {ln.to_dc} (sea/road)", q,
                             q * ln.cost_per_t, q * margin, int(ln.transit_days), source=ln.from_dc, target=ln.to_dc))
        opts.append(_opt("EXPEDITE", f"Expedite {q:,.0f} t {ln.from_dc} -> {ln.to_dc} (air/express)", q,
                         q * ln.expedite_cost_per_t, q * margin, int(ln.expedite_days), source=ln.from_dc, target=ln.to_dc))
    for _, p in cons["plants"].iterrows():
        q = min(shortfall, float(p.free_capacity_4wk_t))
        if q <= 0:
            continue
        lane_cost = 0 if p.region == alert["region"] else 120
        days = int(p.lead_time_weeks * 7 + (0 if p.region == alert["region"] else 18))
        if days <= HORIZON_DAYS:
            opts.append(_opt("PRODUCTION_RESCHEDULE", f"Pull forward {q:,.0f} t at {p.plant} (free capacity)", q,
                             q * (p.reschedule_premium_per_t + lane_cost), q * margin, days, plant=p.plant))
    return opts, shortfall


def downside(alert: dict, cons: dict) -> tuple[list[dict], float]:
    pos, net = cons["position"], cons["network"]
    excess = max(0.0, pos["gap_vs_ss_t"] - pos["sensed_4wk_t"] * 0.25)  # beyond safety stock + 1 week buffer
    value_per_t = alert["price_per_t"] - alert["margin_per_t"]
    lanes = load("lanes")
    opts = []
    for _, p in cons["plants"][cons["plants"].region == alert["region"]].iterrows():
        q = min(excess, p.planned_t_per_week * 4 * 0.3)
        if q > 0:
            opts.append(_opt("PRODUCTION_CUT", f"Reduce planned production {q:,.0f} t at {p.plant} over 4 weeks", q,
                             q * 15, q * value_per_t * CARRYING_RATE_MONTH * 3, 7, plant=p.plant,
                             working_capital_release_usd=round(q * value_per_t)))
    for _, r in net[(net.region != alert["region"]) & (net.surplus_vs_ss_t < 0)].iterrows():
        q = min(excess, -r.surplus_vs_ss_t)
        ln = lanes[(lanes.from_region == alert["region"]) & (lanes.to_region == r.region)].iloc[0]
        if q > 0:
            opts.append(_opt("STOCK_TRANSFER", f"Re-deploy {q:,.0f} t {ln.from_dc} -> {ln.to_dc} (covers deficit there)",
                             q, q * ln.cost_per_t, q * alert["margin_per_t"], int(ln.transit_days),
                             source=ln.from_dc, target=ln.to_dc))
    return opts, excess


def build_plan(opts: list[dict], need: float) -> list[dict]:
    """Greedy: best net value per tonne first, until the gap is closed."""
    plan, left, used_sources = [], need, set()
    for o in sorted(opts, key=lambda o: -(o["net_value_usd"] / max(o["qty_t"], 1))):
        if left <= 0:
            break
        if o["net_value_usd"] <= 0 and o["type"] != "PRODUCTION_CUT":
            continue
        src = o.get("source")
        if src and src in used_sources:
            continue  # the same surplus stock cannot be shipped twice
        take = min(o["qty_t"], left)
        scale = take / o["qty_t"]
        plan.append({**o, "qty_t": round(take), "cost_usd": round(o["cost_usd"] * scale),
                     "benefit_usd": round(o["benefit_usd"] * scale),
                     "net_value_usd": round((o["benefit_usd"] - o["cost_usd"]) * scale)})
        if src:
            used_sources.add(src)
        left -= take
    return plan


def run(alert: dict, impact: dict, cons: dict, llm: LLMClient) -> dict[str, Any]:
    up = alert["gap_t"] > 0
    opts, need = (upside if up else downside)(alert, cons)
    plan = build_plan(opts, need) if need > 0 else []
    residual = max(0.0, need - sum(p["qty_t"] for p in plan))
    if up and residual > 0:
        plan.append(_opt("ALLOCATION", f"Allocate remaining supply: protect strategic accounts, defer {residual:,.0f} t "
                                       f"for non-strategic customers", residual, 0, 0, 0,
                         margin_forgone_usd=round(residual * alert["margin_per_t"])))
    plan.append(_opt("PLAN_UPDATE", f"Update S&OP demand plan {alert['sku']} {alert['region']} to sensed "
                                    f"{alert['sensed']:,.0f} t (next 4 wks)", 0, 0, 0, 0))
    totals = {"need_t": round(need), "cost_usd": sum(p["cost_usd"] for p in plan),
              "benefit_usd": sum(p["benefit_usd"] for p in plan)}
    totals["net_value_usd"] = totals["benefit_usd"] - totals["cost_usd"]
    totals["margin_forgone_usd"] = sum(p.get("margin_forgone_usd", 0) for p in plan)

    def fallback() -> dict[str, Any]:
        if need <= 0:
            return {"rationale": "Inventory plus in-transit stock covers sensed demand above safety stock; recommend "
                                 "updating the demand plan and monitoring weekly - no physical action required."}
        steps = "; ".join(p["action"] for p in plan[:-1])
        return {"rationale": (
            f"{'Shortfall' if up else 'Excess'} of {need:,.0f} t vs safety stock at {cons['position']['dc']} over the next "
            f"4 weeks, driven mainly by {impact['primary_driver']}. Least-cost plan: {steps}. Total cost "
            f"${totals['cost_usd']:,.0f} against ${totals['benefit_usd']:,.0f} "
            f"{'margin protected' if up else 'carrying cost avoided / margin captured'}"
            + (f"; ${totals['margin_forgone_usd']:,.0f} margin forgone on deferred volume." if totals['margin_forgone_usd'] else "."))}

    rat = llm.complete_json(
        NAME,
        "You are a supply chain planner. Explain the recommended plan and trade-offs in <= 4 sentences. Do not change "
        'any quantities or costs. Return {"rationale": str}.',
        f"Alert: {alert}\nPosition: {cons['position']}\nOptions: {opts}\nPlan: {plan}\nTotals: {totals}",
        fallback,
    )
    return {"options": opts, "plan": plan, "totals": totals, "rationale": rat["rationale"],
            "approval_level": "S&OP Lead" if totals["cost_usd"] > APPROVAL_THRESHOLD_USD else "Demand Planner"}

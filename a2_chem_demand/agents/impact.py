"""Impact Agent: drills a deviation down to the customers driving it and
quantifies revenue / margin at risk."""
from __future__ import annotations

from typing import Any

import pandas as pd

from shared.llm_client import LLMClient

from . import load

NAME = "Impact Agent"


def run(alert: dict, llm: LLMClient) -> dict[str, Any]:
    od = load("orders")
    od["week"] = pd.to_datetime(od.week)
    s = od[(od.sku == alert["sku"]) & (od.region == alert["region"])]
    last = s.week.max()
    recent = s[s.week > last - pd.Timedelta(weeks=4)].groupby("customer").qty_t.sum() / 4
    # baseline = 13 weeks ending 8 weeks ago (clean of the most recent shift)
    base = s[(s.week <= last - pd.Timedelta(weeks=8)) & (s.week > last - pd.Timedelta(weeks=21))].groupby("customer").qty_t.sum() / 13
    cust = pd.DataFrame({"baseline_t_wk": base.round(1), "recent_t_wk": recent.round(1)})
    cust["change_pct"] = (cust.recent_t_wk / cust.baseline_t_wk - 1).round(3)
    cust["delta_t_wk"] = (cust.recent_t_wk - cust.baseline_t_wk).round(1)
    cust = cust.sort_values("delta_t_wk", key=abs, ascending=False).reset_index()
    total_delta = cust.delta_t_wk.sum()
    driver = cust.iloc[0]
    share = driver.delta_t_wk / total_delta if total_delta else 0
    revenue = abs(alert["gap_t"]) * alert["price_per_t"]
    anomalous = cust[cust.change_pct.abs() >= 0.5]
    anomaly_txt = "; ".join(f"{r.customer} {r.change_pct:+.0%} (anomalous - confirm with account team)"
                            for r in anomalous.itertuples() if r.customer != driver.customer)

    def fallback() -> dict[str, Any]:
        verb = "increase" if alert["gap_t"] > 0 else "decrease"
        return {"narrative": (
            f"{alert['sku']} ({alert['name']}) in {alert['region']}: sensed demand for the next 4 weeks is "
            f"{alert['deviation_pct']:+.0%} vs the S&OP plan ({alert['gap_t']:+,.0f} t). {driver.customer} explains "
            f"~{share:.0%} of the {verb} ({driver.change_pct:+.0%} vs its 13-week baseline). Regional PMI is "
            f"{alert['pmi']:.1f} ({alert['pmi_chg4']:+.1f} over 4 weeks). "
            + (f"Also: {anomaly_txt}. " if anomaly_txt else "") +
            f"Revenue exposure ~${revenue:,.0f}; margin ~${alert['margin_at_stake_usd']:,.0f}.")}

    out = llm.complete_json(
        NAME,
        "You are a demand planner. Explain in 3 sentences what is driving this deviation, using only the data. "
        'Return {"narrative": str}.',
        f"Alert: {alert}\nCustomer breakdown: {cust.to_dict('records')}",
        fallback,
    )
    return {"customers": cust, "primary_driver": driver.customer, "driver_share": round(float(share), 2),
            "anomalous_customers": anomalous.customer.tolist(),
            "revenue_at_risk_usd": round(revenue), "narrative": out["narrative"]}

"""Deviation Agent: flags SKU x region series where sensed demand diverges
significantly from the frozen S&OP plan, and ranks them by margin at stake."""
from __future__ import annotations

import pandas as pd

from . import load

NAME = "Deviation Agent"
FWD_THRESHOLD = 0.15     # sensed next-4-week vs plan
ACTUAL_THRESHOLD = 0.20  # actual last-4-week vs plan
Z_THRESHOLD = 1.5


def run(latest: pd.DataFrame) -> pd.DataFrame:
    skus = load("skus")[["sku", "name", "margin_per_t", "price_per_t"]]
    d = latest.merge(skus, on="sku")
    d["gap_t"] = d.sensed - d.plan
    d["margin_at_stake_usd"] = (d.gap_t.abs() * d.margin_per_t).round(0)
    fwd = d.deviation_pct.abs() >= FWD_THRESHOLD
    act = (d.actual_dev_pct.abs() >= ACTUAL_THRESHOLD) & (d.z_score.abs() >= Z_THRESHOLD)
    d["flag"] = fwd | act
    d["direction"] = d.gap_t.apply(lambda g: "UPSIDE (shortage risk)" if g > 0 else "DOWNSIDE (excess risk)")
    d["severity"] = pd.cut(d.margin_at_stake_usd, [-1, 25_000, 75_000, float("inf")], labels=["Low", "Medium", "High"])
    d["evidence"] = d.apply(lambda r: f"sensed {r.deviation_pct:+.0%} vs plan; last 4 wks {r.actual_dev_pct:+.0%} "
                                      f"(z={r.z_score:+.1f}); PMI {r.pmi:.1f} ({r.pmi_chg4:+.1f})", axis=1)
    return d[d.flag].sort_values("margin_at_stake_usd", ascending=False).reset_index(drop=True)

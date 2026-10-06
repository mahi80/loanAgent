"""Constraint Agent: checks inventory position, safety stock, other DCs'
surplus, plant free capacity and lane lead times for the affected SKU."""
from __future__ import annotations

from typing import Any

import pandas as pd

from . import load

NAME = "Constraint Agent"
H = 4


def run(alert: dict, latest: pd.DataFrame) -> dict[str, Any]:
    inv = load("inventory")
    skus = load("skus")
    fam = skus.set_index("sku").loc[alert["sku"], "family"]
    sku_inv = inv[inv.sku == alert["sku"]].merge(latest[latest.sku == alert["sku"]][["region", "sensed"]], on="region")
    sku_inv["available_t"] = sku_inv.on_hand_t + sku_inv.in_transit_t
    sku_inv["projected_end_t"] = sku_inv.available_t - sku_inv.sensed
    sku_inv["surplus_vs_ss_t"] = (sku_inv.projected_end_t - sku_inv.safety_stock_t).round(0)
    sku_inv["weeks_cover"] = (sku_inv.available_t / (sku_inv.sensed / H)).round(1)
    me = sku_inv[sku_inv.region == alert["region"]].iloc[0]
    pl = load("plants")
    pl = pl[pl.family == fam].copy()
    pl["free_capacity_4wk_t"] = (pl.weekly_capacity_t - pl.planned_t_per_week) * H
    pl["utilisation"] = (pl.planned_t_per_week / pl.weekly_capacity_t).round(2)
    lanes = load("lanes")
    lanes = lanes[lanes.to_region == alert["region"]]
    return {
        "family": fam,
        "network": sku_inv[["region", "dc", "on_hand_t", "in_transit_t", "safety_stock_t", "sensed", "projected_end_t",
                            "surplus_vs_ss_t", "weeks_cover"]].round(0),
        "position": {"dc": me.dc, "available_t": float(me.available_t), "sensed_4wk_t": round(float(me.sensed)),
                     "safety_stock_t": float(me.safety_stock_t), "gap_vs_ss_t": float(me.surplus_vs_ss_t),
                     "weeks_cover": float(me.weeks_cover)},
        "plants": pl,
        "lanes": lanes,
    }

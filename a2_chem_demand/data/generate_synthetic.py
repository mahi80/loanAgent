"""Synthetic data for the chemical demand-sensing prototype (ALL DATA IS SYNTHETIC).

Generates 104 weeks of customer-level orders for 12 SKUs x 4 regions x 3
customers per region, regional PMI / Brent / construction signals, DC
inventory, plant capacity and inter-DC lanes.

Demand model per SKU-region-customer:
    base x seasonality x trend x (1 + 0.05 * (PMI[t-3] - 50)) x events x noise

Injected events (what the agents should find):
  1. APAC / EPX-200 epoxy resin - Pacific Coatings wins a large project
     (ramping +50%..+130% over the last 6 weeks) while APAC PMI climbs -> upside deviation, shortage risk
     in the Singapore DC.
  2. EU / PVC-K67 - Iberia Polymers plant outage (-85%) plus -10% for other EU buyers and EU PMI softening
     -> downside deviation, excess inventory at Rotterdam.

Run:  python a2_chem_demand/data/generate_synthetic.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
RNG = np.random.default_rng(42)
WEEKS = 104
START = pd.Timestamp("2024-10-07")  # Mondays; last week = 2026-09-28

SKUS = [  # sku, name, family, price $/t, margin $/t, base t/week/region
    ("EPX-200", "Liquid Epoxy Resin", "Epoxy", 3200, 700, 120),
    ("EPX-310", "Epoxy Novolac Resin", "Epoxy", 4100, 950, 45),
    ("PVC-K67", "PVC Resin K67", "PVC", 1100, 180, 380),
    ("PVC-K57", "PVC Resin K57", "PVC", 1150, 190, 160),
    ("POL-3000", "Polyether Polyol 3000", "Polyols", 1900, 380, 140),
    ("POL-5600", "Polymer Polyol 5600", "Polyols", 2100, 420, 70),
    ("SOL-MEK", "Methyl Ethyl Ketone", "Solvents", 1300, 210, 200),
    ("SOL-BAC", "Butyl Acetate", "Solvents", 1250, 200, 150),
    ("SUR-LAS", "Linear Alkylbenzene Sulfonate", "Surfactants", 1600, 310, 180),
    ("SUR-AEO", "Alcohol Ethoxylate", "Surfactants", 1800, 350, 90),
    ("ADD-UV1", "UV Stabilizer", "Additives", 9500, 2600, 12),
    ("ADD-AO2", "Phenolic Antioxidant", "Additives", 8200, 2200, 15),
]
REGIONS = {
    "NAM": ("DC-Houston", ["Apex Coatings", "Midwest Plastics", "Gulf Packaging"], 0.0),
    "EU": ("DC-Rotterdam", ["Rhein Composites", "Nordic Paints", "Iberia Polymers"], 0.0),
    "APAC": ("DC-Singapore", ["Pacific Coatings", "Shenzhen Electronic Materials", "Jurong Construction Chem"], 0.5),
    "LATAM": ("DC-Sao-Paulo", ["Andes Plastics", "Brasil Tintas", "Mexico Industrial"], 0.5),
}
REGION_SCALE = {"NAM": 1.0, "EU": 0.9, "APAC": 1.2, "LATAM": 0.5}
CONSTRUCTION_FAMILIES = {"Epoxy", "PVC", "Polyols"}


def signals() -> pd.DataFrame:
    weeks = pd.date_range(START, periods=WEEKS, freq="W-MON")
    out = {"week": weeks}
    for r in REGIONS:
        walk = 50 + np.cumsum(RNG.normal(0, 0.35, WEEKS))
        walk = 50 + (walk - walk.mean()) * 0.8
        if r == "APAC":
            walk[-10:] += np.linspace(0.5, 5.0, 10)
        if r == "EU":
            walk[-10:] -= np.linspace(0.3, 3.5, 10)
        out[f"pmi_{r.lower()}"] = walk.round(1)
    out["brent_usd"] = (78 + np.cumsum(RNG.normal(0, 1.2, WEEKS))).round(1)
    out["construction_idx"] = (100 + 6 * np.sin(2 * np.pi * np.arange(WEEKS) / 52) + RNG.normal(0, 1, WEEKS)).round(1)
    return pd.DataFrame(out)


def orders(sig: pd.DataFrame) -> pd.DataFrame:
    rows = []
    t = np.arange(WEEKS)
    for sku, _, fam, *_rest, base in SKUS:
        for r, (_, customers, phase) in REGIONS.items():
            pmi = sig[f"pmi_{r.lower()}"].to_numpy()
            pmi_lag = np.concatenate([np.full(3, pmi[0]), pmi[:-3]])
            amp = 0.18 if fam in CONSTRUCTION_FAMILIES else 0.07
            season = 1 + amp * np.sin(2 * np.pi * (t / 52 - 0.1 + phase))
            trend = 1 + RNG.uniform(-0.03, 0.06) * t / 52
            macro = 1 + 0.05 * (pmi_lag - 50)
            shares = RNG.dirichlet([4, 3, 2])
            for c, share in zip(customers, shares):
                event = np.ones(WEEKS)
                if sku == "EPX-200" and c == "Pacific Coatings":
                    event[-6:] = np.linspace(1.5, 2.3, 6)  # project ramp-up
                if sku == "PVC-K67" and r == "EU":
                    event[-6:] = 0.15 if c == "Iberia Polymers" else 0.9  # outage + soft market
                noise = RNG.lognormal(0, 0.22, WEEKS)
                qty = base * REGION_SCALE[r] * share * season * trend * macro * event * noise
                for i in range(WEEKS):
                    rows.append((sig.week[i], sku, r, c, round(max(qty[i], 0), 1)))
    return pd.DataFrame(rows, columns=["week", "sku", "region", "customer", "qty_t"])


def inventory(od: pd.DataFrame) -> pd.DataFrame:
    """On-hand roughly 3-5 weeks of recent demand; tuned so EPX-200 Singapore is
    tight and PVC-K67 Rotterdam is long (set from the pre-event run-rate)."""
    rows = []
    recent = od[od.week >= od.week.max() - pd.Timedelta(weeks=12)]
    rate = recent.groupby(["sku", "region"]).qty_t.sum() / 13
    for (sku, r), wk in rate.items():
        dc = REGIONS[r][0]
        cover = RNG.uniform(3.0, 5.0)
        if (sku, r) == ("EPX-200", "APAC"):
            cover = 2.2
        if (sku, r) == ("EPX-200", "EU"):
            cover = 7.5
        if (sku, r) == ("EPX-200", "NAM"):
            cover = 5.5
        if (sku, r) == ("PVC-K67", "EU"):
            cover = 6.5
        rows.append({"sku": sku, "region": r, "dc": dc, "on_hand_t": round(wk * cover),
                     "in_transit_t": round(wk * RNG.uniform(0, 0.8)), "safety_stock_t": round(wk * 1.5)})
    return pd.DataFrame(rows)


def plants() -> pd.DataFrame:
    # plant, region, family, weekly capacity (t), planned next 4 weeks (t/week), lead time (weeks), premium $/t
    data = [
        ("Plant-Texas", "NAM", "Epoxy", 650, 560, 2, 140), ("Plant-Texas", "NAM", "PVC", 1500, 1380, 1, 60),
        ("Plant-Texas", "NAM", "Solvents", 900, 720, 1, 50), ("Plant-Antwerp", "EU", "Epoxy", 420, 330, 2, 160),
        ("Plant-Antwerp", "EU", "PVC", 1350, 1300, 1, 70), ("Plant-Antwerp", "EU", "Polyols", 700, 560, 2, 90),
        ("Plant-Antwerp", "EU", "Additives", 60, 45, 3, 900), ("Plant-Jurong", "APAC", "Epoxy", 380, 300, 2, 120),
        ("Plant-Jurong", "APAC", "Surfactants", 800, 640, 1, 80), ("Plant-Jurong", "APAC", "Polyols", 500, 410, 2, 85),
        ("Plant-Camacari", "LATAM", "PVC", 600, 520, 2, 75), ("Plant-Camacari", "LATAM", "Solvents", 400, 300, 1, 55),
    ]
    return pd.DataFrame(data, columns=["plant", "region", "family", "weekly_capacity_t", "planned_t_per_week",
                                       "lead_time_weeks", "reschedule_premium_per_t"])


def lanes() -> pd.DataFrame:
    dcs = {r: v[0] for r, v in REGIONS.items()}
    base = {("NAM", "EU"): (95, 16), ("NAM", "APAC"): (140, 24), ("NAM", "LATAM"): (85, 12),
            ("EU", "APAC"): (120, 21), ("EU", "LATAM"): (110, 18), ("APAC", "LATAM"): (150, 28)}
    rows = []
    for (a, b), (cost, days) in base.items():
        for x, y in ((a, b), (b, a)):
            rows.append({"from_region": x, "from_dc": dcs[x], "to_region": y, "to_dc": dcs[y],
                         "cost_per_t": cost, "transit_days": days, "expedite_cost_per_t": cost * 4, "expedite_days": 4})
    return pd.DataFrame(rows)


def main() -> None:
    sig = signals()
    od = orders(sig)
    sku_df = pd.DataFrame(SKUS, columns=["sku", "name", "family", "price_per_t", "margin_per_t", "base_t_week"])
    for name, df in {"signals": sig, "orders": od, "inventory": inventory(od), "plants": plants(),
                     "lanes": lanes(), "skus": sku_df}.items():
        df.to_csv(OUT / f"{name}.csv", index=False)
        print(f"{name:10s} {len(df):>6} rows")


if __name__ == "__main__":
    main()

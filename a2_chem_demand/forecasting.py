"""Demand sensing model.

Direct 4-week-ahead model per SKU x region (global gradient boosting across
all series). Target and lag features are scaled by each series' 13-week mean,
so one model learns shape/response across products of very different volume.

Baseline ("S&OP plan") = 4 x 13-week moving average, frozen at the monthly
planning cycle - the typical statistical forecast in today's process.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

DATA = Path(__file__).resolve().parent / "data"
H = 4  # horizon (weeks)
PLAN_LAG = 4  # plan was frozen 4 weeks before the current week (monthly S&OP)
SENSE_W = 0.5  # weight of the ML forecast vs the latest 4-week run-rate


def load_weekly() -> pd.DataFrame:
    od = pd.read_csv(DATA / "orders.csv", parse_dates=["week"])
    sig = pd.read_csv(DATA / "signals.csv", parse_dates=["week"])
    skus = pd.read_csv(DATA / "skus.csv")
    wk = od.groupby(["sku", "region", "week"], as_index=False).qty_t.sum()
    wk = wk.merge(sig, on="week").merge(skus[["sku", "family"]], on="sku")
    wk["pmi"] = [row[f"pmi_{row.region.lower()}"] for _, row in wk.iterrows()]
    return wk.sort_values(["sku", "region", "week"]).reset_index(drop=True)


def features(wk: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (_, _), g in wk.groupby(["sku", "region"], sort=False):
        g = g.copy()
        q = g.qty_t
        g["ma13"] = q.rolling(13).mean()
        g["ma4"] = q.rolling(4).mean()
        for l in range(4):
            g[f"lag{l}_r"] = q.shift(l) / g.ma13
        g["ma4_r"] = g.ma4 / g.ma13
        g["ma26_r"] = q.rolling(26).mean() / g.ma13
        g["ly_r"] = (q.shift(52 - H).rolling(H).sum()) / (H * g.ma13)  # same window last year
        g["pmi_chg4"] = g.pmi - g.pmi.shift(4)
        woy = g.week.dt.isocalendar().week.astype(float) + H / 2
        g["woy_sin"], g["woy_cos"] = np.sin(2 * np.pi * woy / 52), np.cos(2 * np.pi * woy / 52)
        g["target"] = q[::-1].rolling(H).sum()[::-1].shift(-1)  # sum of t+1..t+H
        g["target_r"] = g.target / (H * g.ma13)
        g["baseline"] = H * g.ma13
        g["plan"] = (H * g.ma13).shift(PLAN_LAG)  # stale S&OP plan for the same window
        out.append(g)
    f = pd.concat(out)
    for c in ("sku", "region", "family"):
        f[c + "_c"] = f[c].astype("category").cat.codes
    return f


FEATS = ["lag0_r", "lag1_r", "lag2_r", "lag3_r", "ma4_r", "ma26_r", "ly_r", "pmi", "pmi_chg4",
         "brent_usd", "construction_idx", "woy_sin", "woy_cos", "sku_c", "region_c", "family_c"]


def wmape(y, yhat) -> float:
    return float(np.abs(y - yhat).sum() / np.abs(y).sum())


def _model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                         min_samples_leaf=20, l2_regularization=1.0,
                                         categorical_features=[FEATS.index(c) for c in ("sku_c", "region_c", "family_c")],
                                         random_state=0)


@dataclass
class SensingResult:
    frame: pd.DataFrame        # full feature frame with predictions
    backtest: pd.DataFrame     # per-series backtest metrics
    mape_model: float
    mape_baseline: float
    mape_plan: float
    latest: pd.DataFrame       # one row per SKU x region at the latest week: sensed vs plan
    as_of: pd.Timestamp


def run(test_weeks: int = 16) -> SensingResult:
    f = features(load_weekly())
    f = f.dropna(subset=[c for c in FEATS if c not in ("ly_r",)])
    weeks = sorted(f.week.unique())
    as_of = weeks[-1]
    known = f.dropna(subset=["target"])
    cutoff = sorted(known.week.unique())[-test_weeks]
    # backtest: train strictly before cutoff (no leakage: targets of training rows end before cutoff)
    train = known[known.week < cutoff - pd.Timedelta(weeks=H)]
    test = known[known.week >= cutoff].copy()
    m = _model().fit(train[FEATS], train.target_r)
    test["pred_ml"] = m.predict(test[FEATS]) * H * test.ma13
    test["pred"] = SENSE_W * test.pred_ml + (1 - SENSE_W) * H * test.ma4
    bt = (test.groupby(["sku", "region"])
          .apply(lambda g: pd.Series({"wmape_model": wmape(g.target, g.pred),
                                      "wmape_baseline": wmape(g.target, g.baseline),
                                      "wmape_ml_only": wmape(g.target, g.pred_ml),
                                      "wmape_plan": wmape(g.target, g.plan)}), include_groups=False)
          .reset_index())
    # production fit on all known targets, predict forward from latest week
    final = _model().fit(known[FEATS], known.target_r)
    f["sensed"] = final.predict(f[FEATS]) * H * f.ma13
    f.loc[f.index.isin(test.index), "backtest_pred"] = test.pred
    # demand sensing = ML forecast blended with the latest 4-week run-rate (short-term signal)
    f["sensed"] = SENSE_W * f.sensed + (1 - SENSE_W) * H * f.ma4
    # actuals-to-date vs the plan that was set for those same weeks
    f["actual_last4"] = f.groupby(["sku", "region"]).qty_t.transform(lambda q: q.rolling(H).sum())
    f["plan_last4"] = f.groupby(["sku", "region"]).baseline.shift(H + PLAN_LAG)
    f["hist_std4"] = f.groupby(["sku", "region"]).actual_last4.transform(lambda q: q.rolling(52, min_periods=20).std())
    latest = f[f.week == as_of][["sku", "region", "family", "ma13", "ma4", "pmi", "pmi_chg4", "plan", "sensed",
                                  "actual_last4", "plan_last4", "hist_std4"]].copy()
    latest["deviation_pct"] = (latest.sensed - latest.plan) / latest.plan
    latest["actual_dev_pct"] = (latest.actual_last4 - latest.plan_last4) / latest.plan_last4
    latest["z_score"] = (latest.actual_last4 - latest.plan_last4) / latest.hist_std4
    return SensingResult(f, bt, wmape(test.target, test.pred), wmape(test.target, test.baseline),
                         wmape(test.target, test.plan), latest.reset_index(drop=True), as_of)


if __name__ == "__main__":
    r = run()
    print(f"as of {r.as_of.date()}  WMAPE model {r.mape_model:.1%}  baseline {r.mape_baseline:.1%}  stale plan {r.mape_plan:.1%}")
    print(r.latest.sort_values("deviation_pct").to_string(index=False))

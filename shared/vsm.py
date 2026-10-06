"""Lean Six Sigma Value Stream Map engine (shared by both assignments).

Step times are MOCKED assumptions supplied per process as a CSV
(a1: loan origination -> disbursement, a2: demand exception -> replenishment
action). Everything else -
takt, effective cycle time, lead time, PCE, capacity and the Automation
Priority Index - is computed here so nothing in the deck is hard-coded.

Definitions
  VA    value-added work the borrower would pay for (analysis, judgement, decision)
  NVA   necessary-but-wasteful manual touch (re-keying, chasing, formatting, rework)
  Wait  queue / hand-off time (1 day = 8 h)
  Takt  available time / demand
  Eff. CT = (VA + NVA touch) / FTE   (> takt => bottleneck)
  PCE   = VA time / lead time
  API   = NVA hours (touch + wait) x agent feasibility (1-5) x max(1, CT/takt) / 10
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

HOURS_PER_DAY = 8


@dataclass(frozen=True)
class Assumptions:
    demand_per_month: int = 120
    working_days: int = 21
    hours_per_day_available: float = 7.5

    @property
    def available_h(self) -> float:
        return self.working_days * self.hours_per_day_available

    @property
    def takt_h(self) -> float:
        return self.available_h / self.demand_per_month


def load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def state(df: pd.DataFrame, a: Assumptions, future: bool = False) -> pd.DataFrame:
    p = "future_" if future else ""
    out = pd.DataFrame({
        "step_no": df.step_no, "step": df.step, "fte": df.fte,
        "va_h": df[f"{p}va_h"], "nva_h": df[f"{p}nva_h"], "wait_d": df[f"{p}wait_d"],
    })
    out["wait_h"] = out.wait_d * HOURS_PER_DAY
    out["eff_ct_h"] = ((out.va_h + out.nva_h) / out.fte).round(2)
    out["over_takt"] = out.eff_ct_h > a.takt_h
    out["capacity_per_month"] = (a.available_h / out.eff_ct_h).round(0)
    return out


def summary(s: pd.DataFrame, a: Assumptions) -> dict[str, float]:
    va, nva, wait = s.va_h.sum(), s.nva_h.sum(), s.wait_h.sum()
    lead = va + nva + wait
    return {
        "va_h": va, "nva_h": nva, "wait_h": wait,
        "touch_h": va + nva,
        "lead_time_h": lead, "lead_time_d": round(lead / HOURS_PER_DAY, 1),
        "pce": round(va / lead, 4),
        "steps_over_takt": int(s.over_takt.sum()),
        "bottleneck": s.loc[s.eff_ct_h.idxmax(), "step"],
        "capacity_per_month": int(s.capacity_per_month.min()),
        "takt_h": round(a.takt_h, 2),
    }


def priority(df: pd.DataFrame, a: Assumptions) -> pd.DataFrame:
    cur = state(df, a)
    out = cur[["step_no", "step"]].copy()
    out["nva_total_h"] = cur.nva_h + cur.wait_h
    out["feasibility"] = df.feasibility
    out["bottleneck_factor"] = (cur.eff_ct_h / a.takt_h).clip(lower=1).round(2)
    out["api"] = (out.nva_total_h * out.feasibility * out.bottleneck_factor / 10).round(1)
    out["agent"] = df.agent
    out = out.sort_values("api", ascending=False).reset_index(drop=True)
    out.insert(0, "rank", out.index + 1)
    return out


def before_after(df: pd.DataFrame, a: Assumptions) -> pd.DataFrame:
    b, f = summary(state(df, a), a), summary(state(df, a, True), a)

    def pct(x, y):
        return f"{(y - x) / x:+.0%}"

    rows = [
        ("Lead time (days)", b["lead_time_d"], f["lead_time_d"], pct(b["lead_time_d"], f["lead_time_d"])),
        ("Touch time per unit (h)", b["touch_h"], f["touch_h"], pct(b["touch_h"], f["touch_h"])),
        ("NVA touch (h)", b["nva_h"], f["nva_h"], pct(b["nva_h"], f["nva_h"])),
        ("Wait (h)", b["wait_h"], f["wait_h"], pct(b["wait_h"], f["wait_h"])),
        ("PCE", f"{b['pce']:.1%}", f"{f['pce']:.1%}", f"{f['pce'] / b['pce']:.1f}x"),
        ("Steps over takt", b["steps_over_takt"], f["steps_over_takt"], "bottlenecks removed" if not f["steps_over_takt"] else ""),
        ("Capacity (units/month, bottleneck-bound)", b["capacity_per_month"], f["capacity_per_month"],
         pct(b["capacity_per_month"], f["capacity_per_month"])),
    ]
    return pd.DataFrame(rows, columns=["KPI", "Before", "After", "Change"])


if __name__ == "__main__":
    import sys

    a, df = Assumptions(int(sys.argv[2]) if len(sys.argv) > 2 else 120), load(Path(sys.argv[1]))
    print(f"Takt: {a.takt_h:.2f} h ({a.takt_h * 60:.0f} min)")
    print(state(df, a).to_string(index=False))
    print(summary(state(df, a), a))
    print(priority(df, a).to_string(index=False))
    print(before_after(df, a).to_string(index=False))

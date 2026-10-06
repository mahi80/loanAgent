"""Demand-response agents. Deterministic code owns quantities, costs and
constraints; the LLM writes explanations and the planner-facing narrative."""
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"


def load(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / f"{name}.csv", keep_default_na=False, na_values=[""])

"""Loan lifecycle agents.

Each agent is a small, single-responsibility unit:
deterministic code owns numbers and policy outcomes; the LLM owns extraction,
summarisation and narrative. Every agent returns a plain dict that the
orchestrator writes to the audit log.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = DATA / "documents"

REQUIRED_DOCS = {
    "term_loan": ["financial_statements", "kyc", "bank_statement", "collateral_valuation"],
    "working_capital": ["financial_statements", "kyc", "bank_statement", "stock_statement"],
    "project_finance": ["financial_statements", "kyc", "bank_statement", "collateral_valuation", "project_report"],
}

SECURED_PRODUCTS = {"term_loan", "project_finance"}
WATCHLIST_SECTORS = ("infrastructure", "real estate", "power")


def doc_type(filename: str) -> str:
    """APP-1001_financial_statements.txt -> financial_statements.
    (Production: a document classifier / Azure Document Intelligence.)"""
    return filename.split("_", 1)[1].rsplit(".", 1)[0]

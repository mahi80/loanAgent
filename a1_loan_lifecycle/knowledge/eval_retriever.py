"""Retrieval eval: expected clause must be in the top 2 (or nothing for off-topic).

Run:  python a1_loan_lifecycle/knowledge/eval_retriever.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from knowledge.retriever import PolicyRetriever  # noqa: E402

CASES = {
    "what is the LTV limit?": "CP-4.3",
    "ltv limit": "CP-4.3",
    "can we lend to a politician?": "CP-2.2",
    "minimum DSCR": "CP-4.1",
    "who approves a 15 million loan": "CP-6.1",
    "what documents before disbursement": "CP-7.1",
    "is a 2 year old company eligible": "CP-3.1",
    "max leverage for project finance": "CP-4.2",
    "what if the borrower is on OFAC list": "CP-2.1",
    "do we need audited accounts": "CP-3.3",
    "valuation older than a year": "CP-4.4",
    "too many cheque bounces": "CP-5.2",
    "what is the weather today": None,
}

if __name__ == "__main__":
    r = PolicyRetriever()
    passed = 0
    for q, expected in CASES.items():
        hits = r.search(q, k=3)
        ok = expected in [h["id"] for h in hits[:2]] if expected else not hits
        passed += ok
        print("PASS" if ok else "FAIL", f"{q:40s}", [(h["id"], h["score"]) for h in hits])
    print(f"{passed}/{len(CASES)} passed")
    sys.exit(0 if passed == len(CASES) else 1)

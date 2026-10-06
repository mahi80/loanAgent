"""Origination / Intake Agent: normalises the application, classifies the
segment, inventories documents and screens them for prompt injection."""
from __future__ import annotations

from typing import Any

from shared.llm_client import detect_injection

from . import DOCS, REQUIRED_DOCS, doc_type

NAME = "Intake Agent"


def segment(amount: float) -> str:
    if amount <= 2_000_000:
        return "SME"
    if amount <= 10_000_000:
        return "Mid-Corporate"
    return "Large Corporate"


def run(app: dict[str, Any]) -> dict[str, Any]:
    docs, security = {}, []
    for fname in app["documents"]:
        path = DOCS / fname
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        docs[doc_type(fname)] = {"file": fname, "text": text}
        hits = detect_injection(text)
        if hits:
            security.append(
                {
                    "file": fname,
                    "markers": hits,
                    "action": "Instruction-like text quarantined; not passed to LLM; flagged for human review",
                }
            )
    return {
        "application_id": app["application_id"],
        "borrower": app["borrower"],
        "product": app["product"],
        "segment": segment(app["amount_usd"]),
        "amount_usd": app["amount_usd"],
        "required_documents": REQUIRED_DOCS[app["product"]],
        "received_documents": sorted(docs),
        "security_flags": security,
        "_docs": docs,  # internal: passed to downstream agents, not rendered
    }

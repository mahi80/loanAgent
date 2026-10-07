"""Document & policy ingestion (POC placeholder for the production ingestion pipeline).

POC: files uploaded in the UI -> text extraction (txt / md / pdf via pypdf) ->
document classification (keyword rules) -> landing folder runtime/uploads/<APP>/
-> the normal agent pipeline (Intake screens for prompt injection, Document
Intelligence extracts fields with grounding).

Production: S3 / Blob landing zone -> EventBridge / Event Grid trigger ->
Textract / Azure AI Document Intelligence (OCR, tables, key-values) ->
classification model -> malware scan -> same agent pipeline, with the policy
corpus indexed in OpenSearch / Azure AI Search.
"""
from __future__ import annotations

import io
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from shared.audit import RUNTIME_DIR

UPLOAD_DIR = RUNTIME_DIR / "uploads"
POLICY_DIR = RUNTIME_DIR / "policy"
MAX_BYTES = 5 * 1024 * 1024
ALLOWED = {".txt", ".md", ".pdf"}

# keyword rules: first match wins (filename checked before content)
DOC_RULES = [
    ("financial_statements", r"financial|balance sheet|profit and loss|p&l|ebitda|audited|annual report"),
    ("kyc", r"\bkyc\b|incorporation|beneficial owner|sanctions|directors|registration no"),
    ("bank_statement", r"bank statement|account statement|cheque bounce|overdraft|average monthly balance"),
    ("collateral_valuation", r"valuation|valuer|collateral"),
    ("project_report", r"project report|project cost|detailed project|dpr\b|traffic study"),
    ("stock_statement", r"stock statement|inventory statement|debtors|receivables ageing"),
]


def extract_text(name: str, data: bytes) -> str:
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError(f"{name}: unsupported type {suffix} (allowed: {', '.join(sorted(ALLOWED))})")
    if len(data) > MAX_BYTES:
        raise ValueError(f"{name}: larger than {MAX_BYTES // 1024 // 1024} MB")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise ValueError("PDF support needs `pypdf` (pip install pypdf)") from exc
        text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
        if not text.strip():
            raise ValueError(f"{name}: no text layer (scanned PDF) - production uses OCR (Textract / Document Intelligence)")
        return text
    return data.decode("utf-8", errors="replace")


def classify(name: str, text: str) -> str:
    for source in (name.lower().replace("_", " "), text[:3000].lower()):
        for dtype, pattern in DOC_RULES:
            if re.search(pattern, source):
                return dtype
    return "other"


def next_app_id() -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    n = len([p for p in UPLOAD_DIR.iterdir() if p.is_dir()]) + 1
    return f"UPL-{2000 + n}"


def create_application(fields: dict[str, Any], files: list[tuple[str, bytes]], actor: str) -> dict[str, Any]:
    """Validate, extract, classify and land an uploaded application. Returns the application dict."""
    if not files:
        raise ValueError("Upload at least one document.")
    app_id = next_app_id()
    folder = UPLOAD_DIR / app_id
    folder.mkdir(parents=True)
    docs, report = [], []
    for name, data in files:
        text = extract_text(name, data)
        dtype = classify(name, text)
        fname = f"{app_id}_{dtype}.txt" if dtype != "other" else f"{app_id}_other_{len(docs)}.txt"
        if fname in docs:  # two files of the same type: keep both, the first is used for extraction
            fname = fname.replace(".txt", f"_{len(docs)}.txt")
        (folder / fname).write_text(text, encoding="utf-8")
        docs.append(fname)
        report.append({"file": name, "classified_as": dtype, "chars": len(text)})
    app = {
        "application_id": app_id,
        "borrower": fields["borrower"].strip(),
        "sector": fields["sector"].strip(),
        "country": fields.get("country", ""),
        "product": fields["product"],
        "amount_usd": float(fields["amount_usd"]),
        "tenor_years": int(fields["tenor_years"]),
        "interest_rate": float(fields["interest_rate"]),
        "purpose": fields["purpose"].strip(),
        "relationship_manager": fields.get("relationship_manager", actor),
        "submitted_on": date.today().isoformat(),
        "documents": docs,
        "doc_dir": str(folder),
        "source": f"upload by {actor}",
        "ingestion_report": report,
    }
    (folder / "application.json").write_text(json.dumps(app, indent=2), encoding="utf-8")
    return app


def list_uploaded() -> list[dict[str, Any]]:
    if not UPLOAD_DIR.exists():
        return []
    return [json.loads((d / "application.json").read_text(encoding="utf-8"))
            for d in sorted(UPLOAD_DIR.iterdir()) if (d / "application.json").exists()]


def ingest_policy(name: str, data: bytes) -> list[str]:
    """Add a policy addendum (markdown with '## CP-x.y Title' clauses). Returns the clause ids found."""
    text = extract_text(name, data)
    ids = re.findall(r"^## (CP-[\d.]+) ", text, re.M)
    if not ids:
        raise ValueError("No clauses found - each clause needs a heading like '## CP-9.1 Title'.")
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    (POLICY_DIR / (Path(name).stem + ".md")).write_text(text, encoding="utf-8")
    return ids

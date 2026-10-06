"""Due-Diligence Agent: (a) identifies missing documents/fields and drafts the
information request, (b) computes pro-forma ratios deterministically and
(c) runs policy / eligibility checks, each cited to a policy clause (RAG)."""
from __future__ import annotations

from datetime import date
from typing import Any

from shared.llm_client import LLMClient

from . import SECURED_PRODUCTS, WATCHLIST_SECTORS

NAME = "Due-Diligence Agent"

CRITICAL_FIELDS = ["revenue", "ebitda", "total_debt", "existing_debt_service", "incorporation_date",
                   "sanctions_screening", "pep_status"]


def _v(fields: dict, key: str) -> Any:
    return (fields.get(key) or {}).get("value")


# ---------------------------------------------------------------- missing info
def missing_info(app: dict, intake: dict, fields: dict, llm: LLMClient) -> dict[str, Any]:
    items = []
    for d in intake["required_documents"]:
        if d not in intake["received_documents"]:
            items.append({"type": "document", "item": d.replace("_", " ").title(), "clause": "CP-1 checklist"})
    for f in CRITICAL_FIELDS:
        if _v(fields, f) is None:
            items.append({"type": "field", "item": f.replace("_", " "), "clause": "Data completeness"})
    bo = str(_v(fields, "beneficial_owner_declaration") or "")
    if bo and "not" in bo.lower():
        items.append({"type": "declaration", "item": "Signed beneficial owner declaration", "clause": "CP-2.4"})
    audit = str(_v(fields, "audit_status") or "")
    if app["amount_usd"] > 1_000_000 and audit and "unaudited" in audit.lower():
        items.append({"type": "document", "item": "Audited financial statements FY2025-26", "clause": "CP-3.3"})

    def fallback() -> dict[str, Any]:
        if not items:
            return {"request_email": ""}
        bullets = "\n".join(f"  - {i['item']} ({i['clause']})" for i in items)
        return {
            "request_email": (
                f"Subject: {app['application_id']} - additional information required\n\n"
                f"Dear {app['relationship_manager']},\n\n"
                f"To progress the {app['product'].replace('_', ' ')} application for {app['borrower']} "
                f"(USD {app['amount_usd']:,.0f}), please obtain the following from the client:\n{bullets}\n\n"
                "The application is on hold until these are received; the SLA clock pauses on dispatch.\n\n"
                "Regards,\nCredit Operations (drafted by Due-Diligence Agent - pending human review)"
            )
        }

    draft = llm.complete_json(
        NAME,
        "Draft a concise, professional information-request email to the relationship manager listing each "
        'missing item and its policy reference. Return {"request_email": "..."}. Empty string if nothing is missing.',
        f"Application: {app['application_id']} {app['borrower']} {app['product']} USD {app['amount_usd']}\n"
        f"RM: {app['relationship_manager']}\nMissing: {items}",
        fallback,
    )
    return {"items": items, "request_email": draft.get("request_email", "") if items else ""}


# ---------------------------------------------------------------- ratios
def annual_debt_service(app: dict) -> float:
    p, r, n = app["amount_usd"], app["interest_rate"], app["tenor_years"]
    if app["product"] == "working_capital":
        return p * r  # revolving: interest-only servicing
    return p * r / (1 - (1 + r) ** -n)


def compute_metrics(app: dict, fields: dict) -> dict[str, Any]:
    ebitda, debt, eds = _v(fields, "ebitda"), _v(fields, "total_debt"), _v(fields, "existing_debt_service")
    coll = _v(fields, "collateral_value")
    new_ds = annual_debt_service(app)
    m: dict[str, Any] = {"proposed_annual_debt_service": round(new_ds)}
    if ebitda and eds is not None:
        m["dscr"] = round(ebitda / (eds + new_ds), 2)
        m["dscr_stressed_-20pct"] = round(ebitda * 0.8 / (eds + new_ds), 2)
    if ebitda and debt is not None:
        m["leverage"] = round((debt + app["amount_usd"]) / ebitda, 2)
    if coll:
        m["ltv"] = round(app["amount_usd"] / coll, 3)
    submitted = date.fromisoformat(app["submitted_on"])
    inc = _v(fields, "incorporation_date")
    if inc:
        m["vintage_years"] = round((submitted - date.fromisoformat(inc)).days / 365.25, 1)
    vd = _v(fields, "valuation_date")
    if vd:
        m["valuation_age_months"] = round((submitted - date.fromisoformat(vd)).days / 30.44, 1)
    return m


# ---------------------------------------------------------------- policy checks
def _check(cid, check, value, threshold, status, severity, note):
    return {"clause": cid, "check": check, "value": value, "threshold": threshold,
            "status": status, "severity": severity, "note": note}


def policy_checks(app: dict, fields: dict, m: dict, retriever) -> list[dict[str, Any]]:
    c = []
    product, amount, sector = app["product"], app["amount_usd"], app["sector"].lower()

    sanc = str(_v(fields, "sanctions_screening") or "")
    if sanc:
        hit = "match" in sanc.lower() and "no match" not in sanc.lower()
        c.append(_check("CP-2.1", "Sanctions screening", sanc, "No match", "FAIL" if hit else "PASS", "hard",
                        "Mandatory decline" if hit else "Clear"))
    pep = str(_v(fields, "pep_status") or "")
    if pep:
        is_pep = pep.lower().startswith("yes")
        c.append(_check("CP-2.2", "PEP status", pep, "No / EDD", "WARN" if is_pep else "PASS", "soft",
                        "Enhanced Due Diligence + escalate one authority level" if is_pep else "Clear"))
    media = str(_v(fields, "adverse_media") or "")
    if media:
        adverse = not media.lower().startswith("none")
        c.append(_check("CP-2.3", "Adverse media", media, "None", "WARN" if adverse else "PASS", "soft",
                        "Refer to Compliance before decision" if adverse else "Clear"))

    if "vintage_years" in m:
        v = m["vintage_years"]
        if v >= 3:
            c.append(_check("CP-3.1", "Operating vintage", f"{v} yrs", ">= 3 yrs", "PASS", "hard", "OK"))
        elif product == "project_finance":
            c.append(_check("CP-3.1", "Operating vintage", f"{v} yrs", ">= 3 yrs", "WARN", "soft",
                            "SPV < 3 yrs: sponsor corporate guarantee required"))
        else:
            c.append(_check("CP-3.1", "Operating vintage", f"{v} yrs", ">= 3 yrs", "FAIL", "hard", "Below minimum"))

    audit = str(_v(fields, "audit_status") or "")
    if audit and amount > 1_000_000:
        if "unaudited" in audit.lower():
            c.append(_check("CP-3.3", "Audited financials", audit, "Audited", "MISSING", "hard",
                            "Audited FS mandatory above USD 1M"))
        elif "qualified" in audit.lower() and "unqualified" not in audit.lower():
            c.append(_check("CP-3.3", "Audited financials", audit, "Unqualified", "WARN", "soft",
                            "Qualified opinion must be explained in memo"))
        else:
            c.append(_check("CP-3.3", "Audited financials", audit, "Audited", "PASS", "hard", "OK"))

    if "dscr" in m:
        d = m["dscr"]
        st = "PASS" if d >= 1.25 else ("WARN" if d >= 1.10 else "FAIL")
        c.append(_check("CP-4.1", "Pro-forma DSCR", f"{d:.2f}x", ">= 1.25x", st, "hard",
                        f"Stressed (-20% EBITDA) DSCR {m['dscr_stressed_-20pct']:.2f}x"))
    if "leverage" in m:
        limit = 6.0 if product == "project_finance" else 4.0
        lv = m["leverage"]
        c.append(_check("CP-4.2", "Pro-forma Debt/EBITDA", f"{lv:.2f}x", f"<= {limit}x",
                        "PASS" if lv <= limit else "FAIL", "hard", "OK" if lv <= limit else "Exceeds limit"))
    if product in SECURED_PRODUCTS:
        if "ltv" in m:
            ltv = m["ltv"]
            c.append(_check("CP-4.3", "Loan-to-Value", f"{ltv:.0%}", "<= 70%", "PASS" if ltv <= 0.70 else "FAIL",
                            "hard", "OK" if ltv <= 0.70 else "Exceeds limit"))
        valuer = str(_v(fields, "valuer") or "")
        age = m.get("valuation_age_months")
        if valuer:
            issues = []
            if "not on bank panel" in valuer.lower() or "sponsor" in valuer.lower():
                issues.append("valuer not bank-empanelled")
            if age is not None and age > 12:
                issues.append(f"valuation {age:.0f} months old (stale)")
            c.append(_check("CP-4.4", "Collateral valuation quality", valuer, "Empanelled, <= 12 months",
                            "WARN" if issues else "PASS", "soft", "; ".join(issues) or "OK"))

    if any(s in sector for s in WATCHLIST_SECTORS):
        c.append(_check("CP-5.1", "Sector watchlist", app["sector"], "Not on watchlist", "WARN", "soft",
                        "Sector-head concurrence + -20% revenue stress test"))
    bounces, od = _v(fields, "cheque_bounces_12m"), _v(fields, "od_peak_utilisation_pct")
    if bounces is not None:
        stress = bounces > 3 or (od or 0) > 90
        c.append(_check("CP-5.2", "Account conduct", f"{bounces:.0f} bounces, OD peak {od:.0f}%",
                        "<= 3 bounces, OD <= 90%", "WARN" if stress else "PASS", "soft",
                        "Cash-flow stress indicator" if stress else "OK"))
    conc = _v(fields, "customer_concentration_pct")
    if conc is not None:
        c.append(_check("CP-5.3", "Customer concentration", f"{conc:.0f}%", "<= 25%",
                        "PASS" if conc <= 25 else "WARN", "soft", "OK" if conc <= 25 else "Mitigant required"))

    for item in c:  # RAG grounding: attach the policy text each check relies on
        item["policy_text"] = retriever.get(item["clause"])["text"]
    return c


def run(app: dict, intake: dict, docintel: dict, llm: LLMClient, retriever) -> dict[str, Any]:
    fields = docintel["fields"]
    metrics = compute_metrics(app, fields)
    return {
        "missing": missing_info(app, intake, fields, llm),
        "metrics": metrics,
        "checks": policy_checks(app, fields, metrics, retriever),
    }

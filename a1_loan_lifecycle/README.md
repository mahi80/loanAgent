# Assignment 1: Agentic Loan Lifecycle Management

```bash
streamlit run a1_loan_lifecycle/app.py
```

## What the prototype does

Loan application → ingest supporting documents → extract information → identify missing information → policy and eligibility checks → risk observations → recommended next action → **human approval** → **auditable decision summary**.

| Tab | Shows |
|---|---|
| ⓪ Value stream | Lean VSM: VA / NVA / wait per step, takt time, PCE, bottlenecks, Automation Priority Index, before vs after. Demand and hours are editable. |
| ① Origination → Decision | Agent pipeline with timings, evidence-backed extraction, missing-info email draft, RAG-cited policy checks, risk grade, recommendation, credit memo, human gate and downloadable decision summary |
| ② Disbursement CPs | Condition-precedent checklist that blocks release until every CP is evidenced |
| ③ Portfolio monitoring | Covenant and early-warning (EWS) scan over 10 synthetic loans, with notes on Red accounts |
| ④ Audit & observability | Hash-chain validity, audit events, LLM telemetry (mode, latency, tokens) |

### Demo cases (synthetic)

| Case | Facility | Expected agent outcome |
|---|---|---|
| APP-1001 Greenfield Logistics | $4.0M term loan | All checks pass (DSCR 1.97x, LTV 53%) → **APPROVE**, Senior Credit Officer |
| APP-1002 Sunrise Agro Foods | $1.5M working capital | Missing bank statement, stock statement, BO declaration, audited FS → **REQUEST INFO** + draft email |
| APP-1003 Meridian Infra SPV | $28M project finance | DSCR 0.59x, leverage 10.2x, LTV 93%, PEP, adverse media, stale valuation, **prompt-injection text in a document** → **DECLINE**, Board Credit Committee |

Controls to try: approving above your role's authority is blocked, and overriding the agent without a rationale is blocked.

## Agents

| Agent | File | Role |
|---|---|---|
| Intake | `agents/intake.py` | Normalises the application, classifies the segment, inventories documents, screens for prompt injection |
| Document Intelligence | `agents/doc_intel.py` | LLM extraction with confidence and evidence. Each value is grounded against the source (regex fallback in mock mode). |
| Due-Diligence | `agents/due_diligence.py` | Missing docs and fields + drafted request; deterministic ratios (DSCR, stressed DSCR, leverage, LTV, vintage); policy checks cited to clauses |
| Risk | `agents/risk.py` | Transparent scorecard grade 1–10 + observations and mitigants (no protected attributes) |
| Approval / Workflow | `agents/approval.py` | Recommendation, authority routing (CP-6.1), conditions precedent, draft credit memo |
| Disbursement / CP | `agents/disbursement.py` | Gates disbursement until every CP is evidenced |
| Portfolio Monitoring | `agents/portfolio.py` | Quarterly covenant and EWS rules (CP-8.1) |

The orchestrator (`orchestrator.py`) is an explicit state machine that times each step and writes it to the audit log. Its nodes map one-to-one onto LangGraph, Azure AI Foundry Agent Service or Durable Functions in production. RAG uses TF-IDF over `knowledge/credit_policy.md` in the prototype; Azure AI Search replaces it in production.

## Value stream map (current state + agent overlay)

![VSM](../deliverables/img/a1_vsm_block.png)

```mermaid
flowchart LR
  subgraph VSM[Current state · Takt 1.31 h · PCE 6.0% · LT 34.5 d · capacity 66/mo vs demand 120]
    S1[1 Intake<br/>VA1 NVA2 W2d] --> S2[2 Completeness 🔴<br/>VA0.5 NVA4 W6d] --> S3[3 Extraction 🔴<br/>VA1.5 NVA4.5 W2d]
    S3 --> S4[4 KYC/DD<br/>VA2 NVA3 W3d] --> S5[5 Policy<br/>VA1 NVA2 W1d] --> S6[6 Appraisal/Memo 🔴<br/>VA6 NVA6 W4d]
    S6 --> S7[7 Approval 👤<br/>VA1.5 NVA1.5 W5d] --> S8[8 Docs/CP 🔴<br/>VA2 NVA3 W4d] --> S9[9 Disbursement<br/>VA1 NVA1.5 W2d]
  end
  A1[P1 Intake + Doc Intel<br/>missing-info + auto-chase] -.-> S2
  A4[P4 Doc Intel extraction] -.-> S3
  A5[P5 Due-Diligence] -.-> S4
  A2[P2 Risk Agent<br/>memo draft] -.-> S6
  H[👤 Human decision<br/>+ audit chain] ==> S7
  A3[P3 Condition Agent] -.-> S8
  S9 --> OUT[Future · LT 12.7 d · PCE 14.3% · capacity 131/mo · 0 steps over takt]
```

**Formulas:** Takt = available time ÷ demand. Effective CT = (VA + NVA) ÷ FTE. PCE = VA ÷ lead time. Automation Priority Index = NVA hours (touch + wait) × feasibility (1–5) × max(1, CT ÷ takt) ÷ 10.

## Assumptions

- **Synthetic data:** applications, documents, credit policy (CP-x clauses), portfolio and KYC results are all synthetic.
- **VSM inputs:** step times, FTEs and feasibility scores are mocked in `data/vsm_steps.csv`. Demand is 120 applications/month, available time is 21 days × 7.5 h, and 1 wait-day = 8 h.
- **Value:** the value estimate uses $60/h loaded analyst cost.
- **SLA:** SLA adherence (~30% → ~90%) assumes a 21-day SLA and a typical lead-time spread.
- **LLM modes:** in mock mode the LLM outputs are deterministic templates built from the same facts. In Azure mode the prompts are in each agent.

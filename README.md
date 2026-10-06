# FDE Client Challenge: Agentic AI prototypes

This repo holds two client scenarios. Each comes with a working prototype, a deck of 10 slides, architecture and value-stream diagrams, and stated assumptions.

| | Assignment 1: Financial institution | Assignment 2: Chemical manufacturer |
|---|---|---|
| Prototype | Agentic Loan Lifecycle: application → decision summary | Demand Prediction + Agentic Response: signal → SAP action |
| App | `streamlit run a1_loan_lifecycle/app.py` | `streamlit run a2_chem_demand/app.py` |
| Deck | [deliverables/A1_Loan_Lifecycle_Deck.pptx](deliverables/A1_Loan_Lifecycle_Deck.pptx) | [deliverables/A2_Chemical_Demand_Deck.pptx](deliverables/A2_Chemical_Demand_Deck.pptx) |
| Architecture | [deliverables/img/a1_architecture.png](deliverables/img/a1_architecture.png) | [deliverables/img/a2_architecture.png](deliverables/img/a2_architecture.png) |
| Value stream map | [deliverables/img/a1_vsm_block.png](deliverables/img/a1_vsm_block.png) | [deliverables/img/a2_vsm_block.png](deliverables/img/a2_vsm_block.png) |
| Details | [a1_loan_lifecycle/README.md](a1_loan_lifecycle/README.md) | [a2_chem_demand/README.md](a2_chem_demand/README.md) |

## Quick start

```bash
pip install -r requirements.txt
```

```bash
streamlit run a1_loan_lifecycle/app.py
```

```bash
streamlit run a2_chem_demand/app.py
```

**LLM.** Copy `.env.example` to `.env` and set either `AZURE_OPENAI_*` (Azure OpenAI) or `OPENAI_API_KEY` (OpenAI API). Without credentials, the agents run in **deterministic mock mode**, so every demo works offline and gives the same result each time. `LLM_MODE=auto|azure|openai|mock`. `.env` is git-ignored.

### Run in Docker

Both prototypes run from one image with two services:

```bash
docker compose up --build -d
```

- A1 loan lifecycle: http://localhost:8501
- A2 demand response: http://localhost:8502

`.env` is optional and is picked up automatically. Audit logs and the mock SAP outbox are kept in the `runtime` volume. To stop the services:

```bash
docker compose down
```

**Rebuild the diagrams and decks:**

```bash
python deliverables/diagrams.py
```

```bash
python deliverables/build_decks.py
```

**Regenerate the A2 synthetic data:**

```bash
python a2_chem_demand/data/generate_synthetic.py
```

## Design principles (both prototypes)

1. **Lean first, AI second.** A value stream map (VA / NVA / wait, takt, PCE) and an Automation Priority Index decide where agents go. The engine is `shared/vsm.py` and it's shown in tab ⓪/① of each app.
2. **Deterministic numbers, LLM narrative.** Ratios, policy outcomes, costs and quantities come from code. The LLM extracts, explains and drafts, and it never sets a number.
3. **Human in control.** Agents recommend. Authority matrices and value thresholds are enforced in code, and any override needs a rationale.
4. **Auditable.** Every step is written to a hash-chained JSONL log (`shared/audit.py`) that records the inputs hash, actor and model.
5. **Responsible AI.** PII is masked before model calls, there's a prompt-injection screen on documents, a grounding check on extracted values, and no protected attributes are used in risk scoring.

## Repository layout

```
shared/            llm_client (Azure OpenAI + mock, PII mask, injection guard), audit chain, VSM engine + Streamlit view
a1_loan_lifecycle/ agents/, orchestrator.py, knowledge/ (policy + RAG), data/ (synthetic applications, docs, portfolio, VSM)
a2_chem_demand/    agents/, orchestrator.py, forecasting.py, data/ (generator, SAP-like CSVs, opportunities, VSM)
deliverables/      diagrams.py, build_decks.py, img/, *.pptx
```

## Assumptions & synthetic data

**All data is synthetic.** VSM step times are **mocked**. Takt, PCE, capacity, priority index and before/after KPIs are **computed** from them. Financial benefits are illustrative ranges, and each slide states its basis. SAP/IBP transactions are mock payloads written to `runtime/sap_outbox.jsonl`.

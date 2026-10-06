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

## Quick start: Docker (recommended)

You need Docker Desktop (Windows / macOS) or Docker Engine + Compose v2 (Linux). See **[docs/DOCKER.md](docs/DOCKER.md)** for the full install guide, LLM options, Ollama setup and troubleshooting.

```bash
git clone https://github.com/mahi80/loanAgent.git
```

```bash
cd loanAgent
```

```bash
docker compose up --build -d
```

- A1 Agentic Loan Lifecycle: http://localhost:8501
- A2 Demand Sensing + Agentic Response: http://localhost:8502

That's all you need for an offline demo in **mock mode**. To use a real LLM, copy `.env.example` to `.env`, pick a mode (see below), and recreate the containers:

```bash
docker compose up -d --force-recreate
```

To stop the services:

```bash
docker compose down
```

### LLM modes (`.env`)

| Mode | Settings | Notes |
|---|---|---|
| Mock (default) | none, or `LLM_MODE=mock` | Offline, same result every run |
| Ollama (local) | `LLM_MODE=ollama`, `OLLAMA_MODEL=gemma4:e4b` | Free; data stays on the machine; see [Ollama notes](docs/DOCKER.md#ollama-notes) |
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-4o-mini` | |
| Azure OpenAI | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` | |

`LLM_MODE=auto` picks Azure, then OpenAI, then Ollama, then mock. `.env` is git-ignored and never copied into the image. If an LLM call fails, it falls back to deterministic output and the failure is logged in the Audit & observability tab.

## Alternative: run with local Python

You need Python 3.12.

```bash
pip install -r requirements.txt
```

```bash
streamlit run a1_loan_lifecycle/app.py
```

```bash
streamlit run a2_chem_demand/app.py
```

When running locally, Ollama is reached at `http://localhost:11434/v1`.

## Tests and utilities

**Retrieval eval** for the policy assistant (13/13 expected):

```bash
python a1_loan_lifecycle/knowledge/eval_retriever.py
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
shared/            llm_client (Azure / OpenAI / Ollama + mock, PII mask, injection guard), audit chain, VSM engine + view
docs/DOCKER.md     Docker install & run guide
a1_loan_lifecycle/ agents/, orchestrator.py, knowledge/ (policy, hybrid RAG, assistant, eval), data/ (synthetic applications, docs, portfolio, VSM)
a2_chem_demand/    agents/, orchestrator.py, forecasting.py, data/ (generator, SAP-like CSVs, opportunities, VSM)
deliverables/      diagrams.py, build_decks.py, img/, *.pptx
Dockerfile, docker-compose.yml, .env.example
```

## Assumptions & synthetic data

**All data is synthetic.** VSM step times are **mocked**. Takt, PCE, capacity, priority index and before/after KPIs are **computed** from them. Financial benefits are illustrative ranges, and each slide states its basis. SAP/IBP transactions are mock payloads written to `runtime/sap_outbox.jsonl`.

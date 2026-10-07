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

### Run with a local LLM in Docker (Ollama container + automatic model pull)

With an NVIDIA GPU:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml -f docker-compose.ollama.gpu.yml up --build -d
```

CPU only (slower):

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up --build -d
```

The first start downloads the Ollama image (about 3 GB) and `gemma4:e4b` (about 6.6 GB) into the `ollama` volume. On an RTX 4080 Laptop this runs at about 1.6–6 s per agent call, depending on the GPU power state. The apps start once the pull finishes, and later starts reuse the volume. Details: [docs/DOCKER.md](docs/DOCKER.md#ollama-inside-docker-no-host-install).

### LLM modes (`.env`)

| Mode | Settings | Notes |
|---|---|---|
| Mock (default) | none, or `LLM_MODE=mock` | Offline, same result every run |
| Ollama **in Docker** | start with the add-on file (below); optional `OLLAMA_MODEL` | Nothing to install; the model is pulled automatically |
| Ollama on the host | `LLM_MODE=ollama`, `OLLAMA_MODEL=gemma4:e4b` | Uses an existing host install; see [host notes](docs/DOCKER.md#ollama-on-the-host-alternative) |
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

## Production-readiness (POC placeholders with an upgrade path)

| Concern | What the POC does today | Production upgrade (config, not rewrite) |
|---|---|---|
| **AuthN / AuthZ** | Sidebar sign-in with demo identities (`AUTH_MODE=demo`). The approver's role comes from the identity, so it can't be self-selected. Actions are role-gated, and the orchestrator still enforces authority limits. | `AUTH_MODE=oidc`: SSO through Streamlit's `st.login` with Entra ID, Cognito or Okta. Roles come from a token claim (`AUTH_ROLE_CLAIM`, `AUTH_ROLE_MAP`). Plus JWT validation at API Gateway / API Management. |
| **Observability** | Every run is traced (pipeline → agent → LLM call spans with latency, tokens and fallbacks) to `runtime/traces.jsonl`. The Audit & observability tab shows a waterfall, alongside the hash-chained audit log and LLM telemetry. | Set `OTEL_EXPORTER_OTLP_ENDPOINT` to export the same spans to Langfuse, Jaeger, X-Ray (ADOT) or Application Insights. |
| **Eval harness** | `evals/run_evals.py` runs 50 golden checks across loans, RAG and demand: outcomes, LLM-only field accuracy, citations, refusals, authority and threshold controls, injection detection and the audit chain. It works with every LLM mode. | Run it as a CI gate on each PR and nightly against the production model, and track pass rate and accuracy over time. |
| **Ingestion** | **📥 New application** tab: upload txt / md / pdf files, which are extracted, classified and landed, then go through the normal pipeline with injection screening. You can also upload a policy addendum and re-index the RAG store. | S3 / Blob landing, event triggers, Textract / Document Intelligence OCR, malware scan, and OpenSearch / AI Search indexing. |
| **Security** | PII masking before LLM calls, prompt-injection quarantine, grounding check, deterministic maths, non-root container, secrets only in `.env` | Key Vault / Secrets Manager, private networking, WAF, Guardrails / Content Safety (see appendix deployment slides) |

Demo identities, which are POC only and have no passwords:

| App | Identity | Role and what it can do |
|---|---|---|
| A1 | A. Mehta | Credit Analyst: run pipelines and ingest applications, but not decide |
| A1 | R. Iyer · J. Smith · C. Kumar · B. Board | Credit Manager → Board Credit Committee: decide within authority (CP-6.1). Policy upload needs Credit Manager or above. |
| A1 / A2 | Auditor / Finance (read-only) | Viewer: view only |
| A2 | P. Planner · L. Chen | Demand Planner (plans up to $50k) · S&OP Lead |

## Tests and utilities

**Agent eval harness.** 50 checks; writes `runtime/eval_report.json`; exits with code 1 on any failure:

```bash
python evals/run_evals.py --mode mock
```

The same harness against the configured LLM, e.g. Ollama gemma4. That run also scored 50/50, with 91–100% LLM-only field accuracy:

```bash
python evals/run_evals.py
```

Inside Docker:

```bash
docker exec a1-loan-lifecycle python evals/run_evals.py
```

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
shared/            llm_client (Azure / OpenAI / Ollama + mock, PII mask, injection guard), audit chain,
                   auth (demo / OIDC roles), observability (tracing + OTel export), VSM engine + views
docs/DOCKER.md     Docker install & run guide
a1_loan_lifecycle/ agents/, orchestrator.py, ingestion.py, knowledge/ (policy, hybrid RAG, assistant, eval), data/ (synthetic applications, docs, portfolio, VSM)
a2_chem_demand/    agents/, orchestrator.py, forecasting.py, data/ (generator, SAP-like CSVs, opportunities, VSM)
evals/             run_evals.py + golden.json (agent eval harness)
deliverables/      diagrams.py, deployment_diagrams.py, build_decks.py, img/, *.pptx (10 slides + 3 appendix)
Dockerfile, docker-compose.yml (+ .ollama.yml / .ollama.gpu.yml add-ons), .env.example
```

## Assumptions & synthetic data

**All data is synthetic.** VSM step times are **mocked**. Takt, PCE, capacity, priority index and before/after KPIs are **computed** from them. Financial benefits are illustrative ranges, and each slide states its basis. SAP/IBP transactions are mock payloads written to `runtime/sap_outbox.jsonl`.

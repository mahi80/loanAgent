# Install and run with Docker

This guide runs both prototypes in containers on Windows, macOS or Linux. One image serves both apps through two Compose services:

| Service | Container | URL |
|---|---|---|
| A1 Agentic Loan Lifecycle | `a1-loan-lifecycle` | http://localhost:8501 |
| A2 Demand Sensing + Agentic Response | `a2-demand-response` | http://localhost:8502 |

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Docker Desktop 4.x (Windows / macOS) or Docker Engine + Compose v2 (Linux) | Check with `docker --version` and `docker compose version`. Docker Desktop must show **Engine running**. |
| Git | To clone the repo |
| ~2 GB free disk | Image is about 1 GB (Python 3.12 slim + scientific stack) |
| Ports 8501 and 8502 free | Change them in `docker-compose.yml` if they're taken |
| *Optional:* an LLM | Mock mode (default) needs nothing. You can also use OpenAI, Azure OpenAI, or a local [Ollama](https://ollama.com). See step 3. |

## 2. Get the code

```bash
git clone https://github.com/mahi80/loanAgent.git
```

```bash
cd loanAgent
```

## 3. Choose an LLM mode (optional)

Copy the template. `.env` is git-ignored and is never copied into the image.

```bash
cp .env.example .env
```

On Windows PowerShell, use `copy .env.example .env`. Then edit `.env` and pick **one** of these:

| Mode | Put in `.env` | When to use |
|---|---|---|
| **Mock** (default) | `LLM_MODE=mock` (or no `.env` at all) | Offline demos. The answers are fixed, so every run gives the same result. |
| **Ollama in Docker** (local, free, nothing to install) | `OLLAMA_MODEL=gemma4:e4b` (optional) and start with the add-on Compose file | See [Ollama inside Docker](#ollama-inside-docker-no-host-install) |
| **Ollama on the host** | `LLM_MODE=ollama`<br>`OLLAMA_MODEL=gemma4:e4b` | You already run Ollama on the host. See [Ollama on the host](#ollama-on-the-host-alternative). |
| **OpenAI** | `OPENAI_API_KEY=sk-...`<br>`OPENAI_MODEL=gpt-4o-mini` | You have an OpenAI key |
| **Azure OpenAI** | `AZURE_OPENAI_ENDPOINT=...`<br>`AZURE_OPENAI_API_KEY=...`<br>`AZURE_OPENAI_DEPLOYMENT=gpt-4o` | Enterprise / client tenant |

With `LLM_MODE=auto`, the app uses Azure if it's configured, then OpenAI, then Ollama, then mock. If a provider call fails, that call falls back to deterministic output and the failure is logged in the **Audit & observability** tab, so a demo never breaks.

> Never commit `.env`, and never paste keys into chats or tickets. If a key leaks, revoke it straight away.

## 4. Build and start

```bash
docker compose up --build -d
```

The first build takes 2–5 minutes, and later builds are cached. Check that both containers report **healthy**:

```bash
docker compose ps
```

Then open http://localhost:8501 and http://localhost:8502. The sidebar shows the active **LLM mode** and model.

## 5. Verify the setup

Health endpoints (both should return `ok`):

```bash
curl http://localhost:8501/_stcore/health
```

```bash
curl http://localhost:8502/_stcore/health
```

Check which LLM each container is using. Expect `mock-deterministic-v1`, `ollama:<model>`, `openai:<model>` or `azure:<deployment>`:

```bash
docker exec a1-loan-lifecycle python -c "import sys; sys.path.insert(0,'.'); from shared.llm_client import LLMClient; print(LLMClient().model_name)"
```

Run the retrieval eval inside the container (expects 13/13):

```bash
docker exec a1-loan-lifecycle python a1_loan_lifecycle/knowledge/eval_retriever.py
```

**Smoke-test the demo in the UI:**
- **A1:** pick **APP-1003**, then **Run agent pipeline**. Expect **DECLINE** routed to the Board Credit Committee. Then open **💬 Policy assistant** and ask "Who approves a $15M loan with a policy exception?" (expect Board Credit Committee, citing CP-6.1).
- **A2:** in **③ Agentic response**, click **Run response agents** on the EPX-200 / APAC alert. Expect a least-cost plan routed to the S&OP Lead.

## 6. Day-to-day commands

| Task | Command |
|---|---|
| Follow logs | `docker compose logs -f` |
| Logs for one app | `docker compose logs -f loan-lifecycle` |
| Stop (keep data) | `docker compose down` |
| Restart after editing `.env` | `docker compose up -d --force-recreate` |
| Rebuild after code changes / `git pull` | `docker compose up --build -d` |
| Run only one app | `docker compose up --build -d loan-lifecycle` |
| Shell into a container | `docker exec -it a1-loan-lifecycle sh` |
| Reset audit logs / SAP outbox | `docker compose down -v` (deletes the `runtime` volume) |
| Remove the image | `docker image rm loanagent-fde:latest` |

`.env` is read when a container is **created**, so use `--force-recreate` after changing it. A plain `restart` keeps the old values.

## 7. Updating to the latest version

```bash
git pull
```

```bash
docker compose up --build -d
```

## Ollama inside Docker (no host install)

This option needs nothing installed on the host apart from Docker. An add-on Compose file starts an **Ollama container**, **pulls the model automatically**, and points both apps at it. Models are kept in the `ollama` volume, so the download happens only once.

**NVIDIA GPU** (recommended; needs an NVIDIA driver, plus Docker Desktop with the WSL2 backend or the NVIDIA Container Toolkit on Linux). Measured on an RTX 4080 Laptop: about 1.6 s per agent call, 7–14 s per loan case, 100% GPU:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml -f docker-compose.ollama.gpu.yml up --build -d
```

**CPU only.** This works anywhere, but each call is much slower (about 30–90 s with `gemma4:e4b`; try `OLLAMA_MODEL=gemma4:e2b`):

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up --build -d
```

What happens on start:

1. `ollama` starts and becomes healthy.
2. `ollama-pull` runs `ollama pull $OLLAMA_MODEL` (default `gemma4:e4b`, about 6.6 GB on first run) and exits.
3. The two apps start only after the pull succeeds, with `LLM_MODE=ollama` and `OLLAMA_BASE_URL=http://ollama:11434/v1`.

Follow the download progress:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml logs -f ollama-pull
```

To choose another model, set `OLLAMA_MODEL=...` in `.env` and run the same `up` command again. Other commands:

| Task | Command |
|---|---|
| Models in the container | `docker exec ollama ollama list` |
| Is it using the GPU? | `docker exec ollama ollama ps` (look for `100% GPU`) |
| Pull another model by hand | `docker exec ollama ollama pull mistral` |
| Stop everything | `docker compose -f docker-compose.yml -f docker-compose.ollama.yml down` |
| Delete downloaded models | `docker volume rm loanagent_ollama` (the prefix is your folder name, so check `docker volume ls`) |

The container's API is also published on **http://localhost:11435** (not 11434), so it doesn't clash with an Ollama already installed on the host.

> **Tip:** to save typing, put `COMPOSE_FILE=docker-compose.yml:docker-compose.ollama.yml:docker-compose.ollama.gpu.yml` in `.env`. On Windows, use `;` instead of `:`. After that, plain `docker compose up --build -d` includes Ollama.

## Ollama on the host (alternative)

If Ollama is already installed on the host, the default `docker-compose.yml` (without the add-on files) uses it. The containers reach Ollama on the host through `http://host.docker.internal:11434/v1`. That address is set in `docker-compose.yml`, with a `host-gateway` mapping so it also works on Linux.

1. Pull a model on the host. `gemma4:e4b` is a good default for a 12 GB GPU. Smaller GPUs can try `gemma4:e2b`, and larger ones `gemma4:26b`.

```bash
ollama pull gemma4:e4b
```

2. Set `LLM_MODE=ollama` and `OLLAMA_MODEL=gemma4:e4b` in `.env`, then recreate the containers:

```bash
docker compose up -d --force-recreate
```

3. Optional tuning in `.env`:
   - `OLLAMA_REASONING=none` (the default) turns off model "thinking", which is about 3× faster for extraction. Set it to `default` to keep thinking on.
   - `OLLAMA_TIMEOUT=180` sets the per-call timeout in seconds.

4. **Linux hosts:** Ollama listens on `127.0.0.1` by default, which containers can't reach. Make it listen on the Docker bridge as well:

```bash
sudo systemctl edit ollama
```

Add these lines, then run `sudo systemctl restart ollama`:

```
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

5. **Windows with Ollama inside WSL (Ubuntu):** if the Ollama Windows app is also running, it holds port 11434 and the containers talk to it instead of the WSL one. Quit the Windows Ollama tray app (and turn off its autostart), then restart the WSL service so WSL forwards the port:

```bash
wsl -d Ubuntu -u root -- systemctl restart ollama
```

Check what the containers see:

```bash
docker exec a1-loan-lifecycle python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/v1/models').read()[:300])"
```

**Performance:** the model must fit in VRAM. With 12 GB, `gemma4:e4b` (about 10 GB) runs fully on the GPU at about 3–4 s per agent call. If `ollama ps` shows a CPU/GPU split, unload other models (`ollama stop <model>`) and retry.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` | Docker Desktop isn't running. Start it and wait for **Engine running**. |
| Docker Desktop shows *"An unexpected error occurred … dockerInference … The file cannot be accessed by the system"* (or the same for `docker-secrets-engine\engine.sock`) | A stale socket file from an earlier Docker version. Quit Docker Desktop, rename `%LOCALAPPDATA%\Docker\run` to `run.old` (and likewise `%LOCALAPPDATA%\docker-secrets-engine`), then start Docker Desktop again. It recreates the folders. Don't use *Reset to factory defaults*: it isn't needed, and it wipes your images and settings. |
| `Bind for 0.0.0.0:8501 failed: port is already allocated` | Another app (often a local `streamlit run`) uses the port. Stop it, or change the left-hand port in `docker-compose.yml`, e.g. `"9501:8501"`. |
| Sidebar shows `mock-deterministic-v1` although `.env` is set | The container was created before `.env` changed (run `docker compose up -d --force-recreate`), or the image is out of date after a code change (run `docker compose up --build -d`). |
| `could not select device driver "nvidia"` when using the GPU file | No NVIDIA GPU or driver is visible to Docker. Update the NVIDIA driver, or drop `-f docker-compose.ollama.gpu.yml` to run on CPU. |
| Apps don't start with the Ollama add-on | They wait for `ollama-pull`. Check `docker compose ... logs ollama-pull` for a typo in the model name or a network error. |
| Ollama mode is slow (more than 20 s per call) | The model is split between CPU and GPU, or another model holds VRAM. Check `ollama ps`, unload other models, and use a smaller model. |
| The Ollama model returns empty or odd fields | Small models (around 7B) often mis-format JSON. The app tolerates this and fills gaps with the rule-based parser (flagged `llm_missed` in the Document Intelligence table). For better quality, use `gemma4:e4b` or larger. |
| Container is `unhealthy` | `docker compose logs <service>`. Usually a Python import error after editing code; rebuild with `--build`. |
| Numbers differ slightly from the decks | The forecasting model gives results within 1% between Linux (Docker) and Windows, because floating-point maths differs. For example, the gap is 749 t vs 752 t. Run locally if the demo must match the slides exactly. |

## What's in the image

- `python:3.12-slim`, dependencies pinned in `requirements.txt`, runs as non-root `appuser`, with a Streamlit health check.
- It contains `shared/`, `a1_loan_lifecycle/` and `a2_chem_demand/`. `.dockerignore` excludes `.env`, `.git`, decks and runtime data.
- `APP` and `PORT` choose which app a container serves, so the same image is used for both services.
- The named volume `runtime` (mounted at `/app/runtime`) keeps the hash-chained audit logs and the mock SAP outbox across restarts.

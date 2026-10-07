"""Deployment architecture diagrams (appendix slides).

* poc_deployment.png         - what runs today: Docker Compose + Ollama (GPU)
* {a1,a2}_deploy_{aws,azure} - target production deployment per cloud,
                               mapped to each assignment's agents and systems

Run:  python deliverables/deployment_diagrams.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent / "img"
OUT.mkdir(exist_ok=True)

NAVY, TEAL, ORANGE, GREY, GREEN, RED, BLUE, PURPLE, AMBER, PINK = (
    "#1F3A5F", "#2A9D8F", "#E76F51", "#6C757D", "#2E7D32", "#C62828", "#1565C0", "#6A4C93", "#F4A261", "#AD1457")
plt.rcParams.update({"font.family": "DejaVu Sans"})


def bullets(lines):
    """'  continued' lines (leading spaces) continue the previous bullet without a new marker."""
    return "\n".join(("    " + l.strip()) if l.startswith("  ") else f"• {l}" for l in lines)


def panel(ax, x, y, w, h, title, lines, color, size=8.0, title_size=10, fill=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.6",
                                fc=fill or color + "12", ec=color, lw=1.3))
    ax.text(x + 0.5, y + h - 0.6, title, fontsize=title_size, fontweight="bold", color=color, va="top")
    ax.text(x + 0.5, y + h - (4.2 if "\n" in title else 2.8), bullets(lines), fontsize=size, color="#222",
            va="top", linespacing=1.4)


def card(ax, x, y, w, h, title, lines, color, size=7.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.5", fc="white", ec=color, lw=1.1))
    ax.text(x + w / 2, y + h - 0.6, title, fontsize=8.8, fontweight="bold", color=color, va="top", ha="center")
    ax.text(x + 0.4, y + h - 3.0, bullets(lines), fontsize=size, color="#222", va="top", linespacing=1.4)


def arrow(ax, x1, y1, x2, y2, color=NAVY, lw=1.3, ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=10, color=color, lw=lw,
                                 linestyle=ls))


def save(fig, name):
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", name)


# ---------------------------------------------------------------- cloud service catalogues
CLOUD = {
    "aws": {
        "name": "AWS", "color": "#FF9900",
        "identity": ["IAM Identity Center (SSO)", "Cognito for external users", "OAuth2 / OIDC / SAML, MFA",
                     "Groups → roles → scopes"],
        "network": "Route 53 · CloudFront (CDN) · AWS WAF · Shield (DDoS) · VPC public/private subnets · Security Groups · "
                   "NACLs · PrivateLink / VPC endpoints",
        "edge": ["API Gateway: JWT validation,", "  rate limiting, routing", "Cognito / IAM authorizers",
                 "RBAC/ABAC from token claims"],
        "runtime": "ECS on Fargate (or EKS)",
        "llm": ["Amazon Bedrock (Claude /", "  Llama) + Bedrock Guardrails", "Optional self-hosted: vLLM /",
                "  Ollama on EKS GPU nodes", "Prompt registry + versions"],
        "data": ["Amazon RDS for PostgreSQL", "  (pgvector, cases, audit tables)", "ElastiCache Redis (memory)",
                 "AWS Secrets Manager / KMS"],
        "devops": ["GitHub Actions / CodePipeline", "Amazon ECR (images)", "Terraform (IaC)",
                   "Blue/green, Dev→UAT→Prod"],
        "ingest": ["S3 (raw docs) → EventBridge", "Step Functions / Glue jobs", "Chunk, embed (Bedrock),",
                   "  incremental re-index"],
        "docs": ["Amazon Textract", "OCR, tables, key-values", "Layout → JSON to S3"],
        "search": ["Amazon OpenSearch", "  (vector + BM25 hybrid)", "Metadata filters + ACLs"],
        "hitl": ["Approval UI + Amazon A2I", "Teams / Slack approvals", "Feedback store (RDS)",
                 "Eval sets, red teaming"],
        "ml": ["Amazon SageMaker", "Training, registry, endpoints", "Pipelines, drift monitor"],
        "obs": ["CloudWatch logs/metrics, X-Ray", "OpenTelemetry → Langfuse", "Per-agent latency, tokens, cost"],
        "audit": ["CloudTrail, AWS Config", "S3 Object Lock (WORM) for", "  hash-chained decision log"],
        "dr": ["Multi-AZ RDS + read replica", "Cross-region S3 / backups", "Fargate tasks across AZs"],
        "cost": ["AWS Budgets, Cost Explorer", "Tagging per agent / tenant", "Macie PII discovery"],
    },
    "azure": {
        "name": "Azure", "color": "#0078D4",
        "identity": ["Microsoft Entra ID (SSO)", "OAuth2 / OIDC, MFA", "Conditional Access",
                     "Groups → app roles"],
        "network": "Azure Front Door (CDN + WAF) · VNet with private subnets · Private Endpoints · NSGs · "
                   "Azure Firewall · DDoS Protection",
        "edge": ["Azure API Management:", "  JWT (Entra ID), rate limits,", "  routing, policies",
                 "RBAC from token claims"],
        "runtime": "Azure Container Apps (or AKS)",
        "llm": ["Azure OpenAI (GPT-4o family)", "Azure AI Content Safety", "Optional self-hosted: vLLM /",
                "  Ollama on AKS GPU nodes", "Prompt registry + versions"],
        "data": ["Azure Database for PostgreSQL", "  (pgvector, cases, audit)", "Azure Cache for Redis",
                 "Key Vault + Managed Identity"],
        "devops": ["GitHub Actions / Azure DevOps", "Azure Container Registry", "Bicep / Terraform (IaC)",
                   "Revisions, Dev→UAT→Prod"],
        "ingest": ["Blob / ADLS Gen2 → Event Grid", "Data Factory + Functions", "Chunk, embed (Azure OpenAI),",
                   "  incremental re-index"],
        "docs": ["Azure AI Document", "  Intelligence", "OCR, tables, key-values → JSON"],
        "search": ["Azure AI Search", "  (vector + BM25 + semantic)", "Security trimming filters"],
        "hitl": ["Approval UI + Teams", "  adaptive cards / Power Automate", "Feedback store (PostgreSQL)",
                 "Eval sets, red teaming"],
        "ml": ["Azure Machine Learning", "Training, registry, endpoints", "MLflow, drift monitor"],
        "obs": ["Azure Monitor, App Insights", "OpenTelemetry → Langfuse", "Per-agent latency, tokens, cost"],
        "audit": ["Activity Log, Azure Policy", "Immutable Blob (WORM) for", "  hash-chained decision log, Purview"],
        "dr": ["Zone-redundant Container Apps", "PostgreSQL HA + geo-backup", "GRS storage, paired region"],
        "cost": ["Cost Management + Budgets", "Tagging per agent / tenant", "Purview data classification"],
    },
}

ASSIGNMENT = {
    "a1": {
        "title": "Agentic Loan Lifecycle",
        "users": ["Credit analysts, RMs", "Approvers (authority matrix)", "Ops: CP & portfolio teams",
                  "Web app · Teams · LOS"],
        "agents": ["Intake · Doc Intelligence", "Due-Diligence · Risk", "Approval / Workflow",
                   "Disbursement · EWS", "Policy assistant (RAG)"],
        "mcp_tools": ["los.get_application", "kyc.screen / bureau.pull", "policy.search", "los.update_status"],
        "enterprise": ["LOS (nCino / Finastra)", "Core banking (T24)", "Credit bureau, KYC,",
                       "  sanctions, adverse media", "DMS + e-mail (Graph)"],
        "sources": ["Loan documents (PDF)", "LOS + core banking", "Credit policy corpus",
                    "Covenant / portfolio data"],
        "ml_use": "PD / scorecard models",
    },
    "a2": {
        "title": "Demand Sensing + Agentic Response",
        "users": ["Demand planners", "S&OP lead (approvals)", "Logistics & plant schedulers",
                  "Web cockpit · Teams"],
        "agents": ["Deviation · Impact", "Constraint · Recommender", "Executor · Notification",
                   "Sensing job (daily)"],
        "mcp_tools": ["sap.get_stock / capacity", "sap.create_sto", "sap.change_planned_order", "ibp.update_plan"],
        "enterprise": ["SAP S/4HANA (OData / BAPI", "  via SAP BTP)", "SAP IBP (plans)", "TMS / carriers, CRM",
                       "Market data (PMI, feedstock)"],
        "sources": ["SAP orders, stock, capacity", "IBP consensus plans", "TMS events, promos",
                    "External signals feeds"],
        "ml_use": "Demand-sensing model",
    },
}


def cloud_deployment(cloud: str, asg: str) -> str:
    c, a = CLOUD[cloud], ASSIGNMENT[asg]
    col = c["color"]
    fig, ax = plt.subplots(figsize=(20, 9.6))   # ~2.1:1, matches the slide's image area
    ax.set_xlim(0, 100)
    ax.set_ylim(3.2, 52)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 49.4), 100, 2.6, boxstyle="round,pad=0.02,rounding_size=0.5", fc=NAVY, ec=NAVY))
    ax.text(50, 50.7, f"{c['name']} - {a['title']} - production deployment architecture (agents + MCP + PostgreSQL)",
            fontsize=13, fontweight="bold", color="white", ha="center", va="center")
    import textwrap

    # row A: users / identity / network
    panel(ax, 0, 41.2, 17, 7.6, "1. Users / channels", a["users"], BLUE)
    panel(ax, 18, 41.2, 17, 7.6, "2. Identity & access", c["identity"], RED)
    ax.add_patch(FancyBboxPatch((36, 41.2), 64, 7.6, boxstyle="round,pad=0.02,rounding_size=0.6", fc=GREEN + "10",
                                ec=GREEN, lw=1.3))
    ax.text(36.5, 48.2, "3. Network & security (private by default)", fontsize=10, fontweight="bold", color=GREEN,
            va="top")
    ax.text(36.5, 45.7, textwrap.fill(c["network"], 125), fontsize=8.6, color="#222", va="top", linespacing=1.4)
    ax.text(36.5, 42.9, "All app, data and model traffic on private networking; only the edge is public.",
            fontsize=8.6, color=GREY, va="top", style="italic")

    # row B: edge / application / llm / data / enterprise   (y 27.6 .. 40.4)
    yb, hb = 27.6, 12.8
    panel(ax, 0, yb, 13, hb, "4. Edge & auth", c["edge"], PURPLE)
    ax.add_patch(FancyBboxPatch((14, yb), 44, hb, boxstyle="round,pad=0.02,rounding_size=0.6", fc=AMBER + "14",
                                ec=ORANGE, lw=1.4))
    ax.text(14.5, yb + hb - 0.5, f"5. Application layer - {c['runtime']}", fontsize=10, fontweight="bold",
            color=ORANGE, va="top")
    cw, cy, ch = 10.4, yb + 0.5, hb - 2.9
    card(ax, 14.6, cy, cw, ch, "Web UI + API", ["Streamlit → React", "FastAPI: validate JWT,", "  sessions, streaming",
                                               "Input validation", "Audit every request"], BLUE)
    card(ax, 14.6 + cw + 0.4, cy, cw, ch, "Agent orchestrator", ["LangGraph state graph", *a["agents"][:4],
                                                                 "Human gate in graph"], TEAL)
    card(ax, 14.6 + 2 * (cw + 0.4), cy, cw, ch, "MCP server", ["Tool allow-list", "AuthZ per role (RBAC)",
                                                               "Input enforcement", *a["mcp_tools"][:3]], PINK)
    card(ax, 14.6 + 3 * (cw + 0.4), cy, cw, ch, "Workers / jobs", ["Doc ingestion worker", "Scheduled sensing /",
                                                                   "  EWS scans", "Queue-driven, autoscaled",
                                                                   "Idempotent retries"], GREY)
    panel(ax, 59, yb, 13, hb, "6. LLM layer", c["llm"], PURPLE)
    panel(ax, 73, yb, 12.5, hb, "7. Data access", c["data"], BLUE)
    panel(ax, 86.5, yb, 13.5, hb, "8. Enterprise systems\n    (via MCP tools)", a["enterprise"], NAVY)

    # row C: devops / sources / ingestion / docs / search / hitl / ml   (y 15.0 .. 26.6)
    yc, hc = 15.0, 11.6
    panel(ax, 0, yc, 13, hc, "9. DevOps & deploy", c["devops"], GREY)
    panel(ax, 14, yc, 13, hc, "10. Data sources", a["sources"] + ["(data stays at source)"], NAVY)
    panel(ax, 28, yc, 14.5, hc, "11. Ingestion pipeline", c["ingest"], TEAL)
    panel(ax, 43.5, yc, 12.5, hc, "12. Document AI", c["docs"], TEAL)
    panel(ax, 57, yc, 13, hc, "13. RAG / search", c["search"], TEAL)
    panel(ax, 71, yc, 14.5, hc, "14. Human-in-loop &\n      LLM governance", c["hitl"], ORANGE)
    panel(ax, 86.5, yc, 13.5, hc, "15. ML & MLOps", c["ml"] + [a["ml_use"]], PURPLE)

    # row D: cross-cutting   (y 6.0 .. 14.0)
    yd, hd = 6.0, 8.0
    panel(ax, 0, yd, 24.5, hd, "16. Observability", c["obs"], GREEN)
    panel(ax, 25.5, yd, 24.5, hd, "17. Audit & compliance", c["audit"], RED)
    panel(ax, 51, yd, 24.5, hd, "18. Resilience / DR", c["dr"], BLUE)
    panel(ax, 76.5, yd, 23.5, hd, "19. Cost, data governance", c["cost"], GREY)

    # main flows
    arrow(ax, 8.5, 41.2, 6.5, 40.4)                      # users -> edge
    arrow(ax, 13, 34, 14, 34)                            # edge -> app
    arrow(ax, 58, 35, 59, 35, PURPLE)                    # app -> llm
    arrow(ax, 72, 33, 73, 33, BLUE)                      # -> data
    arrow(ax, 85.5, 34, 86.5, 34, PINK)                  # -> enterprise (MCP)
    for x in (27, 42.5, 56):
        arrow(ax, x, 21, x + 1, 21, TEAL)                # ingestion chain
    arrow(ax, 63.5, 26.6, 40, 27.6, TEAL, ls="--")       # rag -> orchestrator
    arrow(ax, 78, 26.6, 29, 27.6, ORANGE, ls="--")       # hitl <-> app
    ax.text(0, 4.3, "Agents recommend, humans decide: every ERP/LOS write goes through the human gate and the MCP "
                    "server's allow-list. Deterministic engines own numbers. Every step lands in the WORM audit log.",
            fontsize=9, color=GREY, style="italic")
    name = f"{asg}_deploy_{cloud}.png"
    save(fig, name)
    return name


def poc_deployment() -> str:
    def big(*args, **kw):  # POC cards have room for larger text
        card(*args, size=10, **kw)

    fig, ax = plt.subplots(figsize=(20, 8.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 44)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 41.2), 100, 2.8, boxstyle="round,pad=0.02,rounding_size=0.5", fc=NAVY, ec=NAVY))
    ax.text(50, 42.6, "POC deployment today - one laptop / VM with Docker Compose (local LLM on GPU, no data leaves the machine)",
            fontsize=13, fontweight="bold", color="white", ha="center", va="center")
    # host
    ax.add_patch(FancyBboxPatch((0, 4), 64, 36, boxstyle="round,pad=0.02,rounding_size=0.8", fc="#F1F5F9", ec=NAVY, lw=1.5))
    ax.text(1, 39.2, "Docker host (Docker Desktop + WSL2, or Linux) · NVIDIA GPU", fontsize=11, fontweight="bold",
            color=NAVY, va="top")
    big(ax, 2, 22, 19, 14.5, "a1-loan-lifecycle :8501", ["Streamlit UI + 7 agents", "Human gate, role-bound",
                                                          "Hybrid RAG assistant", "Doc / policy ingestion",
                                                          "Traces + eval harness"], TEAL)
    big(ax, 23, 22, 19, 14.5, "a2-demand-response :8502", ["Streamlit UI + 5 agents", "Demand-sensing model",
                                                             "Role-bound approvals", "Mock SAP / IBP payloads",
                                                             "Traces + eval harness"], TEAL)
    big(ax, 44, 22, 18.5, 14.5, "ollama :11434 (GPU)", ["gemma4:e4b, 100% GPU", "~1.6-6 s per agent call",
                                                         "OpenAI-compatible API", "ollama-pull job on start"], PURPLE)
    big(ax, 2, 5.5, 19, 13.5, "volume: runtime", ["Audit chain, traces", "Uploads, eval report", "Mock SAP outbox"], GREY)
    big(ax, 23, 5.5, 19, 13.5, "image: loanagent-fde", ["python:3.12-slim", "Pinned requirements", "Same image, APP/PORT"],
         GREY)
    big(ax, 44, 5.5, 18.5, 13.5, "volume: ollama", ["Model weights (6.6 GB)", "Pulled once", "Model set by .env"], GREY)
    arrow(ax, 21, 23.4, 44, 23.4, PURPLE)
    arrow(ax, 42, 25.2, 44, 25.2, PURPLE)
    arrow(ax, 11.5, 22, 11.5, 19, GREY)
    arrow(ax, 32.5, 22, 15, 19, GREY)
    arrow(ax, 53, 22, 53, 19, GREY)
    # right side: options + mapping
    panel(ax, 66, 27, 34, 13, "LLM options (.env, no code change)", ["mock - deterministic, offline demos",
          "ollama - local GPU (this setup)", "openai / azure - managed APIs", "auto - Azure → OpenAI → Ollama → mock",
          "Failures fall back safely and are logged"], PURPLE, size=9.6)
    ax.add_patch(FancyBboxPatch((66, 4), 34, 21.5, boxstyle="round,pad=0.02,rounding_size=0.6", fc=ORANGE + "10", ec=ORANGE, lw=1.3))
    ax.text(66.5, 24.9, "POC → production mapping", fontsize=10.5, fontweight="bold", color=ORANGE, va="top")
    rows = [("Streamlit UI", "React + FastAPI on ECS / Container Apps"),
            ("Demo sign-in (roles)", "Entra ID / Cognito OIDC (st.login ready)"),
            ("Python orchestrator", "LangGraph + persisted state"),
            ("Ollama gemma4", "Bedrock / Azure OpenAI (or vLLM GPU)"),
            ("UI upload + pypdf", "S3 / Blob + Textract / Doc Intelligence"),
            ("TF-IDF hybrid RAG", "OpenSearch / Azure AI Search"),
            ("Mock SAP outbox", "MCP server tool calls (allow-listed)"),
            ("traces.jsonl spans", "OTel → Langfuse / X-Ray / App Insights"),
            ("JSONL audit chain", "PostgreSQL + WORM storage"),
            ("evals/run_evals.py", "CI gate on every PR + nightly"),
            (".env secrets", "Secrets Manager / Key Vault")]
    for i, (p, q) in enumerate(rows):
        y = 23.0 - i * 1.72
        ax.text(66.8, y, p, fontsize=8.6, color="#222", va="top")
        ax.text(80, y, "→  " + q, fontsize=8.6, color=NAVY, va="top")
    ax.text(0, 2.4, "Run: docker compose -f docker-compose.yml -f docker-compose.ollama.yml -f docker-compose.ollama.gpu.yml "
                    "up --build -d   (see docs/DOCKER.md)", fontsize=9.5, color=GREY, family="monospace")
    save(fig, "poc_deployment.png")
    return "poc_deployment.png"


if __name__ == "__main__":
    poc_deployment()
    for asg in ("a1", "a2"):
        for cloud in ("aws", "azure"):
            cloud_deployment(cloud, asg)

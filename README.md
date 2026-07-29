# infra-ai-agent

Production-grade **RAG + AI Agent** that turns natural-language infrastructure
requests ("create a production VPC with 3 AZs and NAT gateways") into
validated, human-approved Terraform changes against AWS.

Pipeline: `User → API → Agent (LangGraph) → RAG (Qdrant) → LLM → Terraform
Generate → Validate → Plan → Approval → Apply → SNS/Slack Notify → Audit Log`

This repo is built in phases (Part-1 … Part-15). **This commit implements
Part-1: Project Foundation.**

## Status

| Part | Scope | Status |
|---|---|---|
| 1 | Project foundation (repo, Docker, config, logging, CI) | ✅ done |
| 2 | Terraform doc downloader (2000+ docs) | ✅ done — 2,351 docs verified live |
| 3 | Document processing / chunking | ✅ done — 15,789 chunks verified live |
| 4 | Embedding pipeline | ⬜ next |
| 5 | Vector database (Qdrant) | ⬜ |
| 6 | RAG engine (hybrid search, MMR, reranking) | ⬜ |
| 7 | AI agent (LangGraph, memory, tool calling, approval) | ⬜ |
| 8 | Terraform engine (init/plan/apply/destroy/import) | ⬜ |
| 9 | AWS integration (STS, IAM, boto3) | ⬜ |
| 10 | Notifications (SNS/Slack/email/audit) | ⬜ |
| 11 | REST API (FastAPI, JWT, RBAC) | ⬜ |
| 12 | Docker hardening | ⬜ |
| 13 | Kubernetes (Deployment/Service/Ingress/HPA) | ⬜ |
| 14 | Monitoring (Prometheus/Grafana/Loki/OTel) | ⬜ |
| 15 | CI/CD (build → scan → push → deploy) | ⬜ |

## Architecture decisions locked in for Part-1

- **Vector DB: Qdrant.** Self-hostable in Docker/K8s (no vendor lock-in),
  native hybrid (dense+sparse) search, payload filtering for metadata
  (service=`aws_eks_cluster`, doc_type=`resource`), and an HNSW index that
  scales past the ~50-100k chunk range a Terraform+AWS-provider corpus needs.
  pgvector was the runner-up if you'd rather reuse an existing RDS Postgres.
- **Agent framework: LangGraph.** This workflow is a graph with real cycles
  (generate → validate → fix → re-validate) and a hard human-in-the-loop gate
  before `apply`/`destroy` — LangGraph's explicit state machine + interrupt
  points model that far more reliably than LangChain's linear agent executor
  or CrewAI's role-based orchestration.
- **Embeddings: `BAAI/bge-small-en-v1.5`** (384-dim) — strong retrieval
  quality for technical docs, cheap enough to run on CPU, swappable via
  `EMBEDDING_MODEL` without touching code.
- **LLM: Bedrock-first** (`llm_provider=bedrock`), swappable to
  Anthropic/OpenAI/Ollama via `LLM_PROVIDER` — keeps AWS IAM as the single
  credential boundary rather than juggling separate API keys.
- **Chunking: parent-child, markdown-section-aware, token-bounded.** Each
  doc splits on H1/H2 headers (Resource / Example Usage / Argument
  Reference / ... — the natural structure of every provider doc). A
  section that fits in one chunk (≤450 tokens) is stored once. An
  oversized section is stored twice: once whole as a "parent" (used for
  parent-document retrieval — give the LLM full section context once a
  child chunk scores as relevant) and once split into ~450-token
  "child" chunks with ~60-token overlap (what's actually vector-searched).
  Splitting packs whole paragraphs/fenced-code-blocks greedily — HCL code
  blocks are never split mid-block, even if that means one chunk runs
  over budget.

## Quickstart

```bash
# 1. Install system dependencies (Python, Poetry, Terraform, AWS CLI, Docker, kubectl, Helm)
./scripts/install_dependencies.sh

# 2. Configure environment
cp .env.example .env
# edit .env — set JWT_SECRET at minimum

# 3. Install Python dependencies
poetry install

# 4. Run tests
poetry run pytest

# 5. Run the API locally
poetry run uvicorn api.main:app --reload --port 8000
curl http://localhost:8000/health

# 6. Or run the full local stack (API + Qdrant) in Docker
docker compose -f docker/docker-compose.yml up --build
```

## Repository layout

```
infra-ai-agent/
├── agent/              # LangGraph agent: planning, tool calling, approval gates (Part-7)
├── rag/                # RAG orchestration + ingestion + processing (Parts 2-3, 6)
│   ├── ingestion/       # Terraform/AWS provider doc downloader (Part-2)
│   └── processing/      # cleaning + parent-child chunking (Part-3)
├── retriever/           # Hybrid/dense/sparse retrieval, MMR, reranking (Part-6)
├── embeddings/          # Embedding generation + batching + caching (Part-4)
├── vector-db/           # Qdrant client, collections, index config (Part-5)
├── terraform-engine/    # init/fmt/validate/plan/apply/destroy/import wrapper (Part-8)
├── aws/                 # boto3 + STS + IAM helpers (Part-9)
├── api/                 # FastAPI app, routers, auth (Part-1 + Part-11)
├── configs/             # settings.py, logging_config.py — single source of config
├── scripts/             # install_dependencies.sh and future ops scripts
├── docs/                # architecture diagrams, sequence diagrams
├── tests/               # pytest suite
├── docker/              # Dockerfile, docker-compose.yml
├── kubernetes/          # base/ overlays/ helm/ manifests (Part-13)
├── monitoring/          # prometheus/ grafana/ loki/ configs (Part-14)
├── .github/workflows/   # CI/CD (Part-15)
└── terraform/           # Terraform modules the agent generates into / manages
```

## Security posture (baked in from Part-1, not bolted on later)

- No static AWS keys anywhere — `aws/` will assume roles via STS; local dev
  mounts `~/.aws` read-only into the container.
- `.env` is git-ignored; `.env.example` documents every variable with a safe
  default.
- `REQUIRE_HUMAN_APPROVAL_FOR_APPLY` / `_DESTROY` default to `true` — the
  agent cannot mutate AWS infrastructure without an explicit approval step
  (Part-7/Part-8).
- Container runs as a non-root `agent` user.

## Next step

Part-4: Embedding pipeline — batches `docs/processed/chunks.json` through
a sentence-transformer model, caches embeddings by `content_hash` (so
re-running Part-3 doesn't force a full re-embed), and hands off to Part-5
(Qdrant ingestion).

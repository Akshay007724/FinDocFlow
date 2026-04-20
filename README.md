# FinDocFlow

**Cross-page multimodal financial document reasoning pipeline** — ingest PDFs, HTML filings, XBRL, and Excel workbooks; extract tables, charts, and text with vision models; resolve entities across pages via a Neo4j knowledge graph; generate structured analyst recommendation reports and answer complex financial questions through a THINK→ACT→VERIFY reasoning loop.

---

## Architecture

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │                          FinDocFlow Pipeline                          │
 │                                                                       │
 │  Upload      Stage 1           Stage 2           Stage 3             │
 │  (PDF/HTML/  ┌───────────┐     ┌───────────┐     ┌───────────────┐  │
 │   XBRL/XLS) │ Ingestion │────▶│Extraction │────▶│Entity Linking │  │
 │  ──────────▶│  :8001    │     │  :8002    │     │    :8003      │  │
 │             │           │     │           │     │               │  │
 │             │Kafka prod.│     │EasyOCR    │     │Neo4j graph    │  │
 │             │PDF/HTML/  │     │DETR tables│     │Cross-page     │  │
 │             │XBRL parser│     │CLIP charts│     │entity res.    │  │
 │             │10 workers │     │10 workers │     │               │  │
 │             └─────┬─────┘     └─────┬─────┘     └───────┬───────┘  │
 │                   │                 │                    │           │
 │            raw_documents    extracted_documents   linked_documents   │
 │                   │                 │                    │           │
 │                   └─────────────────┴────────────────────┘           │
 │                                     │                                │
 │                               Stage 4             Frontend           │
 │                          ┌──────────────┐    ┌────────────────┐     │
 │                          │  Reasoning   │    │   Streamlit    │     │
 │                          │   :8004      │◀───│    :8501       │◀─── │
 │                          │              │    │                │  User│
 │                          │ LLaVA (vis.) │    │ Documents      │     │
 │                          │ THINK→ACT→  │    │ Report Generator│     │
 │                          │  VERIFY loop │    │ Chat Interface │     │
 │                          │ Report gen.  │    │ Benchmark      │     │
 │                          └──────────────┘    └────────────────┘     │
 │                                                                       │
 │  Infrastructure: Kafka · Redis · Neo4j · MinIO (Iceberg) · Ollama    │
 └──────────────────────────────────────────────────────────────────────┘
```

---

## Key Features

- **Multi-format ingestion** — PDF, HTML (SEC EDGAR), XBRL, and Excel parsers backed by a Kafka producer with 10-worker thread pool for durable, replay-able document queues. Supports multi-document batch ingestion.
- **Multimodal extraction** — EasyOCR (arm64-native) for scanned text, DETR for table structure detection, CLIP for chart classification; pages processed in parallel with 10 workers.
- **Vision-language reasoning** — LLaVA multimodal model (via Ollama) reads page images directly alongside extracted text, enabling chart value extraction, complex table parsing, and visual layout understanding.
- **Cross-page entity resolution** — Neo4j knowledge graph links companies, figures, and time periods mentioned across disparate pages of the same filing.
- **Analyst report generation** — One-click structured recommendation reports with 9 standard equity research sections: Investment Summary, Business Description, Industry Analysis, Financial Analysis, Key Risks, ESG Analysis, Management Quality, Growth Catalysts, and Valuation Indicators. Sections generated in parallel using 4 workers. Downloadable as Markdown.
- **Section-focused chat** — Chat interface grounded in ingested documents with configurable analyst focus (ESG, Key Risks, Financial Analysis, etc.) loaded from an editable `prompts.json` template file.
- **Investment management UI** — Dark OLED theme (IBM Plex Sans, `#020617` background) designed for professional analyst workflows: document library, report generator, and chat in a single interface.
- **Kubernetes-native** — All services ship with Deployments, Services, and HPAs; a Helm chart covers the full stack with a single `helm install`.

---

## Prerequisites

| Tool | Minimum version | Purpose |
|------|----------------|---------|
| Docker + Docker Compose | 24.x / 2.x | Local development |
| kubectl | 1.28+ | Kubernetes CLI |
| helm | 3.13+ | Chart deployment |
| make | any | Convenience targets |

> **Apple Silicon (M1/M2/M3/M4/M5):** All services run natively on `linux/arm64`. EasyOCR replaces PaddleOCR for arm64 compatibility.

---

## Frontend

FinDocFlow ships **two frontends**. The Next.js app is the preferred experience going forward; the Streamlit UI is retained for now as a legacy fallback.

### Next.js SPA (preferred) — `http://localhost:3000`

Production-grade interactive UI on Next.js 14 + Tailwind + shadcn-style primitives + TanStack Query. Dark OLED design system from `design-system/findocflow/MASTER.md`. Features:

- **Streaming reasoning** — Server-Sent Events render THINK → ACT → VERIFY phases live as they arrive from the reasoning service.
- **Streaming reports** — Each of the 9 analyst sections streams in its own card with a per-section progress badge; up to 4 sections run concurrently.
- **Live ingest progress** — Uploads push per-file progress via WebSocket (`/ingest/ws/{job_id}`) with a retry-friendly toast on failure.
- **Command palette** — `⌘K` / `Ctrl+K` fuzzy navigation and quick actions.
- **Vim-style nav** — `g d` Dashboard · `g l` Library · `g r` Reports · `g c` Chat · `g g` Graph · `g p` Pipeline.
- **Service health HUD** — Top bar indicator polls every 15s; full breakdown on hover.

Local dev:

```bash
cd services/frontend-next
npm install
npm run dev               # http://localhost:3000
npm run test              # Vitest (28 unit tests)
npm run typecheck         # tsc --noEmit
npm run build             # next build
```

Docker:

```bash
docker compose up -d frontend-next
```

### Streamlit (legacy) — `http://localhost:8501`

Kept for backward compatibility. Prefer the Next.js app for new work.

---

## Quick Start (Docker Compose)

```bash
# Clone the repo
git clone https://github.com/yourorg/findocflow.git
cd findocflow

# Start all services (builds images on first run)
make up

# Pull the LLaVA vision-language model (~4.7 GB)
make pull-model

# Tail logs from all services
make logs
```

Open [http://localhost:8501](http://localhost:8501) to access the dashboard.

```bash
# Stop and remove all containers and volumes
make down
```

---

## Using the Interface

### Document Library
Upload multiple PDFs, HTML filings, XBRL, or Excel files at once. Batch ingest from SEC EDGAR URLs. All ingested documents are listed with their status and cached for querying.

### Report Generator
1. Select one or more ingested documents
2. Choose which report sections to include (all 9 enabled by default)
3. Click **Generate Report** — LLaVA analyzes pages multimodally
4. Each section renders as an expandable card; download the full report as Markdown

### Chat
1. Select documents from the left panel
2. Optionally choose an **Analysis Focus** (e.g., ESG Analysis, Key Risks) to inject expert analyst context
3. Type questions freely — the model grounds all answers in document evidence with page citations

### Customizing Prompts
Section prompts are defined in `services/reasoning_service/prompts.json`. Edit this file to adjust analyst frameworks without rebuilding:

```json
{
  "sections": [
    {
      "id": "key_risks",
      "label": "Key Risks",
      "icon": "⚠️",
      "prompt": "Your custom analyst prompt here..."
    }
  ]
}
```

---

## API Reference

### Ingestion Service — `http://localhost:8001`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ingest/upload` | Upload a document (PDF, HTML, XBRL, Excel); returns `job_id` and `doc_ids` |
| `POST` | `/ingest/batch` | Batch ingest from a list of URLs |
| `GET`  | `/ingest/status/{job_id}` | Poll ingestion job status |
| `GET`  | `/ingest/docs` | List all ingested documents (last 50) |
| `GET`  | `/ingest/pages/{doc_id}` | Retrieve cached page content for a document |
| `GET`  | `/health` | Liveness probe |

### Extraction Service — `http://localhost:8002`

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Liveness probe |
| `GET`  | `/models` | List loaded OCR/table/chart models |

### Entity Linking Service — `http://localhost:8003`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/graph/company-metrics` | Query Neo4j for company financial metrics |
| `POST` | `/embed/similar-pages` | Semantic similarity search over page embeddings |
| `GET`  | `/health` | Liveness probe |

### Reasoning Service — `http://localhost:8004`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/reason` | THINK→ACT→VERIFY Q&A with page citations |
| `POST` | `/report` | Generate multi-section analyst report from pages |
| `POST` | `/chat` | Conversational Q&A with history and section focus |
| `POST` | `/summarize` | Executive summary of provided pages |
| `GET`  | `/prompts` | Retrieve all analyst section prompt templates |
| `GET`  | `/health` | Liveness probe (includes Ollama/model status) |

---

## Kubernetes Deployment (raw manifests)

```bash
make k8s-deploy    # Apply namespace, config, secrets, and all service manifests
make k8s-status    # Check pod and service status
make k8s-delete    # Tear down the entire namespace
```

---

## Helm Deployment

```bash
# Install with default values
helm install findocflow ./helm/findocflow \
  --namespace findocflow \
  --create-namespace

# Override model and secrets
helm install findocflow ./helm/findocflow \
  --namespace findocflow \
  --create-namespace \
  --set neo4j.password=mysecret \
  --set minio.accessKey=mykey \
  --set minio.secretKey=mysecretkey \
  --set ollama.model=llava

# Upgrade a running release
helm upgrade findocflow ./helm/findocflow \
  --namespace findocflow \
  --set ingestion.replicaCount=3

# Enable ingress
helm upgrade findocflow ./helm/findocflow \
  --namespace findocflow \
  --set ingress.enabled=true \
  --set ingress.host=findocflow.example.com

# Uninstall
helm uninstall findocflow --namespace findocflow
```

Key values (see `helm/findocflow/values.yaml` for the full reference):

| Value | Default | Description |
|-------|---------|-------------|
| `ingestion.replicaCount` | `2` | Ingestion pod count (HPA min) |
| `extraction.replicaCount` | `1` | Extraction pod count |
| `ollama.model` | `llava` | Vision-language model pulled by Ollama |
| `ingress.enabled` | `false` | Enable Nginx Ingress for the frontend |
| `ingress.host` | `findocflow.example.com` | Ingress hostname |
| `logLevel` | `INFO` | Log level for all services |

---

## Dataset & Experiments

```bash
make collect-dataset   # Collect the FinDocBench evaluation dataset
make evaluate          # Run full model evaluation
make ablation          # Run ablation study (disable individual pipeline stages)
```

Results and logs are written to `experiments/results/`.

---

## Benchmark Results

Performance on **FinDocBench** (127 SEC 10-K filings, 412 expert-annotated multi-page QA pairs).

| System | Accuracy | EGS | MRR |
|--------|----------|-----|-----|
| GPT-4o (text-only) | 58.1% | 0.51 | 0.47 |
| Llama 3.2 (text-only) | 49.3% | 0.44 | 0.41 |
| FinDocFlow w/o entity linking | 63.7% | 0.59 | 0.55 |
| FinDocFlow w/o multimodal extraction | 61.2% | 0.56 | 0.52 |
| **FinDocFlow (full, LLaVA)** | **71.3%** | **0.68** | **0.64** |

- **Accuracy** — exact-match answer correctness
- **EGS** — Evidence Grounding Score (fraction of answer tokens traceable to a source span)
- **MRR** — Mean Reciprocal Rank of the correct evidence page

---

## Project Structure

```
findocflow/
├── dataset/
│   └── collector.py                  # FinDocBench dataset collector
├── docker-compose.yml                # Local development stack
├── experiments/
│   ├── ablation.py                   # Stage-ablation experiments
│   └── evaluate.py                   # End-to-end evaluation harness
├── helm/findocflow/                  # Helm chart (full stack)
├── k8s/                              # Raw Kubernetes manifests
├── Makefile                          # Build / deploy / experiment targets
├── monitoring/                       # Prometheus / Grafana configs
├── paper/                            # Research paper source
├── pipeline/                         # Shared pipeline utilities
└── services/
    ├── ingestion_service/            # FastAPI — Kafka producer + parsers (10 workers)
    ├── extraction_service/           # FastAPI — EasyOCR + DETR + CLIP (10 workers)
    ├── entity_linking_service/       # FastAPI — Neo4j graph builder
    ├── reasoning_service/
    │   ├── main.py                   # FastAPI — /reason /report /chat /prompts
    │   ├── think_act_verify.py       # THINK→ACT→VERIFY loop (LLaVA multimodal)
    │   ├── report_generator.py       # 9-section analyst report generator (4 workers)
    │   ├── ollama_client.py          # Ollama HTTP client (text + vision)
    │   └── prompts.json              # Editable analyst section prompt templates
    └── frontend/                     # Streamlit — dark investment management UI
```

---

## Contributing

1. Fork the repository and create a feature branch (`git checkout -b feat/my-feature`).
2. Make your changes and ensure `make lint` and `make test` pass.
3. Open a pull request against `main` with a clear description of the change.

Please follow the existing code style (ruff-formatted Python, conventional commits).

---

## License

MIT License. See [LICENSE](LICENSE) for details.

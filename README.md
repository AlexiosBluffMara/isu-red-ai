# ISU ReD AI — Intelligent Research Discovery Platform

> AI-powered semantic search over Illinois State University's entire Research and eData (ReD) repository — 20,224 scholarly works spanning 169 years (1857–2026), across 12,369 subjects.

[![CI](https://github.com/AlexiosBluffMara/isu-red-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/AlexiosBluffMara/isu-red-ai/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Gemini API](https://img.shields.io/badge/Gemini-2.5_Flash-4285F4.svg)](https://ai.google.dev/)

---

## What This Is

ISU ReD AI transforms Illinois State University's static PDF archive into a **semantically searchable, AI-queryable knowledge base**. Researchers can ask natural language questions and receive precise, cited answers across the full breadth of ISU scholarship.

**Example queries:**
- "What work has ISU done on machine learning in agriculture?"
- "Show me cybersecurity research published in the last 5 years"
- "Find research connecting education and technology at ISU"

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   ISU ReD AI Platform                     │
├──────────────┬──────────────┬──────────────┬─────────────┤
│  Collection  │  Extraction  │  Embedding   │   Search    │
│              │              │              │             │
│  ISU ReD     │  Gemini 2.5  │  Gemini      │  LanceDB    │
│  Repository  │  Flash/Pro   │  Embedding 2 │  Vector     │
│  (Digital    │  + PyMuPDF   │  (3072-dim)  │  Store      │
│  Commons)    │  fallback    │              │             │
│              │              │              │  + Gemini   │
│  20,224 docs │  13,613 done │  193,653     │  2.5 Flash  │
│  40 GB       │  257 MB text │  chunks      │  RAG        │
└──────────────┴──────────────┴──────────────┴─────────────┘
                                              │
                          ┌───────────────────┘
                          ▼
                ┌──────────────────┐
                │   FastAPI Web    │
                │  (4-tab UI)      │
                ├──────────────────┤
                │  Search + RAG    │
                │  Dashboard       │
                │  Browse/Filter   │
                │  Subject Cards   │
                └──────────────────┘
```

## Pipeline Statistics

| Component | Status | Detail |
|-----------|--------|--------|
| PDF Collection | ✅ Complete | 16,356 PDFs, 40 GB |
| Metadata Database | ✅ Complete | 20,224 papers cataloged |
| Text Extraction | ✅ Complete | 13,613 papers extracted (257 MB text) |
| Semantic Chunking | ✅ Complete | 193,653 chunks (1,500 chars, 300 overlap) |
| Vector Embeddings | ✅ Complete | 193,653 chunks embedded (3072-dim) |
| LanceDB Vector Store | ✅ Operational | 2.5 GB queryable vector database |
| Subject Coverage | ✅ Indexed | 12,369 unique subject tags |
| Temporal Range | ✅ Indexed | 1857–2026 |
| Web UI | ✅ Live | 4-tab student-facing research discovery |
| CI/CD | ✅ Active | GitHub Actions + Cloud Run deployment |
| Test Suite | ✅ 38 tests | Papers data + API endpoint tests |

## Cost

| Line Item | Cost |
|-----------|------|
| Gemini API (extraction + embedding) | ~$604 |
| Infrastructure (Mac Mini M-series) | ~$700 |
| Software licensing | $0 |
| **Total** | **~$1,300** |
| **Cost per paper** | **$0.044** |
| **Commercial equivalent** | **$36,000–$150,000+** |

> **60×–250× cost advantage** over commercial buildout.

## Quick Start

### Prerequisites
- Python 3.11+
- Gemini API key ([get one free](https://aistudio.google.com/apikey))
- 3+ GB disk space for vector database

### Setup

```bash
git clone https://github.com/AlexiosBluffMara/isu-red-ai.git
cd isu-red-ai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your GEMINI_API_KEY
```

### Run the Demo

```bash
# Start the web interface (with hot-reload)
make serve

# Or run directly
python web/app.py

# Query from CLI
python search/cli.py "What has ISU published about digital twins?"
```

### Run Tests

```bash
make test
# Or directly:
PAPERS_DB=tests/fixtures/sample_papers.json pytest tests/ -v
```

### Run the Full Pipeline (if rebuilding from scratch)

```bash
# Sync data from scraper output
make sync

# Or run individual stages:
make extract    # PDF → text (Gemini Flash/Pro + PyMuPDF)
make embed      # text → LanceDB vectors
make process    # summaries + KMeans clustering

# Or all at once:
make pipeline
```

### Deploy

```bash
# Docker (local)
make docker-build && make docker-run

# Cloud Run (interactive)
make deploy

# Or via GitHub Actions (recommended)
# Push to main → CI runs → manual deploy trigger
```

## Project Structure

```
isu-red-ai/
├── .github/workflows/
│   ├── ci.yml                # Lint + test + Docker build on push/PR
│   └── deploy.yml            # Manual Cloud Run deploy via Workload Identity
│
├── pipeline/                 # Data processing pipeline
│   ├── config.py             # Centralized configuration
│   ├── extract.py            # Gemini-powered PDF text extraction
│   ├── embed.py              # Vector embedding + LanceDB storage
│   └── process.py            # AI summaries + KMeans clustering
│
├── search/                   # Search & retrieval
│   ├── engine.py             # RAG query engine (LanceDB + Gemini 2.5 Flash)
│   └── cli.py                # Command-line search interface
│
├── web/                      # FastAPI web application
│   ├── app.py                # API server (10 endpoints + health/readiness)
│   ├── papers_data.py        # Papers data aggregation module
│   ├── static/css/           # ISU brand stylesheet
│   └── templates/
│       └── index.html        # 4-tab student-facing UI
│
├── tests/                    # Test suite (38 tests)
│   ├── conftest.py           # Shared fixtures + env setup
│   ├── test_papers_data.py   # Data module unit tests
│   ├── test_api.py           # API endpoint integration tests
│   └── fixtures/
│       └── sample_papers.json
│
├── scripts/                  # Deployment & utility scripts
│   ├── deploy_cloud_run.sh   # Cloud Run deployment
│   ├── quickstart.sh         # Zero-to-hero setup
│   ├── sync_to_gcs.py        # GCS data upload
│   └── setup_vertex_search.py
│
├── docs/                     # Documentation
│   ├── COST_ANALYSIS.md      # Detailed cost breakdown
│   └── index.html            # GitHub Pages landing page
│
├── data/                     # Data assets (symlinked / volume-mounted)
│   ├── metadata/             # Paper catalog + index
│   ├── lancedb/              # 2.5 GB vector database
│   ├── pdfs/                 # 40 GB PDFs (external)
│   └── extracted/            # 257 MB extracted text (external)
│
├── Dockerfile                # Multi-stage, non-root, health-checked
├── docker-compose.yml        # Local Docker deployment
├── Makefile                  # CLI for pipeline, dev, deploy
├── requirements.txt          # Python dependencies
└── .env.example              # Environment variable template
```

## Data Assets

The full dataset (40+ GB) is stored externally and linked via symlinks in development or volume mounts in Docker. This repo contains:
- **Test fixtures** (`tests/fixtures/`) — 8-paper sample for CI testing
- **Pipeline code** — Everything needed to rebuild from scratch
- **Metadata index** (`data/metadata/`) — Paper catalog with subject index

### External Data Manifest

| Asset | Size | Records |
|-------|------|---------|
| Raw PDFs | 40 GB | 16,356 files |
| Papers Database | 22 MB | 20,224 entries |
| Extracted text | 257 MB | 13,613 files |
| LanceDB vectors | 2.5 GB | 193,653 chunks |

## Team

| Person | Role | Affiliation |
|--------|------|-------------|
| **Soumit "Om" Lahiri** | Principal Architect | Alexios Bluff Mara LLC |
| **Dr. Mangolika Bhattacharya** | Faculty Sponsor | Asst. Prof., School of IT, ISU |
| **Dr. Rudra Prasad Baksi** | Security Advisor | Asst. Prof., Cybersecurity, ISU |
| **Dr. Somnath Lahiri** | Strategic Advisor | Interim Dept Chair, Management, ISU |

## License

MIT License — See [LICENSE](LICENSE).

ISU ReD content remains the property of its respective authors and Illinois State University. This platform indexes and enables discovery of existing open-access works.

---

*Built by [Alexios Bluff Mara LLC](https://github.com/AlexiosBluffMara) — March 2026*

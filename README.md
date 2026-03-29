# ISU ReD AI — Intelligent Research Discovery Platform

> AI-powered semantic search over Illinois State University's entire Research and eData (ReD) repository — 16,355 scholarly works spanning 169 years (1857–2026), across 12,369 subjects.

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
│              │              │              │  + Vertex   │
│  16,355 PDFs │  13,610 done │  193,653     │  AI Search  │
│  40 GB       │  257 MB text │  chunks      │  (GCP)      │
└──────────────┴──────────────┴──────────────┴─────────────┘
```

## Pipeline Statistics

| Component | Status | Detail |
|-----------|--------|--------|
| PDF Collection | ✅ Complete | 16,355 PDFs, 40 GB |
| Text Extraction | ✅ Complete | 13,610 papers extracted (257 MB text) |
| Metadata Database | ✅ Complete | 20,224 papers cataloged |
| Semantic Chunking | ✅ Complete | 193,653 chunks (1,500 chars, 300 overlap) |
| Vector Embeddings | ✅ Complete | 193,653/193,653 chunks embedded (3072-dim) |
| LanceDB Vector Store | ✅ Operational | 2.5 GB queryable vector database |
| Subject Coverage | ✅ Indexed | 12,369 unique subject tags |
| Temporal Range | ✅ Indexed | 1857–2026 |

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
# Start the web interface
python web/app.py

# Or query from CLI
python search/cli.py "What has ISU published about digital twins?"
```

### Run the Full Pipeline (if rebuilding from scratch)

```bash
# Phase 1: Download PDFs from ISU ReD
python pipeline/download.py

# Phase 2: Extract text using Gemini
python pipeline/extract.py

# Phase 3: Chunk and embed into LanceDB
python pipeline/embed.py

# Phase 4: Generate index report
python pipeline/index.py
```

## Project Structure

```
isu-red-ai/
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variable template
│
├── docs/
│   ├── PITCH.md              # Full stakeholder proposal
│   ├── ARCHITECTURE.md       # Technical deep dive
│   ├── COST_ANALYSIS.md      # Detailed cost breakdown + thinking token analysis
│   ├── LEGAL_ANALYSIS.md     # Fair use and ToS analysis
│   ├── GENAI_CREDIT.md       # $1000 GenAI App Builder strategy
│   └── forensics/
│       └── PROJECT_HISTORY.md
│
├── pipeline/                 # Data processing pipeline
│   ├── download.py           # PDF collection from ISU ReD
│   ├── extract.py            # Gemini-powered text extraction
│   ├── embed.py              # Vector embedding + LanceDB storage
│   ├── index.py              # Content index generation
│   └── config.py             # Centralized configuration
│
├── search/                   # Search & retrieval
│   ├── engine.py             # RAG query engine (LanceDB)
│   ├── cli.py                # Command-line search interface
│   └── vertex_ai.py          # Vertex AI Search integration
│
├── web/                      # Web demo
│   ├── app.py                # FastAPI application
│   ├── static/css/
│   │   └── isu-brand.css     # ISU brand guidelines
│   └── templates/
│       └── index.html        # Demo UI
│
├── gcloud/                   # Google Cloud deployment
│   ├── setup_vertex_search.py
│   └── import_data.py
│
├── data/                     # Data assets (large files not in git)
│   ├── metadata/
│   │   ├── papers_database.json
│   │   └── isu_red_index.json
│   └── sample/               # Small sample for testing
│
└── scripts/
    └── cost_analysis.py
```

## Data Assets

The full dataset (40+ GB) is stored externally. This repo contains:
- **Metadata** (`data/metadata/`) — Full paper catalog and subject index
- **Sample data** (`data/sample/`) — Representative subset for testing
- **Pipeline code** — Everything needed to rebuild from scratch

### External Data Manifest

| Asset | Size | Location |
|-------|------|----------|
| Raw PDFs | 40 GB (16,355 files) | `data/pdfs/` (external) |
| Extracted text | 257 MB (13,610 files) | `data/extracted/` (external) |
| LanceDB vectors | 2.5 GB (193,653 chunks) | `data/lancedb/` (external) |
| Chunks JSON | ~500 MB | `data/chunks.json` (external) |

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

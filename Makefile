.PHONY: help install extract embed process search serve serve-prod \
       sync sync-gcs pipeline docker-build docker-run docker-stop \
       gcloud-setup vertex-setup deploy deploy-dry deploy-cloud-build \
       quickstart status test clean

VENV      := .venv
PYTHON    := $(VENV)/bin/python
PIP       := $(VENV)/bin/pip
UVICORN   := $(VENV)/bin/uvicorn
PORT      := 8080
WORKERS   := 4
CLUSTERS  := 25
PDFS_DIR  ?= data/pdfs
DATA_SRC  ?= $(HOME)/.openclaw/workspace/isu-genai-platform/scrapers/output/research

# Default target
.DEFAULT_GOAL := help

# ── Help ──────────────────────────────────────────────────────────────

help: ## Show this help
	@echo ""
	@echo "  ╦╔═╗╦ ╦  ╦═╗┌─┐╔╦╗  ╔═╗╦"
	@echo "  ║╚═╗║ ║  ╠╦╝├┤  ║║  ╠═╣║"
	@echo "  ╩╚═╝╚═╝  ╩╚═└─┘═╩╝  ╩ ╩╩"
	@echo "  Research Discovery AI — CLI"
	@echo ""
	@echo "  QUICKSTART"
	@echo "    make quickstart       — Full setup from zero (venv + deps + data sync + serve)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "    \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Environment ───────────────────────────────────────────────────────

install: $(VENV)/bin/activate ## Create venv + install Python dependencies
	$(PIP) install -r requirements.txt --quiet

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip --quiet

# ── Pipeline stages ───────────────────────────────────────────────────

extract: install ## Extract text from PDFs (Gemini Flash → Pro → PyMuPDF)
	$(PYTHON) -m pipeline.extract --source $(PDFS_DIR) --workers $(WORKERS)

embed: install ## Chunk text + generate embeddings → LanceDB
	$(PYTHON) -m pipeline.embed --source data/extracted --workers $(WORKERS)

process: install ## Summarize papers + KMeans clustering
	$(PYTHON) -m pipeline.process --clusters $(CLUSTERS) --workers $(WORKERS)

pipeline: extract embed process ## Run full pipeline: extract → embed → process

# ── Data sync ─────────────────────────────────────────────────────────

sync: ## Sync data from OpenClaw scraper output → data/
	@echo "Syncing from $(DATA_SRC)..."
	@mkdir -p data/extracted data/pdfs data/lancedb data/metadata
	rsync -a --info=progress2 $(DATA_SRC)/extracted/ data/extracted/
	@if [ -d "$(DATA_SRC)/pdfs" ]; then rsync -a --info=progress2 $(DATA_SRC)/pdfs/ data/pdfs/; fi
	@if [ -d "$(DATA_SRC)/isu_red_lancedb" ]; then rsync -a $(DATA_SRC)/isu_red_lancedb/ data/lancedb/; fi
	@echo "Sync complete."

sync-gcs: install ## Upload data to Google Cloud Storage
	$(PYTHON) scripts/sync_to_gcs.py

# ── Search & serve ────────────────────────────────────────────────────

search: install ## Search papers (use ARGS="query --rag")
	$(PYTHON) -m search.cli $(ARGS)

serve: install ## Start dev server with hot reload (port 8080)
	$(UVICORN) web.app:app --host 0.0.0.0 --port $(PORT) --reload

serve-prod: install ## Start production server (4 workers)
	$(UVICORN) web.app:app --host 0.0.0.0 --port $(PORT) --workers 4

# ── Docker ────────────────────────────────────────────────────────────

docker-build: ## Build Docker image locally
	docker build -t isu-red-ai .

docker-run: ## Start with docker compose (background)
	docker compose up -d

docker-stop: ## Stop docker compose
	docker compose down

# ── Google Cloud ──────────────────────────────────────────────────────

gcloud-setup: ## Install gcloud CLI + enable APIs + create GCS bucket
	chmod +x scripts/install_gcloud.sh
	bash scripts/install_gcloud.sh

vertex-setup: install ## Create Vertex AI Search data store + engine
	$(PYTHON) scripts/setup_vertex_search.py setup

vertex-search: install ## Test Vertex AI Search (use ARGS="query")
	$(PYTHON) scripts/setup_vertex_search.py search $(ARGS)

vertex-status: install ## Check Vertex AI Search provisioning status
	$(PYTHON) scripts/setup_vertex_search.py status

vertex-cost: install ## Show Vertex AI cost estimates
	$(PYTHON) scripts/setup_vertex_search.py cost

# ── Deployment ────────────────────────────────────────────────────────

deploy: ## Deploy to Cloud Run (interactive)
	chmod +x scripts/deploy_cloud_run.sh
	bash scripts/deploy_cloud_run.sh

deploy-dry: ## Preview Cloud Run deploy commands (no changes)
	chmod +x scripts/deploy_cloud_run.sh
	bash scripts/deploy_cloud_run.sh --dry-run

deploy-cloud-build: ## Deploy using Cloud Build (no local Docker needed)
	chmod +x scripts/deploy_cloud_run.sh
	bash scripts/deploy_cloud_run.sh --cloud-build

# ── Full workflows ────────────────────────────────────────────────────

quickstart: ## Zero-to-hero: venv + deps + data sync + dev server
	chmod +x scripts/quickstart.sh
	bash scripts/quickstart.sh

full-cloud: gcloud-setup sync-gcs vertex-setup deploy ## Full cloud setup (GCP + GCS + Vertex + Cloud Run)

# ── Status & info ─────────────────────────────────────────────────────

status: ## Show data counts and system status
	@echo ""
	@echo "  Data Status"
	@echo "  ─────────────────────────────────────"
	@printf "  PDFs:         %s\n" "$$(find data/pdfs -name '*.pdf' 2>/dev/null | wc -l | tr -d ' ')"
	@printf "  Extracted:    %s\n" "$$(find data/extracted -name '*.txt' 2>/dev/null | wc -l | tr -d ' ')"
	@printf "  LanceDB:     %s\n" "$$(du -sh data/lancedb 2>/dev/null | cut -f1 || echo 'empty')"
	@printf "  Chunks:      %s\n" "$$(wc -c < data/chunks.json 2>/dev/null | tr -d ' ' || echo 'none')"
	@echo ""
	@echo "  Environment"
	@echo "  ─────────────────────────────────────"
	@printf "  Python:      %s\n" "$$(python3 --version 2>&1)"
	@printf "  Venv:        %s\n" "$$([ -d .venv ] && echo 'yes' || echo 'no')"
	@printf "  .env:        %s\n" "$$([ -f .env ] && echo 'yes' || echo 'missing')"
	@printf "  Gemini key:  %s\n" "$$(grep -qE '^GEMINI_API_KEY=.+' .env 2>/dev/null && echo 'set' || echo 'not set')"
	@printf "  gcloud:      %s\n" "$$(command -v gcloud >/dev/null 2>&1 && gcloud --version 2>/dev/null | head -1 || echo 'not installed')"
	@printf "  Docker:      %s\n" "$$(command -v docker >/dev/null 2>&1 && docker --version 2>/dev/null | head -1 || echo 'not installed')"
	@echo ""

# ── Cleanup ───────────────────────────────────────────────────────────

test: install ## Run tests
	PAPERS_DB=tests/fixtures/sample_papers.json GEMINI_API_KEY=test-key \
		$(PYTHON) -m pytest tests/ -v --tb=short

clean: ## Remove venv and Python caches
	rm -rf $(VENV) __pycache__ pipeline/__pycache__ search/__pycache__ web/__pycache__
	rm -rf .pytest_cache .mypy_cache
	find . -name "*.pyc" -delete

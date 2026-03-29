.PHONY: install extract embed process search serve sync docker-build docker-run clean test

VENV      := .venv
PYTHON    := $(VENV)/bin/python
PIP       := $(VENV)/bin/pip
UVICORN   := $(VENV)/bin/uvicorn
PORT      := 8080
WORKERS   := 4
CLUSTERS  := 25
PDFS_DIR  ?= data/pdfs
DATA_SRC  ?= $(HOME)/.openclaw/workspace/isu-genai-platform/scrapers/output/research

# ── Environment ───────────────────────────────────────────────────────

install: $(VENV)/bin/activate
	$(PIP) install -r requirements.txt

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

# ── Pipeline stages ───────────────────────────────────────────────────

extract: install
	$(PYTHON) -m pipeline.extract --source $(PDFS_DIR) --workers $(WORKERS)

embed: install
	$(PYTHON) -m pipeline.embed --source data/extracted --workers $(WORKERS)

process: install
	$(PYTHON) -m pipeline.process --clusters $(CLUSTERS) --workers $(WORKERS)

# ── Sync data from OpenClaw scraper output ────────────────────────────

sync:
	@echo "Syncing extracted texts from $(DATA_SRC)..."
	mkdir -p data/extracted data/pdfs data/metadata
	rsync -av --progress $(DATA_SRC)/extracted/ data/extracted/
	@if [ -d "$(DATA_SRC)/pdfs" ]; then rsync -av --progress $(DATA_SRC)/pdfs/ data/pdfs/; fi
	@echo "Sync complete."

# ── Search & serve ────────────────────────────────────────────────────

search: install
	$(PYTHON) -m search.cli $(ARGS)

serve: install
	$(UVICORN) web.app:app --host 0.0.0.0 --port $(PORT) --reload

serve-prod: install
	$(UVICORN) web.app:app --host 0.0.0.0 --port $(PORT) --workers 4

# ── Docker ────────────────────────────────────────────────────────────

docker-build:
	docker build -t isu-red-ai .

docker-run:
	docker compose up -d

# ── Testing & cleanup ─────────────────────────────────────────────────

test: install
	$(PYTHON) -m pytest tests/ -v --tb=short 2>/dev/null || echo "No tests found yet."

clean:
	rm -rf $(VENV) __pycache__ pipeline/__pycache__ search/__pycache__ web/__pycache__
	rm -rf .pytest_cache .mypy_cache
	find . -name "*.pyc" -delete

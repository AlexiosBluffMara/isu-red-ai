#!/usr/bin/env bash
#
# quickstart.sh — Zero-to-running ISU ReD AI setup.
#
# Does everything: venv, deps, data sync, and starts the dev server.
# Run from the repo root.
#
# Usage:
#   ./scripts/quickstart.sh              # Full local setup + dev server
#   ./scripts/quickstart.sh --no-serve   # Setup only, don't start server
#   ./scripts/quickstart.sh --cloud      # Setup + GCP (gcloud, GCS sync, Cloud Run)
#

set -euo pipefail
cd "$(dirname "$0")/.."

NO_SERVE=false
CLOUD=false

for arg in "$@"; do
    case "$arg" in
        --no-serve) NO_SERVE=true ;;
        --cloud)    CLOUD=true ;;
        -h|--help)
            echo "Usage: $0 [--no-serve] [--cloud]"
            echo "  --no-serve   Setup only, don't start the dev server"
            echo "  --cloud      Also set up Google Cloud (gcloud, GCS, Cloud Run)"
            exit 0 ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

info()  { printf '\033[1;34m▸\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m!\033[0m %s\n' "$*"; }

echo
echo "  ╦╔═╗╦ ╦  ╦═╗┌─┐╔╦╗  ╔═╗╦"
echo "  ║╚═╗║ ║  ╠╦╝├┤  ║║  ╠═╣║"
echo "  ╩╚═╝╚═╝  ╩╚═└─┘═╩╝  ╩ ╩╩"
echo "  Research Discovery AI — Quickstart"
echo

# ──────────────────────────────────────────────────────────────────────
# 1. Check Python
# ──────────────────────────────────────────────────────────────────────
info "Checking Python..."
if ! command -v python3 &>/dev/null; then
    echo "  Python 3 is required. Install from python.org or:"
    echo "    brew install python@3.11"
    exit 1
fi
PY_VER=$(python3 --version 2>&1)
ok "Found $PY_VER"

# ──────────────────────────────────────────────────────────────────────
# 2. Create virtualenv + install deps
# ──────────────────────────────────────────────────────────────────────
info "Setting up virtualenv..."
if [[ ! -d .venv ]]; then
    python3 -m venv .venv
    ok "Created .venv"
else
    ok ".venv already exists"
fi

source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
ok "Dependencies installed"

# ──────────────────────────────────────────────────────────────────────
# 3. Environment variables
# ──────────────────────────────────────────────────────────────────────
info "Checking environment..."
if [[ ! -f .env ]]; then
    if [[ -f .env.example ]]; then
        cp .env.example .env
        warn "Created .env from .env.example — edit it to add your GEMINI_API_KEY"
    else
        cat > .env <<'ENVEOF'
# GEMINI_API_KEY=your-gemini-api-key-here
# GOOGLE_CLOUD_PROJECT=your-gcp-project-id
# VERTEX_AI_LOCATION=us-central1
ENVEOF
        warn "Created .env — edit it to add your GEMINI_API_KEY"
    fi
else
    ok ".env exists"
fi

# Check if GEMINI_API_KEY is set
if grep -qE '^GEMINI_API_KEY=.+' .env 2>/dev/null; then
    ok "GEMINI_API_KEY is configured"
else
    warn "GEMINI_API_KEY not set in .env — AI features won't work until you add it"
    echo "  Get a key at: https://aistudio.google.com/apikey"
fi

# ──────────────────────────────────────────────────────────────────────
# 4. Data sync
# ──────────────────────────────────────────────────────────────────────
SCRAPER_DIR="$HOME/.openclaw/workspace/isu-genai-platform/scrapers/output/research"
info "Syncing data..."

mkdir -p data/extracted data/pdfs data/lancedb data/metadata

if [[ -d "$SCRAPER_DIR/extracted" ]]; then
    EXTRACTED_COUNT=$(find "$SCRAPER_DIR/extracted" -name "*.txt" 2>/dev/null | wc -l | tr -d ' ')
    info "Found $EXTRACTED_COUNT extracted texts at $SCRAPER_DIR"
    rsync -a --info=progress2 "$SCRAPER_DIR/extracted/" data/extracted/
    ok "Synced extracted texts"
else
    LOCAL_COUNT=$(find data/extracted -name "*.txt" 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$LOCAL_COUNT" -gt 0 ]]; then
        ok "Using existing data/extracted/ ($LOCAL_COUNT files)"
    else
        warn "No extracted data found. Run the pipeline first:"
        echo "    make extract    # Extract text from PDFs"
    fi
fi

# Sync LanceDB if it exists
if [[ -d "$SCRAPER_DIR/isu_red_lancedb" ]]; then
    rsync -a "$SCRAPER_DIR/isu_red_lancedb/" data/lancedb/
    ok "Synced LanceDB vectors"
elif [[ -d "$SCRAPER_DIR/lancedb" ]]; then
    rsync -a "$SCRAPER_DIR/lancedb/" data/lancedb/
    ok "Synced LanceDB vectors"
fi

# Show data summary
echo
info "Data summary:"
PDF_N=$(find data/pdfs -name "*.pdf" 2>/dev/null | wc -l | tr -d ' ')
TXT_N=$(find data/extracted -name "*.txt" 2>/dev/null | wc -l | tr -d ' ')
LDB_SIZE=$(du -sh data/lancedb 2>/dev/null | cut -f1 || echo "0B")
echo "  PDFs:       $PDF_N"
echo "  Extracted:  $TXT_N"
echo "  LanceDB:    $LDB_SIZE"
echo

# ──────────────────────────────────────────────────────────────────────
# 5. Cloud setup (optional)
# ──────────────────────────────────────────────────────────────────────
if $CLOUD; then
    info "Setting up Google Cloud..."
    if [[ -x scripts/install_gcloud.sh ]]; then
        bash scripts/install_gcloud.sh
    else
        warn "scripts/install_gcloud.sh not found or not executable"
    fi

    info "Syncing data to GCS..."
    python scripts/sync_to_gcs.py

    info "Setting up Vertex AI Search..."
    python scripts/setup_vertex_search.py setup

    info "Deploying to Cloud Run..."
    bash scripts/deploy_cloud_run.sh
fi

# ──────────────────────────────────────────────────────────────────────
# 6. Start dev server
# ──────────────────────────────────────────────────────────────────────
if ! $NO_SERVE; then
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  ISU ReD AI — Ready                                        ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  Starting dev server on http://localhost:8080               ║"
    echo "║                                                            ║"
    echo "║  Search UI:  http://localhost:8080                         ║"
    echo "║  API:        http://localhost:8080/api/search?q=education   ║"
    echo "║  RAG:        http://localhost:8080/api/ask?q=education      ║"
    echo "║  Stats:      http://localhost:8080/api/stats                ║"
    echo "║                                                            ║"
    echo "║  Press Ctrl+C to stop.                                     ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo
    uvicorn web.app:app --host 0.0.0.0 --port 8080 --reload
else
    echo
    ok "Setup complete. Run 'make serve' to start the dev server."
    echo
    echo "  Available commands:"
    echo "    make serve       — Start dev server (http://localhost:8080)"
    echo "    make extract     — Extract text from PDFs"
    echo "    make embed       — Generate embeddings → LanceDB"
    echo "    make process     — Summarize + cluster papers"
    echo "    make deploy      — Deploy to Cloud Run"
    echo "    make help        — Show all targets"
fi

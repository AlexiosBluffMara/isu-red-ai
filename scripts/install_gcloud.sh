#!/usr/bin/env bash
#
# install_gcloud.sh — Install Google Cloud SDK, authenticate, and enable APIs
# for the ISU ReD Vertex AI Search project.
#
# Usage:
#   chmod +x install_gcloud.sh
#   ./install_gcloud.sh
#

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-}"
ACCOUNT="soumitlahiri@philanthropytraders.com"
BUCKET="isu-red-ai-data"
REGION="us-central1"

REQUIRED_APIS=(
    "discoveryengine.googleapis.com"
    "storage.googleapis.com"
    "aiplatform.googleapis.com"
    "documentai.googleapis.com"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*"; exit 1; }

# ---------------------------------------------------------------------------
# 1. Detect macOS
# ---------------------------------------------------------------------------
if [[ "$(uname -s)" != "Darwin" ]]; then
    error "This script is designed for macOS. Detected: $(uname -s)"
fi
info "macOS detected: $(sw_vers -productVersion)"

# ---------------------------------------------------------------------------
# 2. Install Google Cloud SDK if not present
# ---------------------------------------------------------------------------
if command -v gcloud &>/dev/null; then
    info "gcloud already installed: $(gcloud version 2>/dev/null | head -1)"
else
    info "Installing Google Cloud SDK via Homebrew …"

    if ! command -v brew &>/dev/null; then
        error "Homebrew not found. Install it first: https://brew.sh"
    fi

    brew install --cask google-cloud-sdk

    # Source completions / path
    GCLOUD_DIR="$(brew --prefix)/share/google-cloud-sdk"
    if [[ -f "$GCLOUD_DIR/path.bash.inc" ]]; then
        # shellcheck source=/dev/null
        source "$GCLOUD_DIR/path.bash.inc"
    fi

    if ! command -v gcloud &>/dev/null; then
        error "gcloud still not on PATH after install. Open a new terminal and retry."
    fi
    info "gcloud installed: $(gcloud version 2>/dev/null | head -1)"
fi

# ---------------------------------------------------------------------------
# 3. Authenticate
# ---------------------------------------------------------------------------
CURRENT_ACCOUNT=$(gcloud config get-value account 2>/dev/null || true)
if [[ "$CURRENT_ACCOUNT" == "$ACCOUNT" ]]; then
    info "Already authenticated as $ACCOUNT"
else
    info "Authenticating as $ACCOUNT …"
    gcloud auth login "$ACCOUNT" --no-launch-browser 2>/dev/null || \
        gcloud auth login "$ACCOUNT"
fi

# Application Default Credentials (for Python SDK)
info "Setting Application Default Credentials …"
gcloud auth application-default login --no-launch-browser 2>/dev/null || \
    gcloud auth application-default login

# ---------------------------------------------------------------------------
# 4. Set / create project
# ---------------------------------------------------------------------------
if [[ -z "$PROJECT_ID" ]]; then
    info "No GOOGLE_CLOUD_PROJECT set. Listing your projects …"
    gcloud projects list --format="table(projectId,name,projectNumber)" 2>/dev/null || true
    echo
    read -rp "Enter the GCP project ID to use: " PROJECT_ID
    if [[ -z "$PROJECT_ID" ]]; then
        error "Project ID is required."
    fi
fi

info "Setting project to: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# Verify project access
if ! gcloud projects describe "$PROJECT_ID" &>/dev/null; then
    warn "Cannot access project '$PROJECT_ID'. You may need to create it or check permissions."
    read -rp "Create project '$PROJECT_ID'? (y/N): " CREATE
    if [[ "$CREATE" =~ ^[Yy]$ ]]; then
        gcloud projects create "$PROJECT_ID" --name="ISU ReD AI"
        gcloud config set project "$PROJECT_ID"
        info "Project created. You may need to link a billing account."
        echo "  → https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID"
        read -rp "Press Enter once billing is linked …"
    else
        error "Cannot proceed without a valid project."
    fi
fi

# ---------------------------------------------------------------------------
# 5. Enable required APIs
# ---------------------------------------------------------------------------
info "Enabling required APIs …"
for api in "${REQUIRED_APIS[@]}"; do
    info "  Enabling $api …"
    gcloud services enable "$api" --project="$PROJECT_ID" 2>/dev/null || \
        warn "  Failed to enable $api — may need billing or permissions."
done
info "All APIs enabled."

# ---------------------------------------------------------------------------
# 6. Create GCS bucket
# ---------------------------------------------------------------------------
if gsutil ls -b "gs://$BUCKET" &>/dev/null; then
    info "Bucket gs://$BUCKET already exists."
else
    info "Creating bucket gs://$BUCKET in $REGION …"
    gsutil mb -p "$PROJECT_ID" -l "$REGION" -b on "gs://$BUCKET"
    info "Bucket created."
fi

# ---------------------------------------------------------------------------
# 7. Install Python dependencies
# ---------------------------------------------------------------------------
info "Installing Python SDK packages …"
pip install --quiet \
    google-cloud-storage \
    google-cloud-discoveryengine \
    tqdm

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Setup complete!"
echo ""
echo "  Project:  $PROJECT_ID"
echo "  Account:  $ACCOUNT"
echo "  Bucket:   gs://$BUCKET"
echo "  Region:   $REGION"
echo ""
echo "  Next steps:"
echo "    1. Sync data to GCS:"
echo "       python scripts/sync_to_gcs.py --project $PROJECT_ID"
echo ""
echo "    2. Set up Vertex AI Search:"
echo "       python scripts/setup_vertex_search.py --project $PROJECT_ID setup"
echo ""
echo "    3. Test search:"
echo "       python scripts/setup_vertex_search.py --project $PROJECT_ID search \"crop yield research\""
echo ""
echo "  Export for convenience:"
echo "    export GOOGLE_CLOUD_PROJECT=$PROJECT_ID"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

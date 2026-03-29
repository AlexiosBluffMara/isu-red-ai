#!/usr/bin/env bash
#
# deploy_cloud_run.sh — Build, push, and deploy ISU ReD AI to Cloud Run.
#
# Usage:
#   ./scripts/deploy_cloud_run.sh                    # Interactive (prompts for project)
#   ./scripts/deploy_cloud_run.sh --project my-proj   # Non-interactive
#   ./scripts/deploy_cloud_run.sh --dry-run           # Preview commands only
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (run scripts/install_gcloud.sh first)
#   - Docker installed (for local build) OR use --cloud-build to build on GCP
#   - .env file with GEMINI_API_KEY set
#

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# Defaults
# ──────────────────────────────────────────────────────────────────────
SERVICE_NAME="isu-red-ai"
REGION="${VERTEX_AI_LOCATION:-us-central1}"
REGISTRY="${REGION}-docker.pkg.dev"
REPO_NAME="isu-red-ai"
IMAGE_TAG="latest"
PORT=8080
MEMORY="1Gi"
CPU=1
MIN_INSTANCES=0
MAX_INSTANCES=3
TIMEOUT=300
DRY_RUN=false
CLOUD_BUILD=false
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-}"

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
info()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*"; }
error() { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*"; exit 1; }
run()   {
    if $DRY_RUN; then
        printf '\033[0;36m[DRY-RUN]\033[0m %s\n' "$*"
    else
        info "Running: $*"
        eval "$@"
    fi
}

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --project ID       GCP project ID (or set GOOGLE_CLOUD_PROJECT)
  --region REGION    Cloud Run region (default: $REGION)
  --service NAME     Cloud Run service name (default: $SERVICE_NAME)
  --memory SIZE      Memory allocation (default: $MEMORY)
  --max-instances N  Max instances (default: $MAX_INSTANCES)
  --cloud-build      Build on Cloud Build instead of local Docker
  --dry-run          Print commands without executing
  -h, --help         Show this help

Environment Variables:
  GOOGLE_CLOUD_PROJECT   GCP project ID
  GEMINI_API_KEY         Required for the app to function
  VERTEX_AI_LOCATION     Region (default: us-central1)
EOF
    exit 0
}

# ──────────────────────────────────────────────────────────────────────
# Parse arguments
# ──────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --project)       PROJECT_ID="$2"; shift 2 ;;
        --region)        REGION="$2"; shift 2 ;;
        --service)       SERVICE_NAME="$2"; shift 2 ;;
        --memory)        MEMORY="$2"; shift 2 ;;
        --max-instances) MAX_INSTANCES="$2"; shift 2 ;;
        --cloud-build)   CLOUD_BUILD=true; shift ;;
        --dry-run)       DRY_RUN=true; shift ;;
        -h|--help)       usage ;;
        *)               error "Unknown option: $1" ;;
    esac
done

# ──────────────────────────────────────────────────────────────────────
# Validate prerequisites
# ──────────────────────────────────────────────────────────────────────
cd "$(dirname "$0")/.."
info "Working directory: $(pwd)"

if ! command -v gcloud &>/dev/null; then
    error "gcloud not found. Run: ./scripts/install_gcloud.sh"
fi

if [[ -z "$PROJECT_ID" ]]; then
    info "No project specified. Your projects:"
    gcloud projects list --format="table(projectId,name)" 2>/dev/null || true
    echo
    read -rp "Enter GCP project ID: " PROJECT_ID
    [[ -z "$PROJECT_ID" ]] && error "Project ID required."
fi

# Load .env for GEMINI_API_KEY
GEMINI_KEY=""
if [[ -f .env ]]; then
    GEMINI_KEY=$(grep -E '^GEMINI_API_KEY=' .env | cut -d= -f2- | tr -d '"' || true)
fi
if [[ -z "$GEMINI_KEY" ]]; then
    warn "GEMINI_API_KEY not found in .env — the deployed service will need it set manually."
fi

REGISTRY="${REGION}-docker.pkg.dev"
IMAGE_URI="${REGISTRY}/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:${IMAGE_TAG}"

info "Project:  $PROJECT_ID"
info "Region:   $REGION"
info "Service:  $SERVICE_NAME"
info "Image:    $IMAGE_URI"
echo

# ──────────────────────────────────────────────────────────────────────
# 1. Enable required APIs
# ──────────────────────────────────────────────────────────────────────
info "Step 1/5: Enabling APIs..."
run "gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    --project='$PROJECT_ID' --quiet"

# ──────────────────────────────────────────────────────────────────────
# 2. Create Artifact Registry repo (if needed)
# ──────────────────────────────────────────────────────────────────────
info "Step 2/5: Setting up Artifact Registry..."
run "gcloud artifacts repositories describe '$REPO_NAME' \
    --project='$PROJECT_ID' --location='$REGION' 2>/dev/null || \
    gcloud artifacts repositories create '$REPO_NAME' \
    --project='$PROJECT_ID' --location='$REGION' \
    --repository-format=docker \
    --description='ISU ReD AI container images'"

# Configure Docker auth for the registry
run "gcloud auth configure-docker '$REGISTRY' --quiet"

# ──────────────────────────────────────────────────────────────────────
# 3. Build container image
# ──────────────────────────────────────────────────────────────────────
info "Step 3/5: Building container image..."
if $CLOUD_BUILD; then
    run "gcloud builds submit . \
        --project='$PROJECT_ID' \
        --tag='$IMAGE_URI' \
        --timeout=600"
else
    if ! command -v docker &>/dev/null; then
        error "Docker not found. Install Docker Desktop or use --cloud-build."
    fi
    run "docker build -t '$IMAGE_URI' ."
    info "Pushing image to Artifact Registry..."
    run "docker push '$IMAGE_URI'"
fi

# ──────────────────────────────────────────────────────────────────────
# 4. Deploy to Cloud Run
# ──────────────────────────────────────────────────────────────────────
info "Step 4/5: Deploying to Cloud Run..."

ENV_VARS="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,VERTEX_AI_LOCATION=$REGION"
if [[ -n "$GEMINI_KEY" ]]; then
    ENV_VARS="${ENV_VARS},GEMINI_API_KEY=$GEMINI_KEY"
fi

run "gcloud run deploy '$SERVICE_NAME' \
    --project='$PROJECT_ID' \
    --region='$REGION' \
    --image='$IMAGE_URI' \
    --port='$PORT' \
    --memory='$MEMORY' \
    --cpu='$CPU' \
    --min-instances='$MIN_INSTANCES' \
    --max-instances='$MAX_INSTANCES' \
    --timeout='$TIMEOUT' \
    --set-env-vars='$ENV_VARS' \
    --allow-unauthenticated \
    --quiet"

# ──────────────────────────────────────────────────────────────────────
# 5. Get service URL
# ──────────────────────────────────────────────────────────────────────
info "Step 5/5: Verifying deployment..."
if ! $DRY_RUN; then
    SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
        --project="$PROJECT_ID" --region="$REGION" \
        --format='value(status.url)' 2>/dev/null || echo "")

    echo
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  ISU ReD AI — Deployed to Cloud Run                        ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    if [[ -n "$SERVICE_URL" ]]; then
    echo "║  URL:     $SERVICE_URL"
    echo "║  API:     ${SERVICE_URL}/api/search?q=education"
    echo "║  Stats:   ${SERVICE_URL}/api/stats"
    fi
    echo "║  Region:  $REGION"
    echo "║  Service: $SERVICE_NAME"
    echo "║  Image:   $IMAGE_URI"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo
    echo "Useful commands:"
    echo "  gcloud run services describe $SERVICE_NAME --region=$REGION --project=$PROJECT_ID"
    echo "  gcloud run services logs read $SERVICE_NAME --region=$REGION --project=$PROJECT_ID"
    echo "  gcloud run services delete $SERVICE_NAME --region=$REGION --project=$PROJECT_ID"
else
    echo
    info "Dry run complete. No changes made."
fi

#!/usr/bin/env python3
"""
sync_to_gcs.py — Sync ISU ReD research data to Google Cloud Storage.

Uploads PDFs, extracted text, LanceDB, and metadata index to a GCS bucket
with parallel uploads, progress tracking, and incremental sync (skip by size).

Usage:
    python sync_to_gcs.py --project my-gcp-project
    python sync_to_gcs.py --project my-gcp-project --dry-run
    python sync_to_gcs.py --project my-gcp-project --workers 32 --bucket my-bucket
"""

import argparse
import logging
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from google.cloud import storage
    from google.api_core import exceptions as gcp_exceptions
except ImportError:
    sys.exit(
        "google-cloud-storage not installed. Run:\n"
        "  pip install google-cloud-storage tqdm"
    )

try:
    from tqdm import tqdm
except ImportError:
    sys.exit("tqdm not installed. Run:\n  pip install tqdm")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_BUCKET = "isu-red-ai-data"
DEFAULT_WORKERS = 16
DEFAULT_LOCATION = "us-central1"

# Where the scraper output lives (fallback search order)
CANDIDATE_SOURCE_DIRS = [
    Path.home()
    / ".openclaw/workspace/isu-genai-platform/scrapers/output/research",
    Path(__file__).resolve().parent.parent / "data",
]

# Subdirectories to sync and their GCS prefixes
SYNC_TARGETS = [
    ("pdfs", "pdfs/"),
    ("extracted", "extracted/"),
    ("isu_red_lancedb", "lancedb/"),
]
METADATA_FILE = "isu_red_index.json"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("sync_to_gcs")

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
_shutdown = False


def _handle_sigint(signum, frame):
    global _shutdown
    if _shutdown:
        log.warning("Force quit.")
        sys.exit(1)
    _shutdown = True
    log.warning("Caught SIGINT — finishing in-flight uploads then stopping.")


signal.signal(signal.SIGINT, _handle_sigint)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_source(explicit: str | None) -> Path:
    """Return the source data directory, searching candidates if not given."""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_dir():
            sys.exit(f"Source directory does not exist: {p}")
        return p
    for candidate in CANDIDATE_SOURCE_DIRS:
        if candidate.is_dir():
            log.info("Auto-detected source: %s", candidate)
            return candidate
    sys.exit(
        "Could not find source data directory. Pass --source explicitly.\n"
        f"Searched: {[str(c) for c in CANDIDATE_SOURCE_DIRS]}"
    )


def ensure_bucket(client: storage.Client, name: str, location: str) -> storage.Bucket:
    """Create or fetch the GCS bucket."""
    try:
        bucket = client.get_bucket(name)
        log.info("Bucket gs://%s already exists.", name)
    except gcp_exceptions.NotFound:
        log.info("Creating bucket gs://%s in %s …", name, location)
        bucket = client.create_bucket(name, location=location)
        log.info("Bucket created.")
    except gcp_exceptions.Forbidden as exc:
        sys.exit(f"Permission denied accessing bucket gs://{name}: {exc}")
    return bucket


def collect_files(local_dir: Path) -> list[Path]:
    """Recursively list all files under local_dir."""
    return sorted(p for p in local_dir.rglob("*") if p.is_file())


def blob_exists_same_size(bucket: storage.Bucket, blob_name: str, local_size: int) -> bool:
    """Return True if the blob exists and has the same size."""
    blob = bucket.blob(blob_name)
    blob.reload()
    return blob.size == local_size


def upload_one(
    bucket: storage.Bucket,
    local_path: Path,
    blob_name: str,
    dry_run: bool,
) -> tuple[str, str]:
    """Upload a single file. Returns (blob_name, status)."""
    if _shutdown:
        return (blob_name, "cancelled")

    local_size = local_path.stat().st_size

    # Check if already uploaded with same size
    blob = bucket.blob(blob_name)
    try:
        blob.reload()
        if blob.size == local_size:
            return (blob_name, "skipped")
    except gcp_exceptions.NotFound:
        pass

    if dry_run:
        return (blob_name, "would-upload")

    blob.upload_from_filename(str(local_path), timeout=600)
    return (blob_name, "uploaded")


def sync_directory(
    bucket: storage.Bucket,
    local_dir: Path,
    gcs_prefix: str,
    workers: int,
    dry_run: bool,
) -> dict[str, int]:
    """Sync an entire local directory to a GCS prefix. Returns status counts."""
    files = collect_files(local_dir)
    if not files:
        log.warning("  No files found in %s", local_dir)
        return {}

    total_bytes = sum(f.stat().st_size for f in files)
    log.info(
        "  %s: %d files, %.2f GB → gs://%s/%s",
        local_dir.name,
        len(files),
        total_bytes / (1024**3),
        bucket.name,
        gcs_prefix,
    )

    counts: dict[str, int] = {"uploaded": 0, "skipped": 0, "would-upload": 0, "failed": 0, "cancelled": 0}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for local_path in files:
            if _shutdown:
                break
            rel = local_path.relative_to(local_dir)
            blob_name = gcs_prefix + str(rel)
            fut = pool.submit(upload_one, bucket, local_path, blob_name, dry_run)
            futures[fut] = blob_name

        with tqdm(total=len(futures), desc=f"  {gcs_prefix}", unit="file", leave=True) as pbar:
            for fut in as_completed(futures):
                if _shutdown:
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    _, status = fut.result()
                    counts[status] = counts.get(status, 0) + 1
                except Exception as exc:
                    counts["failed"] += 1
                    log.error("  Upload failed %s: %s", futures[fut], exc)
                pbar.update(1)

    return counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Sync ISU ReD research data to Google Cloud Storage."
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        help="GCP project ID (or set GOOGLE_CLOUD_PROJECT env var).",
    )
    parser.add_argument(
        "--bucket",
        default=DEFAULT_BUCKET,
        help=f"GCS bucket name (default: {DEFAULT_BUCKET}).",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Path to the research output directory containing pdfs/, extracted/, etc.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Parallel upload threads (default: {DEFAULT_WORKERS}).",
    )
    parser.add_argument(
        "--location",
        default=DEFAULT_LOCATION,
        help=f"GCS bucket location (default: {DEFAULT_LOCATION}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without uploading.",
    )
    args = parser.parse_args()

    if not args.project:
        sys.exit(
            "GCP project not set. Use --project or set GOOGLE_CLOUD_PROJECT."
        )

    source = resolve_source(args.source)

    if args.dry_run:
        log.info("=== DRY RUN — no files will be uploaded ===")

    log.info("Project : %s", args.project)
    log.info("Bucket  : gs://%s", args.bucket)
    log.info("Source  : %s", source)
    log.info("Workers : %d", args.workers)

    client = storage.Client(project=args.project)
    bucket = ensure_bucket(client, args.bucket, args.location)

    total_counts: dict[str, int] = {}
    t0 = time.monotonic()

    # Sync each subdirectory
    for subdir, gcs_prefix in SYNC_TARGETS:
        if _shutdown:
            break
        local_dir = source / subdir
        if not local_dir.is_dir():
            log.warning("Skipping %s — directory not found.", local_dir)
            continue
        counts = sync_directory(bucket, local_dir, gcs_prefix, args.workers, args.dry_run)
        for k, v in counts.items():
            total_counts[k] = total_counts.get(k, 0) + v

    # Sync metadata file
    if not _shutdown:
        meta_path = source / METADATA_FILE
        if meta_path.is_file():
            log.info("  Metadata: %s → gs://%s/metadata/%s", meta_path.name, bucket.name, METADATA_FILE)
            blob_name = f"metadata/{METADATA_FILE}"
            _, status = upload_one(bucket, meta_path, blob_name, args.dry_run)
            total_counts[status] = total_counts.get(status, 0) + 1
            log.info("  Metadata: %s", status)
        else:
            log.warning("Metadata file not found: %s", meta_path)

    elapsed = time.monotonic() - t0
    log.info("─" * 50)
    log.info("Done in %.1f s", elapsed)
    for status, count in sorted(total_counts.items()):
        log.info("  %-14s %d", status, count)

    if _shutdown:
        log.warning("Sync interrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()

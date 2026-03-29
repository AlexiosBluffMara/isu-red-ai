"""Centralized configuration for ISU ReD AI pipeline."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── API Keys (from environment) ──────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
VERTEX_AI_LOCATION = os.environ.get("VERTEX_AI_LOCATION", "us-central1")

# ── Paths ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
PDFS_DIR = Path(os.environ.get("PDFS_DIR", DATA_DIR / "pdfs"))
EXTRACTED_DIR = Path(os.environ.get("EXTRACTED_DIR", DATA_DIR / "extracted"))
PROCESSED_DIR = Path(os.environ.get("PROCESSED_DIR", DATA_DIR / "processed"))
LANCEDB_DIR = Path(os.environ.get("LANCEDB_DIR", DATA_DIR / "lancedb"))
METADATA_DIR = DATA_DIR / "metadata"
PAPERS_DB = Path(os.environ.get("PAPERS_DB", METADATA_DIR / "papers_database.json"))
INDEX_PATH = METADATA_DIR / "isu_red_index.json"
CHUNKS_PATH = DATA_DIR / "chunks.json"

# ── Models ────────────────────────────────────────────────────────────
EXTRACT_MODEL = "gemini-2.5-flash"
RETRY_MODEL = "gemini-2.5-pro"
EMBED_MODEL = "gemini-embedding-2-preview"
EMBED_DIM = 3072

# ── Chunking ──────────────────────────────────────────────────────────
CHUNK_SIZE = 1500       # chars per chunk
CHUNK_OVERLAP = 300     # overlap between chunks
MIN_CHUNK_SIZE = 100    # discard tiny trailing chunks

# ── Extraction ────────────────────────────────────────────────────────
EXTRACT_PROMPT = (
    "Extract ALL text content from this PDF document. "
    "Return ONLY the raw extracted text, preserving paragraph structure and headings. "
    "Include all body text, figure captions, table contents, footnotes, and references. "
    "Do NOT add any commentary, formatting, or markdown. Just the plain text."
)
MAX_PDF_SIZE = 20 * 1024 * 1024  # 20 MB
FLASH_TIMEOUT = 120               # seconds
RETRY_TIMEOUT = 120               # seconds
LOCAL_TEXT_THRESHOLD = 200         # min chars from PyMuPDF to skip API

# ── Embedding ─────────────────────────────────────────────────────────
EMBED_BATCH_SIZE = 80   # texts per API call
EMBED_CONCURRENCY = 4   # parallel embed requests

# ── Ensure dirs exist ─────────────────────────────────────────────────
for d in [PDFS_DIR, EXTRACTED_DIR, PROCESSED_DIR, LANCEDB_DIR, METADATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

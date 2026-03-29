#!/usr/bin/env python3
"""ISU ReD AI — Embedding pipeline.

Chunks extracted text and embeds via Gemini, storing vectors in LanceDB.

Usage:
    python -m pipeline.embed --source /path/to/extracted
"""

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path

import lancedb
import numpy as np
import pyarrow as pa
from google import genai
from tqdm import tqdm

from pipeline.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBED_BATCH_SIZE,
    EMBED_CONCURRENCY,
    EMBED_DIM,
    EMBED_MODEL,
    EXTRACTED_DIR,
    GEMINI_API_KEY,
    LANCEDB_DIR,
    METADATA_DIR,
    MIN_CHUNK_SIZE,
    PAPERS_DB,
)

log = logging.getLogger("isu-red-ai.embed")

TABLE_NAME = "isu_red_papers"
CHECKPOINT_PATH = METADATA_DIR / "embed_checkpoint.json"


# ── Checkpoint ────────────────────────────────────────────────────────

def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text())
    return {"completed": [], "total_chunks": 0}


def save_checkpoint(ckpt: dict) -> None:
    tmp = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(ckpt, indent=2))
    tmp.rename(CHECKPOINT_PATH)


# ── Metadata parsing ─────────────────────────────────────────────────

def load_papers_db() -> dict[str, dict]:
    """Load papers metadata database (paper_id → {title, authors, year, pdf_url})."""
    if PAPERS_DB.exists():
        try:
            data = json.loads(PAPERS_DB.read_text())
            if isinstance(data, list):
                return {entry.get("id", entry.get("filename", "")): entry for entry in data}
            return data
        except Exception as exc:
            log.warning("Could not load papers DB: %s", exc)
    return {}


def parse_metadata_from_text(text: str, filename: str) -> dict:
    """Heuristic metadata extraction from first lines of text."""
    lines = [l.strip() for l in text.split("\n") if l.strip()][:10]
    title = lines[0] if lines else filename
    authors = lines[1] if len(lines) > 1 else "Unknown"

    year_match = re.search(r"\b(19|20)\d{2}\b", " ".join(lines[:5]))
    year = year_match.group(0) if year_match else "Unknown"

    return {"title": title[:300], "authors": authors[:300], "year": year}


# ── Chunking ──────────────────────────────────────────────────────────

def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if len(chunk.strip()) >= MIN_CHUNK_SIZE:
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ── Embedding ─────────────────────────────────────────────────────────

async def embed_batch(
    client: genai.Client,
    texts: list[str],
    semaphore: asyncio.Semaphore,
) -> list[list[float]]:
    """Embed a batch of texts via Gemini API."""
    async with semaphore:
        try:
            resp = await asyncio.to_thread(
                client.models.embed_content,
                model=EMBED_MODEL,
                contents=texts,
            )
            return [e.values for e in resp.embeddings]
        except Exception as exc:
            log.error("Embedding batch failed: %s", exc)
            return [np.zeros(EMBED_DIM).tolist() for _ in texts]


# ── LanceDB table setup ──────────────────────────────────────────────

def get_or_create_table(db: lancedb.DBConnection) -> lancedb.table.Table:
    """Open existing table or create with schema."""
    existing = [t for t in db.table_names()] if hasattr(db, 'table_names') else list(db.list_tables())
    if TABLE_NAME in existing:
        return db.open_table(TABLE_NAME)
    schema = pa.schema([
        pa.field("text", pa.string()),
        pa.field("source_file", pa.string()),
        pa.field("title", pa.string()),
        pa.field("authors", pa.string()),
        pa.field("year", pa.string()),
        pa.field("pdf_url", pa.string()),
        pa.field("chunk_idx", pa.int32()),
        pa.field("vector", pa.list_(pa.float32(), EMBED_DIM)),
    ])
    return db.create_table(TABLE_NAME, schema=schema)


# ── Main pipeline ─────────────────────────────────────────────────────

async def run_embedding(source_dir: Path, workers: int = 4) -> dict:
    """Chunk, embed, and store all extracted texts."""
    txt_files = sorted(source_dir.glob("*.txt"))
    if not txt_files:
        log.error("No .txt files found in %s", source_dir)
        return {}

    ckpt = load_checkpoint()
    completed_set = set(ckpt["completed"])
    pending = [f for f in txt_files if f.stem not in completed_set]

    log.info("Total texts: %d | Done: %d | Pending: %d", len(txt_files), len(completed_set), len(pending))
    if not pending:
        log.info("All texts already embedded.")
        return {"total_chunks": ckpt["total_chunks"]}

    papers_db = load_papers_db()
    client = genai.Client(api_key=GEMINI_API_KEY)
    db = lancedb.connect(str(LANCEDB_DIR))
    table = get_or_create_table(db)
    semaphore = asyncio.Semaphore(workers)
    total_new_chunks = 0

    pbar = tqdm(pending, desc="Embedding", unit="file")
    for txt_file in pbar:
        paper_id = txt_file.stem
        text = txt_file.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            ckpt["completed"].append(paper_id)
            continue

        # Metadata
        db_entry = papers_db.get(paper_id, {})
        parsed = parse_metadata_from_text(text, paper_id)
        meta = {
            "title": db_entry.get("title", parsed["title"]),
            "authors": db_entry.get("authors", parsed["authors"]),
            "year": str(db_entry.get("year", parsed["year"])),
            "pdf_url": db_entry.get("pdf_url", db_entry.get("url", "")),
            "source_file": paper_id,
        }

        # Chunk
        chunks = chunk_text(text)
        if not chunks:
            ckpt["completed"].append(paper_id)
            continue

        # Embed in batches
        all_vectors: list[list[float]] = []
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[i : i + EMBED_BATCH_SIZE]
            vectors = await embed_batch(client, batch, semaphore)
            all_vectors.extend(vectors)

        # Build records
        records = []
        for idx, (chunk, vec) in enumerate(zip(chunks, all_vectors)):
            records.append({
                "text": chunk,
                "source_file": meta["source_file"],
                "title": meta["title"],
                "authors": meta["authors"],
                "year": meta["year"],
                "pdf_url": meta["pdf_url"],
                "chunk_idx": idx,
                "vector": vec,
            })

        table.add(records)
        total_new_chunks += len(records)
        ckpt["completed"].append(paper_id)
        ckpt["total_chunks"] += len(records)

        # Checkpoint every 100 files
        if len(ckpt["completed"]) % 100 == 0:
            save_checkpoint(ckpt)
            pbar.set_postfix(chunks=ckpt["total_chunks"])

    save_checkpoint(ckpt)
    log.info("Embedded %d new chunks from %d files. Total: %d chunks.", total_new_chunks, len(pending), ckpt["total_chunks"])
    return {"new_chunks": total_new_chunks, "total_chunks": ckpt["total_chunks"]}


# ── CLI ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ISU ReD AI — Embedding Pipeline")
    parser.add_argument("--source", type=Path, default=EXTRACTED_DIR, help="Directory of extracted .txt files")
    parser.add_argument("--workers", type=int, default=EMBED_CONCURRENCY, help="Concurrent embed requests")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if not GEMINI_API_KEY:
        log.error("GEMINI_API_KEY not set.")
        sys.exit(1)

    t0 = time.perf_counter()
    result = asyncio.run(run_embedding(args.source, args.workers))
    elapsed = time.perf_counter() - t0
    log.info("Done in %.1fs — %s", elapsed, json.dumps(result))


if __name__ == "__main__":
    main()

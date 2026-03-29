#!/usr/bin/env python3
"""ISU ReD AI — PDF text extraction pipeline.

Uses Gemini 2.5 Flash for primary extraction, Gemini 2.5 Pro for retries,
and falls back to PyMuPDF for local extraction.

Usage:
    python -m pipeline.extract --source /path/to/pdfs --workers 4
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF
from google import genai
from tqdm import tqdm

from pipeline.config import (
    EXTRACT_MODEL,
    EXTRACT_PROMPT,
    EXTRACTED_DIR,
    FLASH_TIMEOUT,
    GEMINI_API_KEY,
    LOCAL_TEXT_THRESHOLD,
    MAX_PDF_SIZE,
    METADATA_DIR,
    PDFS_DIR,
    RETRY_MODEL,
    RETRY_TIMEOUT,
)

log = logging.getLogger("isu-red-ai.extract")

CHECKPOINT_PATH = METADATA_DIR / "extract_checkpoint.json"


# ── Checkpoint persistence ────────────────────────────────────────────

def load_checkpoint() -> dict:
    """Load extraction checkpoint (completed paper IDs + failure counts)."""
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text())
    return {"completed": [], "failed": {}, "stats": {"flash": 0, "pro": 0, "local": 0, "skipped": 0}}


def save_checkpoint(ckpt: dict) -> None:
    """Persist checkpoint atomically."""
    tmp = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(ckpt, indent=2))
    tmp.rename(CHECKPOINT_PATH)


# ── Local extraction via PyMuPDF ──────────────────────────────────────

def extract_local(pdf_path: Path) -> str | None:
    """Extract text from a PDF using PyMuPDF. Returns None on failure."""
    try:
        doc = fitz.open(str(pdf_path))
        pages = [page.get_text() for page in doc]
        doc.close()
        text = "\n\n".join(pages).strip()
        return text if len(text) >= LOCAL_TEXT_THRESHOLD else None
    except Exception as exc:
        log.debug("PyMuPDF failed on %s: %s", pdf_path.name, exc)
        return None


# ── Gemini API extraction ─────────────────────────────────────────────

async def extract_gemini(
    client: genai.Client,
    pdf_path: Path,
    model: str,
    timeout: int,
) -> str | None:
    """Upload PDF to Gemini and extract text. Returns None on failure."""
    try:
        pdf_bytes = pdf_path.read_bytes()
        if len(pdf_bytes) > MAX_PDF_SIZE:
            log.warning("Skipping oversized PDF (%d MB): %s", len(pdf_bytes) // (1024 * 1024), pdf_path.name)
            return None

        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=[
                    genai.types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    EXTRACT_PROMPT,
                ],
            ),
            timeout=timeout,
        )
        text = response.text.strip() if response.text else ""
        return text if len(text) >= LOCAL_TEXT_THRESHOLD else None
    except asyncio.TimeoutError:
        log.warning("Timeout (%ds) on %s with %s", timeout, pdf_path.name, model)
        return None
    except Exception as exc:
        log.warning("Gemini %s failed on %s: %s", model, pdf_path.name, exc)
        return None


# ── Single-file pipeline ──────────────────────────────────────────────

async def extract_one(
    client: genai.Client,
    pdf_path: Path,
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    ckpt: dict,
) -> str:
    """Extract text from one PDF. Returns extraction method used."""
    paper_id = pdf_path.stem
    out_file = output_dir / f"{paper_id}.txt"

    if out_file.exists() and out_file.stat().st_size > 0:
        return "skipped"

    async with semaphore:
        # Try Gemini Flash first
        text = await extract_gemini(client, pdf_path, EXTRACT_MODEL, FLASH_TIMEOUT)
        if text:
            out_file.write_text(text, encoding="utf-8")
            return "flash"

        # Retry with Gemini Pro
        text = await extract_gemini(client, pdf_path, RETRY_MODEL, RETRY_TIMEOUT)
        if text:
            out_file.write_text(text, encoding="utf-8")
            return "pro"

        # Fall back to local PyMuPDF extraction
        text = extract_local(pdf_path)
        if text:
            out_file.write_text(text, encoding="utf-8")
            return "local"

        return "failed"


# ── Batch pipeline ────────────────────────────────────────────────────

async def run_extraction(
    source_dir: Path,
    output_dir: Path,
    workers: int = 4,
    batch_size: int = 50,
) -> dict:
    """Run extraction over all PDFs in source_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(source_dir.glob("*.pdf"))
    if not pdfs:
        log.error("No PDFs found in %s", source_dir)
        return {}

    ckpt = load_checkpoint()
    completed_set = set(ckpt["completed"])
    pending = [p for p in pdfs if p.stem not in completed_set]

    log.info("Total PDFs: %d | Already done: %d | Pending: %d", len(pdfs), len(completed_set), len(pending))

    if not pending:
        log.info("All PDFs already extracted.")
        return ckpt["stats"]

    client = genai.Client(api_key=GEMINI_API_KEY)
    semaphore = asyncio.Semaphore(workers)
    stats = ckpt["stats"]

    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start : batch_start + batch_size]
        log.info("Processing batch %d–%d of %d", batch_start + 1, batch_start + len(batch), len(pending))

        tasks = [extract_one(client, pdf, output_dir, semaphore, ckpt) for pdf in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for pdf, result in zip(batch, results):
            if isinstance(result, Exception):
                log.error("Exception extracting %s: %s", pdf.name, result)
                ckpt["failed"][pdf.stem] = ckpt["failed"].get(pdf.stem, 0) + 1
                stats["skipped"] = stats.get("skipped", 0) + 1
            else:
                stats[result] = stats.get(result, 0) + 1
                if result != "failed":
                    ckpt["completed"].append(pdf.stem)
                else:
                    ckpt["failed"][pdf.stem] = ckpt["failed"].get(pdf.stem, 0) + 1

        ckpt["stats"] = stats
        save_checkpoint(ckpt)

    log.info(
        "Extraction complete — Flash: %d | Pro: %d | Local: %d | Skipped: %d | Failed: %d",
        stats.get("flash", 0),
        stats.get("pro", 0),
        stats.get("local", 0),
        stats.get("skipped", 0),
        stats.get("failed", 0),
    )
    return stats


# ── CLI ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ISU ReD AI — PDF Text Extraction")
    parser.add_argument("--source", type=Path, default=PDFS_DIR, help="Directory containing PDFs")
    parser.add_argument("--output", type=Path, default=EXTRACTED_DIR, help="Output directory for .txt files")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent extraction workers")
    parser.add_argument("--batch-size", type=int, default=50, help="PDFs per checkpoint batch")
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if not GEMINI_API_KEY:
        log.error("GEMINI_API_KEY not set. Export it or add to .env")
        sys.exit(1)

    t0 = time.perf_counter()
    stats = asyncio.run(run_extraction(args.source, args.output, args.workers, args.batch_size))
    elapsed = time.perf_counter() - t0
    log.info("Done in %.1fs — %s", elapsed, json.dumps(stats))


if __name__ == "__main__":
    main()

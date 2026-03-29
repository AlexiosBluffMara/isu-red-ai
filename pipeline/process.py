#!/usr/bin/env python3
"""ISU ReD AI — Post-processing pipeline.

Generates AI summaries and discovers topic clusters from extracted texts.

Usage:
    python -m pipeline.process --clusters 25
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import lancedb
import numpy as np
from google import genai
from sklearn.cluster import KMeans
from tqdm import tqdm

from pipeline.config import (
    EMBED_DIM,
    EMBED_MODEL,
    EXTRACTED_DIR,
    GEMINI_API_KEY,
    LANCEDB_DIR,
    METADATA_DIR,
    PROCESSED_DIR,
)

log = logging.getLogger("isu-red-ai.process")

TABLE_NAME = "isu_red_papers"
SUMMARY_MODEL = "gemini-2.5-flash"

SUMMARY_PROMPT = (
    "Write a concise academic abstract (3–5 sentences) summarizing this research paper. "
    "Include the research question, methodology, key findings, and significance. "
    "Return ONLY the abstract text, no commentary.\n\n{text}"
)

CLUSTER_LABEL_PROMPT = (
    "Below are excerpts from several academic papers that belong to the same topic cluster. "
    "Generate a concise topic label (3–6 words) and a one-sentence description.\n"
    "Return JSON: {{\"label\": \"...\", \"description\": \"...\"}}\n\n{excerpts}"
)


# ── Summarization ─────────────────────────────────────────────────────

async def summarize_one(
    client: genai.Client,
    text: str,
    semaphore: asyncio.Semaphore,
) -> str:
    """Generate a proto-abstract for one paper."""
    async with semaphore:
        try:
            # Truncate to first ~8000 chars for summary context
            snippet = text[:8000]
            resp = await asyncio.to_thread(
                client.models.generate_content,
                model=SUMMARY_MODEL,
                contents=SUMMARY_PROMPT.format(text=snippet),
            )
            return resp.text.strip() if resp.text else ""
        except Exception as exc:
            log.warning("Summary failed: %s", exc)
            return ""


# ── Clustering ────────────────────────────────────────────────────────

def get_paper_embeddings(db_path: Path) -> tuple[list[str], np.ndarray]:
    """Load centroid embeddings per paper from LanceDB (average of chunk vectors)."""
    db = lancedb.connect(str(db_path))
    table = db.open_table(TABLE_NAME)

    # Pull all rows — source_file + vector
    df = table.to_pandas()
    if df.empty:
        return [], np.array([])

    paper_vecs: dict[str, list[np.ndarray]] = {}
    for _, row in df.iterrows():
        src = row["source_file"]
        vec = np.array(row["vector"], dtype=np.float32)
        paper_vecs.setdefault(src, []).append(vec)

    paper_ids = sorted(paper_vecs.keys())
    centroids = np.array([np.mean(paper_vecs[pid], axis=0) for pid in paper_ids])
    return paper_ids, centroids


async def label_cluster(
    client: genai.Client,
    excerpts: list[str],
    semaphore: asyncio.Semaphore,
) -> dict:
    """Generate a topic label for a cluster using sample excerpts."""
    async with semaphore:
        try:
            combined = "\n---\n".join(exc[:500] for exc in excerpts[:5])
            resp = await asyncio.to_thread(
                client.models.generate_content,
                model=SUMMARY_MODEL,
                contents=CLUSTER_LABEL_PROMPT.format(excerpts=combined),
            )
            text = resp.text.strip() if resp.text else "{}"
            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            return json.loads(text)
        except Exception as exc:
            log.warning("Cluster labeling failed: %s", exc)
            return {"label": "Unknown", "description": ""}


# ── Main pipeline ─────────────────────────────────────────────────────

async def run_processing(
    source_dir: Path,
    output_dir: Path,
    n_clusters: int = 25,
    summary_workers: int = 4,
) -> dict:
    """Generate summaries and cluster papers."""
    output_dir.mkdir(parents=True, exist_ok=True)

    txt_files = sorted(source_dir.glob("*.txt"))
    if not txt_files:
        log.error("No .txt files in %s", source_dir)
        return {}

    client = genai.Client(api_key=GEMINI_API_KEY)
    semaphore = asyncio.Semaphore(summary_workers)

    # ── Phase 1: Summaries ────────────────────────────────────────────
    log.info("Phase 1: Generating summaries for %d papers...", len(txt_files))
    paper_texts: dict[str, str] = {}
    summaries: dict[str, str] = {}

    for txt_file in txt_files:
        paper_id = txt_file.stem
        text = txt_file.read_text(encoding="utf-8", errors="replace").strip()
        paper_texts[paper_id] = text

        out_path = output_dir / f"{paper_id}.json"
        if out_path.exists():
            try:
                existing = json.loads(out_path.read_text())
                if existing.get("summary"):
                    summaries[paper_id] = existing["summary"]
                    continue
            except Exception:
                pass

    pending_ids = [pid for pid in paper_texts if pid not in summaries]
    log.info("Summaries: %d cached, %d pending", len(summaries), len(pending_ids))

    tasks = [summarize_one(client, paper_texts[pid], semaphore) for pid in pending_ids]
    results = []
    for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Summarizing"):
        results.append(await coro)

    for pid, summary in zip(pending_ids, results):
        summaries[pid] = summary

    # ── Phase 2: Clustering ───────────────────────────────────────────
    log.info("Phase 2: Clustering %d papers into %d topics...", len(paper_texts), n_clusters)
    paper_ids, embeddings = get_paper_embeddings(LANCEDB_DIR)

    cluster_assignments: dict[str, int] = {}
    cluster_info: dict[int, dict] = {}

    if len(embeddings) >= n_clusters:
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)

        for pid, label in zip(paper_ids, labels):
            cluster_assignments[pid] = int(label)

        # Label each cluster using sample excerpts
        log.info("Labeling %d clusters...", n_clusters)
        cluster_papers: dict[int, list[str]] = {}
        for pid, label in zip(paper_ids, labels):
            cluster_papers.setdefault(int(label), []).append(pid)

        label_tasks = []
        cluster_indices = sorted(cluster_papers.keys())
        for cid in cluster_indices:
            members = cluster_papers[cid]
            excerpts = [paper_texts.get(pid, "")[:500] for pid in members[:5]]
            label_tasks.append(label_cluster(client, excerpts, semaphore))

        label_results = await asyncio.gather(*label_tasks)
        for cid, lr in zip(cluster_indices, label_results):
            cluster_info[cid] = {
                "cluster_id": cid,
                "label": lr.get("label", f"Cluster {cid}"),
                "description": lr.get("description", ""),
                "paper_count": len(cluster_papers[cid]),
                "sample_papers": cluster_papers[cid][:10],
            }
    else:
        log.warning("Not enough embeddings (%d) for %d clusters. Skipping clustering.", len(embeddings), n_clusters)

    # ── Phase 3: Write outputs ────────────────────────────────────────
    log.info("Phase 3: Writing processed outputs...")
    for paper_id, text in tqdm(paper_texts.items(), desc="Writing"):
        out_path = output_dir / f"{paper_id}.json"
        record = {
            "paper_id": paper_id,
            "raw_text": text[:500],  # first 500 chars as preview
            "summary": summaries.get(paper_id, ""),
            "cluster_id": cluster_assignments.get(paper_id),
            "topics": [],
        }
        cid = cluster_assignments.get(paper_id)
        if cid is not None and cid in cluster_info:
            record["topics"] = [cluster_info[cid]["label"]]
        out_path.write_text(json.dumps(record, indent=2))

    # Write cluster metadata
    clusters_path = METADATA_DIR / "topic_clusters.json"
    clusters_path.write_text(json.dumps(list(cluster_info.values()), indent=2))
    log.info("Wrote %d cluster definitions to %s", len(cluster_info), clusters_path)

    return {
        "papers": len(paper_texts),
        "summaries": len(summaries),
        "clusters": len(cluster_info),
    }


# ── CLI ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ISU ReD AI — Post-Processing Pipeline")
    parser.add_argument("--source", type=Path, default=EXTRACTED_DIR, help="Extracted text directory")
    parser.add_argument("--output", type=Path, default=PROCESSED_DIR, help="Output directory for processed JSON")
    parser.add_argument("--clusters", type=int, default=25, help="Number of topic clusters")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent summary workers")
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
    result = asyncio.run(run_processing(args.source, args.output, args.clusters, args.workers))
    elapsed = time.perf_counter() - t0
    log.info("Done in %.1fs — %s", elapsed, json.dumps(result))


if __name__ == "__main__":
    main()

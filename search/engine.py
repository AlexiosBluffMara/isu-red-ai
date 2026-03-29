"""ISU ReD AI — RAG Search Engine over LanceDB vectors."""

import json
import os
from pathlib import Path

import lancedb
from google import genai

# Allow overriding data location
LANCEDB_DIR = os.environ.get(
    "LANCEDB_DIR",
    str(Path(__file__).parent.parent / "data" / "lancedb"),
)
TABLE_NAME = "isu_red_papers"
EMBED_MODEL = "gemini-embedding-2-preview"
ANSWER_MODEL = "gemini-2.5-flash"


def get_client():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


def get_table():
    db = lancedb.connect(LANCEDB_DIR)
    return db.open_table(TABLE_NAME)


def embed_query(client, query: str) -> list[float]:
    """Embed a search query using Gemini."""
    resp = client.models.embed_content(
        model=EMBED_MODEL,
        contents=query,
    )
    return resp.embeddings[0].values


def search(query: str, top_k: int = 10, year_filter: str | None = None) -> list[dict]:
    """Search the ISU ReD vector database."""
    client = get_client()
    table = get_table()

    query_vec = embed_query(client, query)

    results = (
        table.search(query_vec)
        .limit(top_k * 3)  # fetch extra for dedup
        .to_list()
    )

    # Deduplicate by source file, keep best score per paper
    seen = {}
    for r in results:
        key = r.get("source_file", "")
        if key not in seen or r.get("_distance", 999) < seen[key].get("_distance", 999):
            seen[key] = r

    output = []
    for r in sorted(seen.values(), key=lambda x: x.get("_distance", 999)):
        if year_filter and r.get("year") and year_filter not in str(r.get("year", "")):
            continue
        output.append({
            "title": r.get("title", "Unknown"),
            "authors": r.get("authors", "Unknown"),
            "year": r.get("year", "Unknown"),
            "source_file": r.get("source_file", ""),
            "pdf_url": r.get("pdf_url", ""),
            "text": r.get("text", ""),
            "score": 1 - r.get("_distance", 0),
            "chunk_idx": r.get("chunk_idx", 0),
        })
        if len(output) >= top_k:
            break

    return output


def search_similar(query_text: str, top_k: int = 8, exclude_title: str | None = None) -> list[dict]:
    """Find papers similar to a given text, optionally excluding a specific title."""
    results = search(query_text, top_k=top_k + 5)
    if exclude_title:
        exclude_lower = exclude_title.strip().lower()
        results = [r for r in results if r.get("title", "").strip().lower() != exclude_lower]
    return results[:top_k]


def rag_answer(query: str, top_k: int = 8) -> dict:
    """Full RAG: search + generate grounded answer."""
    client = get_client()
    results = search(query, top_k=top_k)

    if not results:
        return {"answer": "No relevant results found.", "sources": []}

    # Build context from search results
    context_parts = []
    for i, r in enumerate(results, 1):
        context_parts.append(
            f"[{i}] \"{r['title']}\" by {r['authors']} ({r['year']})\n"
            f"Source: {r['source_file']}\n"
            f"Excerpt: {r['text'][:800]}\n"
        )
    context = "\n---\n".join(context_parts)

    prompt = (
        f"You are a research assistant for Illinois State University's ReD repository. "
        f"Answer the following question using ONLY the provided sources. "
        f"Cite sources by number [1], [2], etc. Be specific and scholarly.\n\n"
        f"Question: {query}\n\n"
        f"Sources:\n{context}\n\n"
        f"Answer:"
    )

    response = client.models.generate_content(
        model=ANSWER_MODEL,
        contents=prompt,
    )

    return {
        "answer": response.text,
        "sources": results,
        "query": query,
    }

#!/usr/bin/env python3
"""ISU ReD AI — Web Application (FastAPI)."""

import os
import sys
import html

from dotenv import load_dotenv

load_dotenv()

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from search.engine import rag_answer, search
from web.papers_data import (
    compute_decade_counts,
    compute_overview_stats,
    compute_subject_categories,
    compute_subject_counts,
    compute_top_authors,
    compute_wordcloud,
    compute_year_counts,
    get_paper_detail,
    search_papers,
)

app = FastAPI(title="ISU ReD AI", version="2.0.0")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ── Pages ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── Search API ────────────────────────────────────────────────────────

@app.get("/api/search")
async def api_search(q: str, k: int = 10, year: str | None = None):
    """Vector similarity search."""
    if not q or not q.strip():
        return JSONResponse({"error": "Query required"}, status_code=400)
    q = q.strip()[:500]
    results = search(q, top_k=min(k, 50), year_filter=year)
    return {"query": q, "results": results, "count": len(results)}


@app.get("/api/ask")
async def api_ask(q: str, k: int = 8):
    """RAG: search + AI-generated answer."""
    if not q or not q.strip():
        return JSONResponse({"error": "Query required"}, status_code=400)
    q = q.strip()[:500]
    result = rag_answer(q, top_k=min(k, 20))
    result["answer"] = html.escape(result["answer"])
    return result


# ── Data / Visualization API ─────────────────────────────────────────

@app.get("/api/stats")
async def api_stats():
    """Return database statistics."""
    try:
        import lancedb
        db_dir = os.environ.get(
            "LANCEDB_DIR",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "lancedb"),
        )
        db = lancedb.connect(db_dir)
        table = db.open_table("isu_red_papers")
        chunk_count = table.count_rows()
    except Exception:
        chunk_count = 0

    overview = compute_overview_stats()
    return {
        "total_papers": overview["total_papers"],
        "total_chunks": chunk_count,
        "with_abstracts": overview["with_abstracts"],
        "with_pdfs": overview["with_pdfs"],
        "unique_subjects": overview["unique_subjects"],
        "year_range": f"{overview['year_min']}–{overview['year_max']}",
        "embedding_dim": 3072,
        "model": "gemini-embedding-2-preview",
        "status": "operational",
    }


@app.get("/api/subjects")
async def api_subjects(limit: int = 50):
    """Subject distribution for charts."""
    subjects = compute_subject_counts()
    return {"subjects": subjects[:min(limit, 500)], "total_unique": len(subjects)}


@app.get("/api/years")
async def api_years():
    """Year distribution for timeline charts."""
    return {"years": compute_year_counts(), "decades": compute_decade_counts()}


@app.get("/api/categories")
async def api_categories():
    """Broad academic categories for subject browsing grid."""
    return {"categories": compute_subject_categories()}


@app.get("/api/wordcloud")
async def api_wordcloud():
    """Word frequency data for word cloud visualization."""
    return {"words": compute_wordcloud()}


@app.get("/api/authors")
async def api_authors(limit: int = 50):
    """Top authors by publication count."""
    return {"authors": compute_top_authors(min(limit, 200))}


@app.get("/api/papers")
async def api_papers(
    q: str = "",
    subject: str = "",
    year_start: int | None = None,
    year_end: int | None = None,
    page: int = 1,
    per_page: int = 20,
):
    """Browse / filter papers with pagination."""
    per_page = min(per_page, 50)
    page = max(page, 1)
    return search_papers(
        query=q.strip()[:200] if q else "",
        subject=subject.strip()[:200] if subject else "",
        year_start=year_start,
        year_end=year_end,
        page=page,
        per_page=per_page,
    )


@app.get("/api/paper/{index}")
async def api_paper(index: int):
    """Get a single paper by index."""
    paper = get_paper_detail(index)
    if paper is None:
        return JSONResponse({"error": "Paper not found"}, status_code=404)
    return paper


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

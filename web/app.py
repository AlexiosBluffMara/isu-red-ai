#!/usr/bin/env python3
"""ISU ReD AI — Web Application (FastAPI)."""

import logging
import os
import sys
import time
import html
import uuid

from dotenv import load_dotenv

load_dotenv()

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

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

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("isu-red-ai.web")

# ── App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="ISU ReD AI",
    version="2.1.0",
    docs_url="/api/docs" if os.environ.get("ENABLE_DOCS") else None,
    redoc_url=None,
)

# ── Middleware ────────────────────────────────────────────────────────

ALLOWED_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:8080,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
    max_age=3600,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if request.url.path.startswith("/api/"):
            log.info(
                "[%s] %s %s → %d (%.0fms)",
                request_id, request.method, request.url.path,
                response.status_code, elapsed_ms,
            )
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# ── Static/Templates ─────────────────────────────────────────────────

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ── Health ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Liveness probe for Cloud Run / load balancers."""
    return {"status": "healthy"}


@app.get("/ready")
async def readiness():
    """Readiness probe — verifies data + model access."""
    checks = {}
    try:
        stats = compute_overview_stats()
        checks["papers_db"] = stats["total_papers"] > 0
    except Exception:
        checks["papers_db"] = False
    try:
        import lancedb
        db_dir = os.environ.get(
            "LANCEDB_DIR",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "lancedb"),
        )
        db = lancedb.connect(db_dir)
        db.open_table("isu_red_papers")
        checks["lancedb"] = True
    except Exception:
        checks["lancedb"] = False
    ready = all(checks.values())
    return JSONResponse(
        {"status": "ready" if ready else "degraded", "checks": checks},
        status_code=200 if ready else 503,
    )


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
    try:
        results = search(q, top_k=min(k, 50), year_filter=year)
    except Exception as exc:
        log.error("Search failed: %s", exc)
        return JSONResponse({"error": "Search unavailable"}, status_code=503)
    return {"query": q, "results": results, "count": len(results)}


@app.get("/api/ask")
async def api_ask(q: str, k: int = 8):
    """RAG: search + AI-generated answer."""
    if not q or not q.strip():
        return JSONResponse({"error": "Query required"}, status_code=400)
    q = q.strip()[:500]
    try:
        result = rag_answer(q, top_k=min(k, 20))
    except Exception as exc:
        log.error("RAG failed: %s", exc)
        return JSONResponse({"error": "AI answer unavailable"}, status_code=503)
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

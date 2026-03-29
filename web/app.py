#!/usr/bin/env python3
"""ISU ReD AI — Web Demo (FastAPI)."""

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

app = FastAPI(title="ISU ReD AI", version="1.0.0")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/search")
async def api_search(q: str, k: int = 10, year: str | None = None):
    """Vector similarity search."""
    if not q or not q.strip():
        return JSONResponse({"error": "Query required"}, status_code=400)
    q = q.strip()[:500]  # limit query length
    results = search(q, top_k=min(k, 50), year_filter=year)
    return {"query": q, "results": results, "count": len(results)}


@app.get("/api/ask")
async def api_ask(q: str, k: int = 8):
    """RAG: search + AI-generated answer."""
    if not q or not q.strip():
        return JSONResponse({"error": "Query required"}, status_code=400)
    q = q.strip()[:500]
    result = rag_answer(q, top_k=min(k, 20))
    # Sanitize the answer to prevent XSS
    result["answer"] = html.escape(result["answer"])
    return result


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
        count = table.count_rows()
        return {
            "total_chunks": count,
            "embedding_dim": 3072,
            "model": "gemini-embedding-2-preview",
            "status": "operational",
        }
    except Exception as e:
        return {"error": str(e), "status": "offline"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

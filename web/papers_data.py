"""ISU ReD AI — Papers Data Module.

Loads papers_database.json and provides pre-computed aggregations
for the web API (subjects, years, word cloud, browsing, etc.).
"""

import json
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path


def _find_papers_db() -> str:
    """Locate papers_database.json with multiple fallback strategies."""
    # 1. Explicit env var
    env_path = os.environ.get("PAPERS_DB", "")
    if env_path and os.path.isfile(env_path):
        return env_path

    base = Path(__file__).parent.parent / "data"

    # 2. Standard config path (works in Docker with volume mount)
    local = base / "metadata" / "papers_database.json"
    if local.is_file():
        return str(local)

    # 3. Follow symlinked data dir (dev environment)
    for symlink_name in ("pdfs", "extracted"):
        link = base / symlink_name
        if link.is_symlink():
            parent = link.resolve().parent
            candidate = parent / "papers_database.json"
            if candidate.is_file():
                return str(candidate)

    raise FileNotFoundError(
        "papers_database.json not found. Set PAPERS_DB env var or place in data/metadata/"
    )


@lru_cache(maxsize=1)
def load_papers() -> list[dict]:
    """Load and return all papers. Cached after first call."""
    path = _find_papers_db()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _extract_year(date_str: str) -> int | None:
    if not date_str:
        return None
    m = re.match(r"(\d{4})", str(date_str))
    return int(m.group(1)) if m else None


@lru_cache(maxsize=1)
def compute_subject_counts() -> list[dict]:
    """Return subject → count sorted descending."""
    counter: Counter = Counter()
    for p in load_papers():
        for s in p.get("subjects") or []:
            s = s.strip()
            if s:
                counter[s] += 1
    return [{"subject": s, "count": c} for s, c in counter.most_common()]


@lru_cache(maxsize=1)
def compute_year_counts() -> list[dict]:
    """Return year → count sorted ascending."""
    counter: Counter = Counter()
    for p in load_papers():
        y = _extract_year(p.get("date", ""))
        if y and 1800 < y < 2100:
            counter[y] += 1
    return [{"year": y, "count": c} for y, c in sorted(counter.items())]


@lru_cache(maxsize=1)
def compute_decade_counts() -> list[dict]:
    """Return decade → count sorted ascending."""
    counter: Counter = Counter()
    for p in load_papers():
        y = _extract_year(p.get("date", ""))
        if y and 1800 < y < 2100:
            decade = (y // 10) * 10
            counter[decade] += 1
    return [{"decade": f"{d}s", "count": c} for d, c in sorted(counter.items())]


STOP_WORDS = frozenset(
    "the and of in to a for is on that by with from as an at are was it "
    "this which or be not have has had been their its they was were will "
    "can could would should may might shall into than more also but about "
    "up out so do if all no when what how who where each between through "
    "over such only after before during both these those other some most "
    "under here there then them being two new between very her his him she he".split()
)


@lru_cache(maxsize=1)
def compute_wordcloud() -> list[dict]:
    """Word frequency from titles for word cloud visualization."""
    counter: Counter = Counter()
    for p in load_papers():
        title = p.get("title", "")
        words = re.findall(r"[a-zA-Z]{3,}", title.lower())
        for w in words:
            if w not in STOP_WORDS:
                counter[w] += 1
    return [{"word": w, "count": c} for w, c in counter.most_common(200)]


@lru_cache(maxsize=1)
def compute_top_authors(limit: int = 50) -> list[dict]:
    """Return top authors by paper count."""
    counter: Counter = Counter()
    for p in load_papers():
        for a in p.get("authors") or []:
            a = a.strip().rstrip(",")
            if a and a.lower() not in ("unknown", "unknown,", ""):
                counter[a] += 1
    return [{"author": a, "count": c} for a, c in counter.most_common(limit)]


@lru_cache(maxsize=1)
def compute_subject_categories() -> list[dict]:
    """Group subjects into broad academic categories for the browsing grid."""
    cats = {
        "Education & Teaching": [],
        "Science & Mathematics": [],
        "Arts & Performance": [],
        "Social Sciences": [],
        "Business & Economics": [],
        "Health & Medicine": [],
        "Law & Criminal Justice": [],
        "Engineering & Technology": [],
        "Humanities & Literature": [],
        "Library & Information Science": [],
        "Other": [],
    }

    cat_keywords = {
        "Education & Teaching": [
            "education", "teaching", "curriculum", "instruction",
            "pedagogy", "learning", "school", "student", "teacher",
            "educational", "vocational", "literacy",
        ],
        "Science & Mathematics": [
            "biology", "chemistry", "physics", "math", "geology",
            "science", "ecology", "botany", "zoology", "plant",
            "genetics", "dynamics", "applied math", "statistics",
            "astronomy", "geography", "environmental",
        ],
        "Arts & Performance": [
            "music", "theatre", "art", "dance", "performance",
            "creative", "film", "visual", "design", "drawing",
        ],
        "Social Sciences": [
            "psychology", "sociology", "political", "anthropology",
            "social", "communication", "family", "gender", "ethnic",
            "women", "history", "speech",
        ],
        "Business & Economics": [
            "business", "economics", "accounting", "finance",
            "marketing", "management", "entrepreneurial", "insurance",
            "agribusiness", "organizational",
        ],
        "Health & Medicine": [
            "nursing", "health", "medical", "kinesiology", "public health",
            "nutrition", "exercise", "clinical", "pathology", "audiology",
        ],
        "Law & Criminal Justice": [
            "criminal", "law", "justice", "legal", "fourth amendment",
            "search and seizure", "warrant", "constitution", "court",
        ],
        "Engineering & Technology": [
            "engineering", "technology", "computer", "information systems",
            "software", "cybersecurity", "network", "data", "computing",
        ],
        "Humanities & Literature": [
            "english", "literature", "philosophy", "religion", "language",
            "writing", "rhetoric", "foreign", "french", "spanish",
            "german", "classical", "humanities",
        ],
        "Library & Information Science": [
            "library", "information science", "archiv", "catalog",
            "collection", "milner",
        ],
    }

    subject_counts = {s["subject"]: s["count"] for s in compute_subject_counts()}

    for subj, count in subject_counts.items():
        subj_lower = subj.lower()
        placed = False
        for cat, keywords in cat_keywords.items():
            if any(kw in subj_lower for kw in keywords):
                cats[cat].append({"subject": subj, "count": count})
                placed = True
                break
        if not placed:
            cats["Other"].append({"subject": subj, "count": count})

    result = []
    for cat_name, subjects in cats.items():
        subjects.sort(key=lambda x: x["count"], reverse=True)
        total = sum(s["count"] for s in subjects)
        if total > 0:
            result.append({
                "category": cat_name,
                "total_papers": total,
                "subject_count": len(subjects),
                "top_subjects": subjects[:15],
            })

    result.sort(key=lambda x: x["total_papers"], reverse=True)
    return result


def search_papers(
    query: str = "",
    subject: str = "",
    year_start: int | None = None,
    year_end: int | None = None,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """Filter and paginate papers."""
    papers = load_papers()
    filtered = []

    q_lower = query.lower() if query else ""
    subj_lower = subject.lower() if subject else ""

    for p in papers:
        # Subject filter
        if subj_lower:
            subjects = [s.lower() for s in (p.get("subjects") or [])]
            if not any(subj_lower in s for s in subjects):
                continue

        # Year filter
        y = _extract_year(p.get("date", ""))
        if year_start and (not y or y < year_start):
            continue
        if year_end and (not y or y > year_end):
            continue

        # Text search (title + abstract)
        if q_lower:
            title = (p.get("title") or "").lower()
            abstract = (p.get("abstract") or "").lower()
            if q_lower not in title and q_lower not in abstract:
                continue

        filtered.append(p)

    # Sort by date descending
    def sort_key(p):
        y = _extract_year(p.get("date", ""))
        return y if y else 0

    filtered.sort(key=sort_key, reverse=True)

    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    page_results = filtered[start:end]

    # Clean results for API
    results = []
    for p in page_results:
        results.append({
            "title": p.get("title", "Untitled"),
            "authors": p.get("authors", []),
            "subjects": p.get("subjects", []),
            "abstract": p.get("abstract", ""),
            "date": p.get("date", ""),
            "year": _extract_year(p.get("date", "")),
            "pdf_url": p.get("pdf_url", ""),
            "page_url": p.get("page_url", ""),
            "doi": p.get("doi", ""),
        })

    return {
        "papers": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


def get_paper_detail(index: int) -> dict | None:
    """Get a single paper by index."""
    papers = load_papers()
    if 0 <= index < len(papers):
        p = papers[index]
        return {
            "title": p.get("title", "Untitled"),
            "authors": p.get("authors", []),
            "subjects": p.get("subjects", []),
            "abstract": p.get("abstract", ""),
            "date": p.get("date", ""),
            "year": _extract_year(p.get("date", "")),
            "pdf_url": p.get("pdf_url", ""),
            "page_url": p.get("page_url", ""),
            "doi": p.get("doi", ""),
            "index": index,
        }
    return None


@lru_cache(maxsize=1)
def compute_overview_stats() -> dict:
    """Compute overview statistics for the dashboard."""
    papers = load_papers()
    total = len(papers)
    with_abstract = sum(1 for p in papers if p.get("abstract"))
    with_pdf = sum(1 for p in papers if p.get("pdf_url"))
    with_subjects = sum(1 for p in papers if p.get("subjects"))

    years = [_extract_year(p.get("date", "")) for p in papers]
    valid_years = [y for y in years if y and 1800 < y < 2100]

    return {
        "total_papers": total,
        "with_abstracts": with_abstract,
        "with_pdfs": with_pdf,
        "with_subjects": with_subjects,
        "unique_subjects": len(compute_subject_counts()),
        "year_min": min(valid_years) if valid_years else None,
        "year_max": max(valid_years) if valid_years else None,
        "top_authors_count": len(compute_top_authors()),
    }


def compute_collection_stats(db_dir: str | None = None) -> list[dict]:
    """Get collection-level stats from LanceDB vectors."""
    try:
        import lancedb
        if not db_dir:
            db_dir = os.environ.get(
                "LANCEDB_DIR",
                str(Path(__file__).parent.parent / "data" / "lancedb"),
            )
        db = lancedb.connect(db_dir)
        table = db.open_table("isu_red_papers")
        rows = table.search().select(["collection"]).limit(300000).to_list()

        from collections import Counter as _Counter
        counts = _Counter(r.get("collection", "") for r in rows)
        result = []
        for coll, count in counts.most_common():
            name = coll.strip() if coll else "Uncategorized"
            if name:
                result.append({"collection": name, "chunks": count})
        return result
    except Exception:
        return []

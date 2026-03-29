"""Shared test fixtures."""

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PAPERS = FIXTURES_DIR / "sample_papers.json"


@pytest.fixture(autouse=True)
def _set_papers_db_env(monkeypatch):
    """Point PAPERS_DB to test fixture for all tests."""
    monkeypatch.setenv("PAPERS_DB", str(SAMPLE_PAPERS))
    # Clear LRU caches so each test gets fresh data
    from web.papers_data import (
        load_papers,
        compute_subject_counts,
        compute_year_counts,
        compute_decade_counts,
        compute_wordcloud,
        compute_top_authors,
        compute_subject_categories,
        compute_overview_stats,
    )
    for fn in [
        load_papers,
        compute_subject_counts,
        compute_year_counts,
        compute_decade_counts,
        compute_wordcloud,
        compute_top_authors,
        compute_subject_categories,
        compute_overview_stats,
    ]:
        fn.cache_clear()


@pytest.fixture
def sample_papers():
    """Load sample papers fixture."""
    with open(SAMPLE_PAPERS) as f:
        return json.load(f)

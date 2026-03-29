"""Tests for web.papers_data module."""

from web.papers_data import (
    load_papers,
    compute_subject_counts,
    compute_year_counts,
    compute_decade_counts,
    compute_wordcloud,
    compute_top_authors,
    compute_subject_categories,
    compute_overview_stats,
    search_papers,
    get_paper_detail,
)


class TestLoadPapers:
    def test_loads_all_papers(self):
        papers = load_papers()
        assert len(papers) == 8

    def test_papers_have_required_fields(self):
        papers = load_papers()
        for p in papers:
            assert "id" in p
            assert "title" in p

    def test_caching(self):
        p1 = load_papers()
        p2 = load_papers()
        assert p1 is p2  # same object = cached


class TestSubjectCounts:
    def test_returns_sorted_list(self):
        subjects = compute_subject_counts()
        assert len(subjects) > 0
        assert all("subject" in s and "count" in s for s in subjects)
        # Should be sorted descending by count
        counts = [s["count"] for s in subjects]
        assert counts == sorted(counts, reverse=True)

    def test_higher_education_appears(self):
        subjects = compute_subject_counts()
        names = [s["subject"] for s in subjects]
        assert "Higher Education" in names


class TestYearCounts:
    def test_returns_sorted_ascending(self):
        years = compute_year_counts()
        assert len(years) > 0
        year_vals = [y["year"] for y in years]
        assert year_vals == sorted(year_vals)

    def test_includes_known_years(self):
        years = compute_year_counts()
        year_vals = [y["year"] for y in years]
        assert 2023 in year_vals
        assert 2022 in year_vals


class TestDecadeCounts:
    def test_returns_decades(self):
        decades = compute_decade_counts()
        assert len(decades) > 0
        for d in decades:
            assert "decade" in d
            assert "count" in d
            assert d["count"] > 0


class TestWordcloud:
    def test_returns_word_list(self):
        words = compute_wordcloud()
        assert len(words) > 0
        assert all("word" in w and "count" in w for w in words)

    def test_excludes_stopwords(self):
        words = compute_wordcloud()
        word_list = [w["word"].lower() for w in words]
        for stop in ["the", "and", "in", "of", "a"]:
            assert stop not in word_list


class TestTopAuthors:
    def test_returns_authors(self):
        authors = compute_top_authors(5)
        assert len(authors) > 0
        assert all("author" in a and "count" in a for a in authors)


class TestSubjectCategories:
    def test_returns_categories(self):
        cats = compute_subject_categories()
        assert len(cats) > 0
        for c in cats:
            assert "category" in c
            assert "total_papers" in c
            assert "top_subjects" in c


class TestOverviewStats:
    def test_returns_all_fields(self):
        stats = compute_overview_stats()
        assert stats["total_papers"] == 8
        assert stats["with_abstracts"] > 0
        assert stats["with_pdfs"] > 0
        assert stats["unique_subjects"] > 0
        assert stats["year_min"] > 0
        assert stats["year_max"] > 0


class TestSearchPapers:
    def test_basic_search(self):
        result = search_papers(query="machine learning")
        assert result["total"] > 0
        assert len(result["papers"]) > 0

    def test_subject_filter(self):
        result = search_papers(subject="Cybersecurity")
        assert result["total"] >= 1
        for p in result["papers"]:
            subjects = p.get("subjects") or []
            assert any("Cybersecurity" in s for s in subjects)

    def test_year_range_filter(self):
        result = search_papers(year_start=2023, year_end=2024)
        assert result["total"] >= 1

    def test_pagination(self):
        result = search_papers(page=1, per_page=2)
        assert len(result["papers"]) <= 2
        assert result["page"] == 1
        assert result["per_page"] == 2

    def test_empty_query_returns_all(self):
        result = search_papers()
        assert result["total"] == 8

    def test_no_results(self):
        result = search_papers(query="zzzznonexistenttermzzzz")
        assert result["total"] == 0


class TestGetPaperDetail:
    def test_valid_index(self):
        paper = get_paper_detail(0)
        assert paper is not None
        assert "title" in paper

    def test_invalid_index(self):
        paper = get_paper_detail(9999)
        assert paper is None

    def test_negative_index(self):
        paper = get_paper_detail(-1)
        assert paper is None

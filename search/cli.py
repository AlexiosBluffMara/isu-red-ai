#!/usr/bin/env python3
"""CLI search interface for ISU ReD AI."""

import argparse
import os
import sys
import textwrap

from dotenv import load_dotenv

# Add parent to path
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])
load_dotenv()

from search.engine import rag_answer, search


def print_results(results: list[dict], verbose: bool = False):
    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        print(f"\n{'─' * 60}")
        print(f"  [{i}] {r['title']}")
        print(f"      Authors: {r['authors']}")
        print(f"      Year: {r['year']}  |  Score: {score:.3f}")
        if r.get("pdf_url"):
            print(f"      URL: {r['pdf_url']}")
        if verbose:
            print(f"      Excerpt: {textwrap.shorten(r['text'], 200)}")
    print(f"\n{'─' * 60}")


def main():
    parser = argparse.ArgumentParser(description="Search ISU ReD AI")
    parser.add_argument("query", nargs="*", help="Search query")
    parser.add_argument("-k", "--top-k", type=int, default=8, help="Number of results")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show excerpts")
    parser.add_argument("--rag", action="store_true", help="Generate AI answer with citations")
    parser.add_argument("--year", type=str, help="Filter by year")
    args = parser.parse_args()

    query = " ".join(args.query) if args.query else input("Search ISU ReD: ")

    if args.rag:
        print(f"\nSearching and generating answer for: \"{query}\"...\n")
        result = rag_answer(query, top_k=args.top_k)
        print(f"{'=' * 60}")
        print(f"  AI ANSWER")
        print(f"{'=' * 60}")
        print(f"\n{result['answer']}\n")
        print(f"{'=' * 60}")
        print(f"  SOURCES ({len(result['sources'])})")
        print(f"{'=' * 60}")
        print_results(result["sources"], verbose=args.verbose)
    else:
        print(f"\nSearching for: \"{query}\"...\n")
        results = search(query, top_k=args.top_k, year_filter=args.year)
        print(f"Found {len(results)} results:")
        print_results(results, verbose=args.verbose)


if __name__ == "__main__":
    main()

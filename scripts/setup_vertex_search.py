#!/usr/bin/env python3
"""
setup_vertex_search.py — Set up Vertex AI Search (GenAI App Builder) for ISU ReD.

Uses the $1000 GenAI App Builder credit for enterprise search over 16K+ research PDFs.

Usage:
    python setup_vertex_search.py setup          # Create data store + search engine
    python setup_vertex_search.py search "query"  # Test search
    python setup_vertex_search.py generate "query" # Grounded generation (RAG)
    python setup_vertex_search.py status          # Check data store status
    python setup_vertex_search.py cost            # Estimate costs

Requires:
    pip install google-cloud-discoveryengine google-cloud-storage
"""

import argparse
import json
import os
import sys
import time

try:
    from google.cloud import discoveryengine_v1 as discoveryengine
    from google.api_core import exceptions as gcp_exceptions
except ImportError:
    sys.exit(
        "Required packages not installed. Run:\n"
        "  pip install google-cloud-discoveryengine google-cloud-storage"
    )

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
DEFAULT_LOCATION = os.environ.get("VERTEX_AI_LOCATION", "global")
DEFAULT_BUCKET = "isu-red-ai-data"
DATA_STORE_ID = "isu-red-research"
ENGINE_ID = "isu-red-search-engine"
COLLECTION = "default_collection"

# ---------------------------------------------------------------------------
# Cost estimates (as of 2026-03, us-central1)
# See: https://cloud.google.com/generative-ai-app-builder/pricing
# ---------------------------------------------------------------------------
COST_ESTIMATES = {
    "Document indexing (unstructured)": {
        "unit": "per 1,000 documents/month",
        "price": "$2.50",
        "our_estimate": "16,372 docs → ~$40.93/month",
    },
    "Search queries": {
        "unit": "per 1,000 queries",
        "price": "$2.00 (first 10K free/month)",
        "our_estimate": "Light usage → likely free tier",
    },
    "Grounded Generation (Gemini)": {
        "unit": "per 1,000 queries",
        "price": "$15.00",
        "our_estimate": "Depends on usage",
    },
    "Document AI OCR (if needed)": {
        "unit": "per 1,000 pages",
        "price": "$1.50",
        "our_estimate": "Only if re-OCR needed; we have extracted text",
    },
    "GCS Storage": {
        "unit": "per GB/month (Standard)",
        "price": "$0.020",
        "our_estimate": "~40 GB PDFs + 2.5 GB LanceDB → ~$0.85/month",
    },
}

MONTHLY_ESTIMATE = """
╔══════════════════════════════════════════════════════════════╗
║  ESTIMATED MONTHLY COST (ISU ReD — Vertex AI Search)       ║
╠══════════════════════════════════════════════════════════════╣
║  Document indexing: ~$41/month (16,372 unstructured docs)   ║
║  Search queries:    ~$0 (10K free queries/month)            ║
║  GCS storage:       ~$1/month (42.5 GB)                     ║
║  ────────────────────────────────────────────────────        ║
║  Base cost:         ~$42/month                              ║
║  + Grounded Gen:    ~$15 per 1K queries (on top)            ║
║                                                              ║
║  $1000 credit ≈ 23+ months of base indexing + search        ║
║  Or ~65K grounded generation queries                         ║
╚══════════════════════════════════════════════════════════════╝
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parent(project: str, location: str) -> str:
    return f"projects/{project}/locations/{location}"


def _data_store_name(project: str, location: str) -> str:
    return (
        f"projects/{project}/locations/{location}"
        f"/collections/{COLLECTION}/dataStores/{DATA_STORE_ID}"
    )


def _engine_name(project: str, location: str) -> str:
    return (
        f"projects/{project}/locations/{location}"
        f"/collections/{COLLECTION}/engines/{ENGINE_ID}"
    )


# ---------------------------------------------------------------------------
# Data Store
# ---------------------------------------------------------------------------


def create_data_store(project: str, location: str, bucket: str) -> None:
    """Create a Vertex AI Search unstructured data store backed by GCS."""
    client = discoveryengine.DataStoreServiceClient()
    parent = _parent(project, location)

    data_store = discoveryengine.DataStore(
        display_name="ISU ReD Research Documents",
        industry_vertical=discoveryengine.IndustryVertical.GENERIC,
        solution_types=[discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH],
        content_config=discoveryengine.DataStore.ContentConfig.CONTENT_REQUIRED,
    )

    print(f"Creating data store '{DATA_STORE_ID}' …")
    try:
        operation = client.create_data_store(
            parent=f"{parent}/collections/{COLLECTION}",
            data_store=data_store,
            data_store_id=DATA_STORE_ID,
        )
        print("Waiting for data store creation …")
        result = operation.result(timeout=300)
        print(f"Data store created: {result.name}")
    except gcp_exceptions.AlreadyExists:
        print(f"Data store '{DATA_STORE_ID}' already exists.")

    # Import documents from GCS
    import_documents(project, location, bucket)


def import_documents(project: str, location: str, bucket: str) -> None:
    """Import PDF documents from GCS into the data store."""
    client = discoveryengine.DocumentServiceClient()
    ds_name = _data_store_name(project, location)

    # Import PDFs from the bucket
    gcs_source = discoveryengine.GcsSource(
        input_uris=[f"gs://{bucket}/pdfs/**"],
        data_schema="content",
    )

    import_config = discoveryengine.ImportDocumentsRequest(
        parent=f"{ds_name}/branches/default_branch",
        gcs_source=gcs_source,
        reconciliation_mode=discoveryengine.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
    )

    print(f"Importing documents from gs://{bucket}/pdfs/ …")
    print("  This will take a while for 16K+ documents.")
    try:
        operation = client.import_documents(request=import_config)
        print(f"Import operation started: {operation.operation.name}")
        print("  Check status with: python setup_vertex_search.py status")
    except gcp_exceptions.AlreadyExists:
        print("Documents already imported.")
    except Exception as exc:
        print(f"Import request submitted (may run async): {exc}")


# ---------------------------------------------------------------------------
# Search Engine (App)
# ---------------------------------------------------------------------------


def create_search_engine(project: str, location: str) -> None:
    """Create a Vertex AI Search engine (app) using the data store."""
    client = discoveryengine.EngineServiceClient()
    parent = f"{_parent(project, location)}/collections/{COLLECTION}"

    engine = discoveryengine.Engine(
        display_name="ISU ReD Search Engine",
        solution_type=discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH,
        search_engine_config=discoveryengine.Engine.SearchEngineConfig(
            search_tier=discoveryengine.SearchTier.SEARCH_TIER_ENTERPRISE,
            search_add_ons=[
                discoveryengine.SearchAddOn.SEARCH_ADD_ON_LLM,
            ],
        ),
        data_store_ids=[DATA_STORE_ID],
    )

    print(f"Creating search engine '{ENGINE_ID}' …")
    try:
        operation = client.create_engine(
            parent=parent,
            engine=engine,
            engine_id=ENGINE_ID,
        )
        print("Waiting for engine creation …")
        result = operation.result(timeout=300)
        print(f"Engine created: {result.name}")
    except gcp_exceptions.AlreadyExists:
        print(f"Engine '{ENGINE_ID}' already exists.")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search(project: str, location: str, query: str, page_size: int = 5) -> None:
    """Run a test search query against the Vertex AI Search engine."""
    client = discoveryengine.SearchServiceClient()
    serving_config = (
        f"{_engine_name(project, location)}"
        f"/servingConfigs/default_search"
    )

    request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=page_size,
        content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
            snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                return_snippet=True,
            ),
            summary_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                summary_result_count=3,
                include_citations=True,
            ),
            extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                max_extractive_answer_count=2,
            ),
        ),
    )

    print(f"\n🔍 Searching: \"{query}\"\n")
    print("─" * 60)

    response = client.search(request)

    # Print AI summary if available
    if hasattr(response, "summary") and response.summary and response.summary.summary_text:
        print("\n📋 AI Summary:")
        print(response.summary.summary_text)
        print("─" * 60)

    # Print individual results
    for i, result in enumerate(response.results, 1):
        doc = result.document
        title = doc.derived_struct_data.get("title", "Untitled") if doc.derived_struct_data else "Untitled"
        link = doc.derived_struct_data.get("link", "") if doc.derived_struct_data else ""

        print(f"\n  [{i}] {title}")
        if link:
            print(f"      {link}")

        # Snippets
        snippets = doc.derived_struct_data.get("snippets", []) if doc.derived_struct_data else []
        for snippet in snippets[:1]:
            text = snippet.get("snippet", "")
            if text:
                print(f"      …{text[:200]}…")

    total = response.total_size if hasattr(response, "total_size") else "?"
    print(f"\n  Total results: {total}")


# ---------------------------------------------------------------------------
# Grounded Generation (RAG)
# ---------------------------------------------------------------------------


def grounded_generate(project: str, location: str, query: str) -> None:
    """Use the Grounded Generation API for RAG over ISU ReD documents."""
    client = discoveryengine.GroundedGenerationServiceClient()

    serving_config = (
        f"{_parent(project, location)}"
        f"/groundingConfigs/default_grounding_config"
    )

    # Config pointing to our data store for grounding
    grounding_spec = discoveryengine.GenerateGroundedContentRequest.GroundingSpec(
        grounding_sources=[
            discoveryengine.GenerateGroundedContentRequest.GroundingSpec.GroundingSource(
                search_source=discoveryengine.GenerateGroundedContentRequest.GroundingSpec.GroundingSource.SearchSource(
                    serving_config=f"{_engine_name(project, location)}/servingConfigs/default_search",
                ),
            ),
        ],
    )

    request = discoveryengine.GenerateGroundedContentRequest(
        location=_parent(project, location),
        system_instruction=discoveryengine.GroundedGenerationContent(
            parts=[
                discoveryengine.GroundedGenerationContent.Part(
                    text=(
                        "You are a research assistant for Iowa State University's "
                        "ReD (Research and Demonstration Farm) repository. Answer "
                        "questions using only the grounded documents. Cite sources."
                    ),
                ),
            ],
        ),
        contents=[
            discoveryengine.GroundedGenerationContent(
                role="user",
                parts=[
                    discoveryengine.GroundedGenerationContent.Part(text=query),
                ],
            ),
        ],
        generation_spec=discoveryengine.GenerateGroundedContentRequest.GenerationSpec(
            model_id="gemini-2.0-flash",
        ),
        grounding_spec=grounding_spec,
    )

    print(f"\n🧠 Grounded Generation: \"{query}\"\n")
    print("─" * 60)

    try:
        response = client.generate_grounded_content(request)

        # Print generated answer
        for candidate in response.candidates:
            for part in candidate.content.parts:
                print(part.text)

            # Print grounding citations
            if candidate.grounding_metadata and candidate.grounding_metadata.support_chunks:
                print("\n📚 Sources:")
                seen = set()
                for chunk in candidate.grounding_metadata.support_chunks:
                    source = chunk.source or "Unknown"
                    if source not in seen:
                        seen.add(source)
                        print(f"  • {source}")
                        content = chunk.content[:150] if chunk.content else ""
                        if content:
                            print(f"    {content}…")

    except Exception as exc:
        print(f"Grounded generation error: {exc}")
        print("\nNote: Grounded Generation requires the search engine to be fully")
        print("provisioned and documents indexed. This may take several hours")
        print("after initial setup.")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def check_status(project: str, location: str) -> None:
    """Check the status of data store and engine."""
    print("Checking Vertex AI Search status …\n")

    # Data store
    try:
        ds_client = discoveryengine.DataStoreServiceClient()
        ds = ds_client.get_data_store(name=_data_store_name(project, location))
        print(f"Data Store: {ds.display_name}")
        print(f"  Name: {ds.name}")
        print(f"  Created: {ds.create_time}")
    except gcp_exceptions.NotFound:
        print(f"Data Store '{DATA_STORE_ID}' not found.")
    except Exception as exc:
        print(f"Data Store check failed: {exc}")

    print()

    # Engine
    try:
        eng_client = discoveryengine.EngineServiceClient()
        eng = eng_client.get_engine(name=_engine_name(project, location))
        print(f"Search Engine: {eng.display_name}")
        print(f"  Name: {eng.name}")
        print(f"  Created: {eng.create_time}")
    except gcp_exceptions.NotFound:
        print(f"Engine '{ENGINE_ID}' not found.")
    except Exception as exc:
        print(f"Engine check failed: {exc}")


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------


def show_cost_estimate() -> None:
    """Print cost breakdown for using Vertex AI Search with $1000 credit."""
    print(MONTHLY_ESTIMATE)
    print("Detailed pricing breakdown:\n")
    for service, info in COST_ESTIMATES.items():
        print(f"  {service}")
        print(f"    Rate:     {info['price']} {info['unit']}")
        print(f"    Estimate: {info['our_estimate']}")
        print()
    print("Pricing source: https://cloud.google.com/generative-ai-app-builder/pricing")
    print("Credit terms:   $1000 GenAI App Builder — covers all services above.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Set up and interact with Vertex AI Search for ISU ReD."
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help="GCP project ID (or set GOOGLE_CLOUD_PROJECT).",
    )
    parser.add_argument(
        "--location",
        default=DEFAULT_LOCATION,
        help=f"Vertex AI location (default: {DEFAULT_LOCATION}).",
    )
    parser.add_argument(
        "--bucket",
        default=DEFAULT_BUCKET,
        help=f"GCS bucket name (default: {DEFAULT_BUCKET}).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # setup
    sub_setup = sub.add_parser("setup", help="Create data store + search engine.")

    # search
    sub_search = sub.add_parser("search", help="Run a test search query.")
    sub_search.add_argument("query", help="Search query string.")
    sub_search.add_argument("--results", type=int, default=5, help="Number of results.")

    # generate
    sub_gen = sub.add_parser("generate", help="Grounded generation (RAG) query.")
    sub_gen.add_argument("query", help="Question to answer with grounded generation.")

    # status
    sub.add_parser("status", help="Check data store and engine status.")

    # cost
    sub.add_parser("cost", help="Show cost estimates for the $1000 credit.")

    args = parser.parse_args()

    if args.command == "cost":
        show_cost_estimate()
        return

    if not args.project:
        sys.exit(
            "GCP project not set. Use --project or set GOOGLE_CLOUD_PROJECT."
        )

    print(f"Project:  {args.project}")
    print(f"Location: {args.location}")
    print()

    if args.command == "setup":
        create_data_store(args.project, args.location, args.bucket)
        print()
        create_search_engine(args.project, args.location)
        print()
        print("✅ Setup complete.")
        print("   Documents will be indexed asynchronously (may take hours for 16K docs).")
        print("   Check status: python setup_vertex_search.py status")
        print("   Cost info:    python setup_vertex_search.py cost")

    elif args.command == "search":
        test_search(args.project, args.location, args.query, args.results)

    elif args.command == "generate":
        grounded_generate(args.project, args.location, args.query)

    elif args.command == "status":
        check_status(args.project, args.location)


if __name__ == "__main__":
    main()

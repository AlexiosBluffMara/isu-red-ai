# ISU ReD AI — Comprehensive Cost Analysis

> Generated: 2026-03-28 | Data: 16,356 PDFs (40GB), 13,613 extracted texts (273MB), 193,653 embeddings (2.5GB LanceDB)

---

## 1. OCR Processor Trade-Off Analysis

### What You Already Have (Free)
Your current pipeline uses **PyMuPDF text extraction → Gemini Flash fallback** for scanned PDFs. This already extracted 13,613 of 16,356 PDFs at **zero cost**.

### Option A: Document AI OCR ($1.50/1K pages, first 1K free/mo)

| Aspect | Detail |
|---|---|
| **Output** | Raw text, page-by-page |
| **Accuracy** | 99%+ for printed text, handles scanned docs natively |
| **Tables/Figures** | Extracts text but loses structural formatting |
| **Languages** | 200+ languages |
| **Estimated cost for full corpus** | ~200K pages × $1.50/1K = **$300 one-time** |

**Advantages over free approach:**
- Consistent quality across all PDF types (scanned, digital, mixed)
- Native handling of rotated/skewed text
- Confidence scores per word
- Supports batch processing via API

**Disadvantages:**
- Still just raw text — no structural awareness
- You already have 83% extracted via free methods
- $300 for marginal quality improvement on remaining 2,743 PDFs
- No auto-chunking — still need manual splitting for RAG

### Option B: Document AI Layout Parser ($10/1K pages)

| Aspect | Detail |
|---|---|
| **Output** | Structured document: headings, paragraphs, tables, lists, figures |
| **Auto-chunking** | Yes — semantically meaningful segments |
| **Table extraction** | Preserves row/column structure |
| **Figure detection** | Identifies and labels figure regions |
| **Estimated cost for full corpus** | ~200K pages × $10/1K = **$2,000 one-time** |

**Advantages:**
- Dramatically better RAG quality (chunks respect document boundaries)
- Table data preserved in structured format
- Heading hierarchy maintained → better metadata
- Figure captions linked to content

**Disadvantages:**
- 6.7× more expensive than OCR
- Exceeds your $1K credit on its own
- Overkill if papers are primarily flowing text (most academic papers are)

### Recommendation

| Scenario | Use |
|---|---|
| **Prototype/Demo** | Keep free approach (PyMuPDF + Gemini Flash). Already have 83% extracted. |
| **Production quality** | Document AI OCR for remaining 2,743 PDFs ($4.11 for those pages specifically) |
| **Enterprise with tables/data** | Layout Parser, but only for high-value subsets (e.g., STEM papers with data tables) |

**Bottom line:** The free OCR approach is fine. The $300 for Document AI OCR buys you marginal improvement. Layout Parser at $2K blows the budget for a feature most text-heavy academic papers don't need.

---

## 2. Element-by-Element GCP Cost Breakdown (with $1K Credit)

### What the $1K GenAI App Builder Credit Covers
Per Google's terms, this credit applies to: Vertex AI Search, Vertex AI Conversation, Grounded Generation API, and related GenAI App Builder services.

### Monthly Operating Costs (assuming 100 queries/day = 3,000/mo)

| Component | Service | Unit Price | Monthly Usage | Monthly Cost |
|---|---|---|---|---|
| **Search Index Storage** | Vertex AI Search | $5/GB/mo (10GB free) | 2.5GB | **$0** (free tier) |
| **Search Queries (Standard)** | Vertex AI Search | $1.50/1K queries | 3,000 queries | **$4.50** |
| **Search Queries (Enterprise)** | Vertex AI Search | $4.00/1K queries | 3,000 queries | **$12.00** |
| **Generated Answers** | Vertex AI Search Advanced | +$4.00/1K queries | 3,000 queries | +**$12.00** |
| **Gemini 2.5 Flash (RAG)** | Vertex AI | $0.30/M in, $2.50/M out | ~6M in, ~1.5M out | **$5.55** |
| **Gemini 2.5 Pro (RAG)** | Vertex AI | $1.25/M in, $10/M out | ~6M in, ~1.5M out | **$22.50** |
| **Gemini 3.1 Pro (RAG)** | Vertex AI | $2.00/M in, $12/M out | ~6M in, ~1.5M out | **$30.00** |
| **Embeddings** | Gemini Embedding | $0.00015/1K tokens | Already computed | **$0** |
| **Cloud Storage** | GCS Standard | $0.020/GB/mo | 40GB PDFs + 0.3GB text | **$0.81** |
| **Web Hosting** | Cloud Run | Free tier: 240K vCPU-sec | ~50K requests/mo | **$0** (free tier) |
| **Document AI OCR** | Document AI | $1.50/1K pages | One-time: 200K pages | **$300** (one-time) |

### Credit Burn Rate by Configuration

| Configuration | Monthly Cost | $1K Credit Duration |
|---|---|---|
| Standard Search + Gemini 2.5 Flash | ~$11/mo | **90+ months** |
| Enterprise Search + Gemini 2.5 Flash | ~$18/mo | **55 months** |
| Enterprise + Gen Answers + Gemini 2.5 Pro | ~$47/mo | **21 months** |
| Enterprise + Gen Answers + Gemini 3.1 Pro | ~$55/mo | **18 months** |
| Above + OCR (one-time) | $55/mo + $300 | **12 months** |

---

## 3. Cross-Cloud Comparison

### GCP vs AWS vs Azure — Feature Equivalents

| Feature | GCP | AWS | Azure |
|---|---|---|---|
| **Managed Search** | Vertex AI Search | Amazon Kendra | Azure AI Search |
| **LLM API** | Gemini 2.5/3.1 | Bedrock (Claude, Titan) | Azure OpenAI (GPT-4o) |
| **Embeddings** | Gemini Embedding | Titan Embeddings | text-embedding-3-large |
| **OCR/Document** | Document AI | Textract | Document Intelligence |
| **Object Storage** | GCS | S3 | Blob Storage |
| **Serverless Compute** | Cloud Run | Lambda + API Gateway | Container Apps |
| **Vector DB (managed)** | Vertex AI Vector Search | OpenSearch Serverless | Azure AI Search (built-in) |

### Monthly Cost Comparison (100 queries/day, 40GB corpus)

| Component | GCP | AWS | Azure |
|---|---|---|---|
| **Managed Search** | $4.50-24/mo (Vertex AI Search) | **$810/mo** (Kendra Developer) | $73/mo (AI Search Basic) |
| **LLM API** | $5.55/mo (Gemini 2.5 Flash) | $8-15/mo (Claude 3.5 Haiku) | $6-12/mo (GPT-4o mini) |
| **Embeddings** | $0 (already computed) | ~$2/mo (Titan Embed) | ~$1/mo (text-embedding-3) |
| **OCR (one-time)** | $300 (Document AI) | $300 (Textract) | $200 (Doc Intelligence) |
| **Storage** | $0.81/mo (GCS) | $0.92/mo (S3) | $0.73/mo (Blob) |
| **Compute** | $0 (Cloud Run free) | ~$5/mo (Lambda) | $0 (Container Apps free) |
| **Total Monthly** | **~$11-25/mo** | **~$826-833/mo** | **~$80-87/mo** |
| **Total Year 1** | **$432-600** | **$10,192-10,296** | **$1,160-1,244** |

### Verdict

| Cloud | Score | Why |
|---|---|---|
| **GCP** ⭐ | Best value | $1K credit covers 1-7 years. Vertex AI Search is 30-180× cheaper than Kendra. Native Gemini integration. |
| **Azure** | Runner-up | Azure AI Search Basic at $73/mo is reasonable. No credits though. Good GPT-4o integration. |
| **AWS** | Prohibitive | Kendra's $810/mo minimum makes it a non-starter for prototype/demo. Great for Fortune 500 budgets. |

---

## 4. Physical Hardware Comparison

### Option: Self-Hosted on Mac Mini

| Hardware | Price | RAM | Use Case |
|---|---|---|---|
| Mac Mini M4 (16GB) | $600 | 16GB | Small models (Llama 3.1 8B, Qwen 2.5 7B) |
| Mac Mini M4 Pro (24GB) | $1,400 | 24GB | Medium models (Mistral 24B, Llama 3.1 24B) |
| Mac Mini M4 Pro (48GB) | $1,800 | 48GB | Large models (Llama 3.1 70B 4-bit quant) |
| Mac Mini M4 Max (64GB) | $2,400 | 64GB | Full 70B models, multiple concurrent users |

### Software Stack (All Free/OSS)

| Component | Tool | Cost |
|---|---|---|
| LLM Runtime | Ollama / llama.cpp | Free |
| Vector DB | LanceDB (already have) | Free |
| Embeddings | nomic-embed-text (Ollama) | Free |
| Web Framework | FastAPI (already have) | Free |
| Reverse Proxy | Caddy / nginx | Free |
| OS | macOS (included) | Free |

### Total Cost of Ownership (3 Years)

| Approach | Year 1 | Year 2 | Year 3 | 3-Year Total |
|---|---|---|---|---|
| **GCP (Standard + Flash)** | $132 | $132 | $132 | **$396** |
| **GCP (Enterprise + Pro)** | $564 | $564 | $564 | **$1,692** |
| **Azure (Basic + GPT-4o mini)** | $1,152 | $960 | $960 | **$3,072** |
| **AWS (Kendra + Haiku)** | $10,200 | $9,960 | $9,960 | **$30,120** |
| **Mac Mini M4 Pro (48GB)** | $1,860 | $60 | $60 | **$1,980** |
| **Mac Mini M4 Max (64GB)** | $2,460 | $60 | $60 | **$2,580** |

*Hardware assumes $5/mo electricity. GCP Year 1 includes $1K credit offset.*

### Hardware Pros/Cons

| Pro | Con |
|---|---|
| Zero recurring costs after purchase | Single point of failure |
| Full data sovereignty | No autoscaling |
| No API rate limits | You maintain everything |
| Fastest iteration (no deploy cycle) | Slower inference than cloud GPUs |
| No vendor lock-in | Local models < Gemini 2.5 Pro quality |
| Tax deductible as business equipment | Need Tailscale/ngrok for public access |

---

## 5. Three Budget Tiers

### Tier 1: Bare Minimum Prototype — $0-30/mo

> **Goal:** Working demo for investor meetings. Runs on free tiers.

| Component | Choice | Cost |
|---|---|---|
| Search | LanceDB local (already have 193K embeddings) | $0 |
| LLM | Gemini 2.5 Flash free tier (15 RPM) | $0 |
| Frontend | GitHub Pages (already deployed) | $0 |
| Backend API | Cloud Run free tier | $0 |
| Storage | GCS 5GB free or serve from repo | $0 |
| Domain | GitHub Pages subdomain | $0 |
| **Monthly total** | | **$0** |
| **Credit burn** | | **$0/mo** |
| **Limitations** | 15 RPM rate limit, no enterprise search features, single region |

**What you get:** A working search + RAG demo with ISU branding, deployed on GitHub Pages + Cloud Run. Searches local LanceDB, generates answers with Gemini Flash. Good enough to show "this works" to investors.

### Tier 2: Fully Featured Enterprise — $100-200/mo

> **Goal:** Production-quality research assistant with all AI features.

| Component | Choice | Cost |
|---|---|---|
| Search | Vertex AI Search Enterprise | $12/mo (3K queries) |
| Generated Answers | Vertex AI Search Advanced | +$12/mo |
| LLM | Gemini 2.5 Pro | $22.50/mo |
| Grounding | Google Search grounding | ~$10/mo |
| OCR | Document AI OCR (one-time) | $300 one-time |
| Frontend | Cloud Run (custom domain) | $5/mo |
| Storage | GCS Standard (40GB) | $0.81/mo |
| Monitoring | Cloud Logging + Monitoring | $0 (free tier) |
| CDN | Cloud CDN | ~$5/mo |
| **Monthly total** | | **~$67/mo** (after one-time OCR) |
| **Credit burn** | | **$1K covers ~10 months + OCR** |

**What you get:** Full enterprise search with AI-generated answers, grounded citations, faceted filtering, document previews, analytics dashboard, custom domain, CDN, monitoring.

### Tier 3: Bleeding Edge (Gemini 3.1) — $300-500/mo

> **Goal:** State-of-the-art showcase. Every cutting-edge feature turned on.

| Component | Choice | Cost |
|---|---|---|
| Search | Vertex AI Search Advanced | $24/mo |
| LLM (primary) | Gemini 3.1 Pro | $30/mo |
| LLM (fast) | Gemini 3.1 Flash-Lite | $5/mo |
| Multi-modal | Gemini 3.1 Pro (PDF vision) | ~$50/mo |
| Grounding | Google Search + Vertex grounding | ~$20/mo |
| OCR | Document AI Layout Parser (one-time) | $2,000 one-time |
| Embeddings | Re-embed with latest model | ~$30 one-time |
| Frontend | Cloud Run + GPU instance | $150/mo |
| Storage | GCS Multi-region | $3/mo |
| CDN + WAF | Cloud Armor + CDN | $15/mo |
| Monitoring | Full observability suite | $10/mo |
| **Monthly total** | | **~$307/mo** (after one-time costs) |
| **One-time setup** | | **~$2,030** |
| **Credit burn** | | **$1K covers ~3 months** (need additional funding) |

**What you get:** Multi-modal document understanding (analyze figures, charts, diagrams directly), real-time grounded generation with live web sources, GPU-accelerated inference, advanced document chunking via Layout Parser, multi-region redundancy, enterprise security.

---

## 6. Recommendation for Investor Demo

**Start with Tier 1** (free prototype) to prove the concept, then pitch for funding to reach Tier 2. The $1K credit is more than enough for Tier 1 and covers ~10 months of Tier 2.

| Milestone | Tier | Monthly Cost | Cumulative Spend |
|---|---|---|---|
| MVP Demo (now) | Tier 1 | $0 | $0 |
| Post-funding (3 mo) | Tier 2 | $67 | $201 |
| Scale-up (6 mo) | Tier 2+ | $100 | $501 |
| Full production (12 mo) | Tier 3 | $307 | $2,345 |

# SPEC.md — Phase 3: Automated Evaluation Pipeline, Golden Dataset, and CI-Gated Quality Thresholds

---

## 1. Executive Summary

Phase 3 transforms the RAG system from a manually-tested pipeline into a measurably reliable, continuously validated production system. The objective is to establish an automated evaluation framework that quantifies retrieval and generation quality, catches regressions before they reach users, and provides the metrics infrastructure needed to confidently iterate on the pipeline.

Phase 1 built the ingestion backbone. Phase 2 graduated retrieval and generation to production quality with hybrid search, reranking, and citation enforcement. Phase 3 now answers the question every production AI system must address: **"How do we know it's still working correctly?"**

### Phase 3 Scope

- Golden dataset creation (manual curation + synthetic augmentation)
- Ragas evaluation pipeline for RAG-specific metrics (Faithfulness, Answer Relevancy, Context Precision, Context Recall)
- DeepEval integration for pytest-compatible CI/CD quality gates
- GitHub Actions workflow that blocks merges on quality regression
- Evaluation results storage and historical tracking
- Per-tenant evaluation support (evaluate against tenant-specific corpora)
- Citation coverage metric (custom: percentage of claims with citation anchors)

### Out of Scope (Deferred to Phase 4)

- AI SDK / Chat widget / Frontend delivery → Phase 4
- PDF viewer with bounding box overlays → Phase 4
- Multi-deployment architecture (API, widget, iframe) → Phase 4
- Production monitoring / online evaluation → Phase 4+
- A/B testing framework → Phase 4+

---

## 2. Architectural Goals

1. **Quantify Pipeline Quality Mathematically**: Replace anecdotal "it looks good" testing with numerical scores across faithfulness, relevancy, context precision, and context recall.
2. **Prevent Silent Degradation**: Any change to ingestion logic, chunking parameters, retrieval weights, prompt templates, or model selection triggers an evaluation run. Regressions are caught before merge.
3. **Separate Retrieval and Generation Failures**: Use component-level metrics to diagnose whether a bad answer is caused by poor retrieval (wrong chunks surfaced) or poor generation (LLM misused good chunks).
4. **Maintain Evaluation Dataset Quality**: The golden dataset is versioned, reviewed, and expanded over time. Synthetic generation supplements manual curation but never replaces human verification.
5. **Keep Evaluation Costs Predictable**: LLM-as-judge calls are the primary cost driver. Use `gpt-4o-mini` for evaluation where possible; reserve `gpt-4o` for faithfulness scoring where accuracy is critical.
6. **Build for Multi-Tenant Evaluation**: Support running evaluation suites against specific tenant corpora to validate per-domain performance.

---

## 3. Prerequisites from Phase 2

Phase 3 assumes the following Phase 2 deliverables are operational:

| Component                                | Status   | Notes                                                              |
|------------------------------------------|----------|--------------------------------------------------------------------|
| Hybrid retrieval (`match_documents_hybrid`) | Complete | Dense + Sparse + RRF fusion working                               |
| Cross-encoder reranking                  | Complete | Cohere rerank with local fallback                                  |
| Citation-enforced generation             | Complete | `[SOURCE_N]` anchors in LLM responses                             |
| Hallucination guardrails                 | Complete | Relevance threshold + prompt-based decline                         |
| Updated `/query` endpoint               | Complete | Full pipeline: embed → retrieve → rerank → generate → cite        |
| Streaming `/query/stream` endpoint       | Complete | SSE streaming with pre-sent sources                                |
| Prompt management (`/prompts`)           | Complete | Versioned prompts in DB + YAML fallback                            |
| Per-step latency tracking                | Complete | Response metadata includes latency breakdown                       |
| `fts` tsvector column + GIN index        | Complete | Sparse search operational                                          |
| `prompt_versions` table                  | Complete | Audit trail for prompt changes                                     |

---

## 4. Tech Stack Additions (Phase 3)

### 4.1 Evaluation Frameworks

| Component          | Technology              | Rationale                                                          |
|--------------------|-------------------------|--------------------------------------------------------------------|
| RAG Metrics        | Ragas `>=0.4.0`         | Industry standard for faithfulness, relevancy, context precision/recall; reference-free evaluation |
| CI Test Runner     | DeepEval `>=1.0.0`      | Pytest-compatible; pass/fail thresholds; designed for CI/CD gates   |
| Synthetic Data     | Ragas TestsetGenerator  | Knowledge-graph-based test generation from ingested documents       |

### 4.2 CI/CD

| Component          | Technology              | Rationale                                                          |
|--------------------|-------------------------|--------------------------------------------------------------------|
| CI Pipeline        | GitHub Actions           | Standard; integrates with pytest and DeepEval CLI                  |
| Test Framework     | pytest `>=7.0`           | DeepEval's native integration layer                                |

### 4.3 Storage & Tracking

| Component          | Technology              | Rationale                                                          |
|--------------------|-------------------------|--------------------------------------------------------------------|
| Eval Results DB    | Supabase PostgreSQL      | Same DB as the rest of the stack; relational storage for eval history |
| Dataset Storage    | JSON files (versioned)   | Golden datasets stored in repo; versioned with git                 |

### 4.4 New Dependencies

```
ragas>=0.4.0                    # RAG evaluation metrics + synthetic test generation
deepeval>=1.0.0                 # Pytest-compatible CI/CD evaluation framework
pandas>=2.0.0                   # Dataset manipulation and analysis
datasets>=2.14.0                # HuggingFace datasets for Ragas compatibility
nest-asyncio>=1.5.0             # Async support in notebook/CI environments
```

---

## 5. System Architecture (Phase 3 Evaluation Pipeline)

### 5.1 High-Level Evaluation Flow

```
┌────────────────────────────────────────────────────┐
│              Evaluation Trigger                      │
│  (Manual CLI / GitHub Actions on PR / Scheduled)     │
└──────────┬───────────────────────────────────────────┘
│
▼
┌──────────────────────┐
│  Load Golden Dataset  │  ← JSON file from eval/datasets/
│  (versioned, curated) │     Contains: query, reference_answer,
│                       │     reference_contexts, source_doc
└──────────┬───────────┘
│
▼
┌──────────────────────┐
│  Run RAG Pipeline     │  ← For each golden question:
│  (Phase 2 /query)     │     1. Embed query
│                       │     2. Hybrid retrieve
│                       │     3. Rerank
│                       │     4. Generate with citations
└──────────┬───────────┘
│
▼
┌──────────────────────┐
│  Collect Samples      │  ← For each question, capture:
│                       │     - user_input (query)
│                       │     - response (generated answer)
│                       │     - retrieved_contexts (chunk texts)
│                       │     - reference (ground truth answer)
└──────────┬───────────┘
│
▼
┌──────────────────────────────────────────────┐
│            Metric Computation                 │
│                                               │
│  ┌──────────────┐  ┌───────────────────────┐  │
│  │  Ragas Core   │  │  Custom Metrics        │  │
│  │  - Faithfulness│  │  - Citation Coverage   │  │
│  │  - Answer Rel. │  │  - Decline Accuracy    │  │
│  │  - Ctx Precision│ │  - Latency Compliance  │  │
│  │  - Ctx Recall  │  │                       │  │
│  └──────┬───────┘  └──────────┬────────────┘  │
│         └──────────┬──────────┘               │
└────────────────────┼──────────────────────────┘
│
▼
┌──────────────────────┐
│  Threshold Check      │  ← Compare scores against minimums
│  (Pass / Fail)        │     Fail → Block merge in CI
└──────────┬───────────┘
│
▼
┌──────────────────────────────────────────────┐
│            Results Handling                    │
│                                               │
│  ┌──────────────┐  ┌───────────────────────┐  │
│  │  Store in DB   │  │  Generate Report     │  │
│  │  (eval_runs    │  │  (JSON + Markdown    │  │
│  │   table)       │  │   summary)           │  │
│  └──────────────┘  └───────────────────────┘  │
└───────────────────────────────────────────────┘
```
### 5.2 Evaluation Modes

| Mode               | Trigger                          | Use Case                                                    |
|--------------------|----------------------------------|-------------------------------------------------------------|
| **CI Gate**        | GitHub Actions on PR             | Block merges when quality drops below thresholds            |
| **Manual Run**     | CLI command                      | Developer runs evaluation locally before pushing            |
| **Scheduled**      | Cron (weekly / daily)            | Detect drift from external changes (model updates, etc.)    |
| **Per-Tenant**     | API endpoint or CLI flag         | Validate quality for a specific tenant's corpus             |

---

## 6. Golden Dataset Specification

### 6.1 Dataset Structure

The golden dataset is a JSON file containing curated question-answer pairs with verified source grounding. Each entry represents a single evaluation scenario.

**Schema** (`eval/datasets/golden_v1.json`):

```json
{
  "version": "1.0.0",
  "created_at": "2026-04-14T00:00:00Z",
  "description": "Phase 3 golden dataset — domain-specific RAG evaluation",
  "tenant_id": "uuid-of-target-tenant",
  "samples": [
    {
      "id": "gs-001",
      "category": "exact_match",
      "difficulty": "easy",
      "user_input": "What is the liability cap in the Master Services Agreement?",
      "reference": "The liability cap shall not exceed $1,000,000 in aggregate for all claims arising under the agreement. This limitation applies to both direct and indirect damages.",
      "reference_contexts": [
        "The liability cap shall not exceed $1,000,000 in aggregate for all claims arising under this agreement. This limitation applies to both direct and indirect damages..."
      ],
      "source_document": "contract.pdf",
      "source_page": 5,
      "tags": ["legal", "liability", "exact_value"]
    },
    {
      "id": "gs-002",
      "category": "unanswerable",
      "difficulty": "hard",
      "user_input": "What is the CEO's favourite colour?",
      "reference": "DECLINE: This information is not present in the available documents.",
      "reference_contexts": [],
      "source_document": null,
      "source_page": null,
      "tags": ["unanswerable", "hallucination_test"]
    },
    {
      "id": "gs-003",
      "category": "multi_context",
      "difficulty": "medium",
      "user_input": "How do the termination clauses differ between the MSA and the NDA?",
      "reference": "The MSA allows termination with 30 days written notice, while the NDA requires 60 days notice and mutual consent...",
      "reference_contexts": [
        "Either party may terminate this MSA with 30 days written notice...",
        "Termination of this NDA requires 60 days notice and written mutual consent..."
      ],
      "source_document": "multiple",
      "source_page": null,
      "tags": ["multi_document", "comparison", "legal"]
    }
  ]
}
```

### 6.2 Dataset Categories

Every golden dataset should include samples across these categories to ensure comprehensive coverage:

| Category           | Description                                                      | Target % | Min Samples |
|--------------------|------------------------------------------------------------------|----------|-------------|
| `exact_match`      | Questions with precise, factual answers (numbers, names, dates)  | 30%      | 15          |
| `conceptual`       | Questions requiring synthesis of a concept from context          | 25%      | 12          |
| `multi_context`    | Questions requiring information from multiple chunks/documents   | 15%      | 8           |
| `unanswerable`     | Questions where the answer is NOT in the knowledge base          | 15%      | 8           |
| `reasoning`        | Questions requiring inference or logical deduction from context  | 10%      | 5           |
| `adversarial`      | Prompt injection attempts, edge cases, ambiguous queries         | 5%       | 3           |

**Minimum viable golden dataset: 50 samples. Target: 100-200 samples.**

### 6.3 Dataset Creation Workflow

**Step 1: Manual Curation (Primary — 60% of dataset)**

Domain experts review ingested documents and create question-answer pairs:

1. Select a representative document from the tenant's corpus.
2. Read a section and formulate a question a real user would ask.
3. Write the reference answer based solely on the document content.
4. Copy the exact context passage(s) that support the answer.
5. Record the source document and page number.
6. Assign a category and difficulty level.
7. Include unanswerable questions (answers NOT in the documents).

**Step 2: Synthetic Augmentation (Secondary — 40% of dataset)**

Use Ragas' `TestsetGenerator` to generate additional samples from the ingested documents, then **human-review every synthetic sample** before including it in the golden dataset.

```python
from ragas.testset import TestsetGenerator
from ragas.testset.graph import KnowledgeGraph, Node, NodeType
from ragas.testset.transforms import default_transforms, apply_transforms
from ragas.testset.synthesizers import default_query_distribution
from ragas.llms import llm_factory
from openai import OpenAI

# Initialize LLM and embeddings for generation
client = OpenAI()
generator_llm = llm_factory("gpt-4o", client=client)

# Build knowledge graph from ingested chunks
kg = KnowledgeGraph()
for chunk in ingested_chunks:
    kg.nodes.append(
        Node(
            type=NodeType.DOCUMENT,
            properties={
                "page_content": chunk["content"],
                "document_metadata": chunk["metadata"],
            }
        )
    )

# Enrich the knowledge graph with transformations
trans = default_transforms(
    documents=docs,
    llm=generator_llm,
    embedding_model=generator_embeddings
)
apply_transforms(kg, trans)

# Save knowledge graph for reuse
kg.save("eval/knowledge_graph.json")

# Generate synthetic test set
generator = TestsetGenerator(
    llm=generator_llm,
    embedding_model=generator_embeddings,
    knowledge_graph=kg
)

query_distribution = default_query_distribution(generator_llm)
# Default: 50% specific, 25% abstract, 25% comparative

testset = generator.generate(testset_size=50, query_distribution=query_distribution)

# Export for human review
df = testset.to_pandas()
df.to_json("eval/datasets/synthetic_for_review.json", orient="records", indent=2)
```

**Step 3: Human Review of Synthetic Samples**

Every synthetic sample must be reviewed before inclusion:

- Verify the reference answer is factually correct against the source.
- Confirm the reference_contexts actually support the answer.
- Discard samples with fabricated or hallucinated content.
- Assign appropriate category and difficulty labels.
- Expect to discard 20-40% of synthetic samples.

### 6.4 Dataset Versioning

Golden datasets are versioned using semantic versioning and stored in the repository:

```
eval/
├── datasets/
│   ├── golden_v1.0.0.json       # Initial curated dataset
│   ├── golden_v1.1.0.json       # Added 20 synthetic samples (reviewed)
│   ├── golden_v1.2.0.json       # Added adversarial edge cases
│   └── CHANGELOG.md             # Documents all dataset changes
```

**Version bumping rules**:
- **Patch** (1.0.x): Fix incorrect reference answers or metadata.
- **Minor** (1.x.0): Add new samples without removing existing ones.
- **Major** (x.0.0): Restructure categories, remove samples, or change schema.

**Critical**: Never compare evaluation scores across different dataset versions. If the dataset changes, previous scores are invalidated. Always record the dataset version alongside evaluation results.

---

## 7. Evaluation Metrics — Detailed Specification

### 7.1 Core RAG Metrics (via Ragas)

| Metric               | What It Measures                                              | Required Inputs                       | Score Range | Phase 3 Threshold |
|----------------------|---------------------------------------------------------------|---------------------------------------|-------------|-------------------|
| **Faithfulness**      | Are claims in the answer supported by retrieved context?      | `response`, `retrieved_contexts`      | 0.0 - 1.0   | ≥ 0.85            |
| **Answer Relevancy**  | Does the answer actually address the user's question?         | `user_input`, `response`              | 0.0 - 1.0   | ≥ 0.80            |
| **Context Precision** | Are the top-ranked retrieved chunks actually relevant?        | `user_input`, `retrieved_contexts`, `reference` | 0.0 - 1.0 | ≥ 0.75  |
| **Context Recall**    | Was all relevant information from the KB retrieved?           | `retrieved_contexts`, `reference`     | 0.0 - 1.0   | ≥ 0.75            |

**How each metric works**:

**Faithfulness**: The LLM judge extracts individual claims from the generated answer, then checks whether each claim is entailed by the retrieved context. The score is the ratio of supported claims to total claims. This is the primary hallucination defense metric.

**Answer Relevancy**: The LLM judge generates N hypothetical questions that the answer would address, then measures cosine similarity between these questions and the original query. A high score means the answer is on-topic.

**Context Precision**: Measures whether the retrieved chunks that are relevant to answering the question are ranked higher than irrelevant ones. High precision means the reranker is doing its job well.

**Context Recall**: Checks whether the retrieved context contains all the information needed to produce the reference answer. Low recall indicates the retrieval stage is missing relevant chunks.

### 7.2 Custom Metrics

| Metric                 | What It Measures                                          | Score Range | Threshold |
|------------------------|-----------------------------------------------------------|-------------|-----------|
| **Citation Coverage**   | % of factual claims with `[SOURCE_N]` citation anchors    | 0.0 - 1.0  | ≥ 0.90    |
| **Decline Accuracy**    | Does the system decline when it should (unanswerable Qs)? | 0.0 - 1.0  | ≥ 0.80    |
| **Latency Compliance**  | % of queries completing within 5s total latency           | 0.0 - 1.0  | ≥ 0.90    |

**Citation Coverage Implementation**:

```python
import re

def citation_coverage_score(response: str, num_claims: int | None = None) -> float:
    """
    Measure the proportion of the response that includes citation anchors.
    
    Simple heuristic: count sentences with citations vs. total factual sentences.
    """
    sentences = [s.strip() for s in re.split(r'[.!?]+', response) if s.strip()]
    if not sentences:
        return 0.0
    
    # Filter to factual sentences (exclude meta-statements, greetings, etc.)
    factual_sentences = [
        s for s in sentences 
        if len(s.split()) > 5  # Heuristic: factual sentences tend to be longer
        and not s.lower().startswith(("i don't have", "the following sources"))
    ]
    
    if not factual_sentences:
        return 1.0  # No factual claims = nothing to cite (e.g., decline responses)
    
    cited_sentences = [
        s for s in factual_sentences 
        if re.search(r'\[SOURCE_\d+\]', s)
    ]
    
    return len(cited_sentences) / len(factual_sentences)
```

**Decline Accuracy Implementation**:

```python
def decline_accuracy_score(
    response: str,
    is_unanswerable: bool
) -> float:
    """
    Check if the system correctly declines unanswerable questions
    and correctly answers answerable ones.
    """
    decline_phrases = [
        "i don't have enough information",
        "not present in the available documents",
        "cannot find",
        "no relevant documents",
    ]
    
    response_is_decline = any(
        phrase in response.lower() for phrase in decline_phrases
    )
    
    # Correct if: unanswerable AND declined, or answerable AND didn't decline
    if is_unanswerable == response_is_decline:
        return 1.0
    return 0.0
```

### 7.3 Metric Computation Implementation (Ragas)

```python
from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
from ragas.metrics import (
    Faithfulness,
    ResponseRelevancy,
    LLMContextPrecisionWithReference,
    LLMContextRecallWithReference,
)
from ragas.llms import llm_factory
from ragas import evaluate
from openai import AsyncOpenAI

# Initialize evaluator LLM
client = AsyncOpenAI()
evaluator_llm = llm_factory("gpt-4o-mini", client=client)

# Define metrics
metrics = [
    Faithfulness(llm=evaluator_llm),
    ResponseRelevancy(llm=evaluator_llm),
    LLMContextPrecisionWithReference(llm=evaluator_llm),
    LLMContextRecallWithReference(llm=evaluator_llm),
]

async def evaluate_single_sample(
    user_input: str,
    response: str,
    retrieved_contexts: list[str],
    reference: str,
) -> dict[str, float]:
    """Evaluate a single sample against all Ragas metrics."""
    sample = SingleTurnSample(
        user_input=user_input,
        response=response,
        retrieved_contexts=retrieved_contexts,
        reference=reference,
    )
    
    scores = {}
    for metric in metrics:
        try:
            score = await metric.single_turn_ascore(sample)
            scores[metric.name] = float(score) if score is not None else None
        except Exception as e:
            # Guard against NaN / invalid JSON from LLM judge
            scores[metric.name] = None
            logger.warning(f"Metric {metric.name} failed: {e}")
    
    return scores


async def evaluate_golden_dataset(dataset_path: str, tenant_id: str) -> dict:
    """Run full evaluation against a golden dataset."""
    golden = load_golden_dataset(dataset_path)
    
    all_scores = []
    for sample in golden["samples"]:
        # Run the RAG pipeline to get actual response + retrieved contexts
        pipeline_result = await run_query_pipeline(
            query=sample["user_input"],
            tenant_id=tenant_id,
        )
        
        # Compute Ragas metrics
        scores = await evaluate_single_sample(
            user_input=sample["user_input"],
            response=pipeline_result["answer"],
            retrieved_contexts=[c["content"] for c in pipeline_result["citations"]],
            reference=sample["reference"],
        )
        
        # Compute custom metrics
        scores["citation_coverage"] = citation_coverage_score(
            pipeline_result["answer"]
        )
        scores["decline_accuracy"] = decline_accuracy_score(
            pipeline_result["answer"],
            is_unanswerable=(sample["category"] == "unanswerable"),
        )
        scores["latency_compliant"] = (
            1.0 if pipeline_result["retrieval_metadata"]["latency_ms"]["total"] < 5000
            else 0.0
        )
        
        all_scores.append({
            "sample_id": sample["id"],
            "category": sample["category"],
            "scores": scores,
        })
    
    # Aggregate
    return aggregate_scores(all_scores)
```

---

## 8. Database Schema Extensions

### 8.1 Evaluation Runs Table

```sql
-- =============================================================
-- Phase 3: Evaluation pipeline schema
-- =============================================================

-- Table: eval_runs
-- Purpose: Track each evaluation run with aggregate scores
CREATE TABLE eval_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  dataset_version TEXT NOT NULL,          -- e.g., "golden_v1.0.0"
  trigger TEXT NOT NULL,                  -- "ci" | "manual" | "scheduled"
  git_sha TEXT,                           -- Commit hash that triggered the eval
  git_branch TEXT,                        -- Branch name
  status TEXT NOT NULL DEFAULT 'running', -- running | completed | failed
  
  -- Aggregate scores
  faithfulness_avg FLOAT,
  answer_relevancy_avg FLOAT,
  context_precision_avg FLOAT,
  context_recall_avg FLOAT,
  citation_coverage_avg FLOAT,
  decline_accuracy_avg FLOAT,
  latency_compliance_avg FLOAT,
  
  -- Thresholds used
  thresholds JSONB NOT NULL DEFAULT '{}',
  -- {"faithfulness": 0.85, "answer_relevancy": 0.80, ...}
  
  -- Pass/fail
  passed BOOLEAN,
  failure_reasons JSONB DEFAULT '[]',
  -- [{"metric": "faithfulness", "score": 0.78, "threshold": 0.85}]
  
  -- Metadata
  total_samples INTEGER DEFAULT 0,
  failed_samples INTEGER DEFAULT 0,
  eval_model TEXT,                        -- LLM used as judge
  total_eval_cost_usd FLOAT,             -- Estimated evaluation cost
  duration_seconds FLOAT,
  
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Table: eval_sample_results
-- Purpose: Per-sample detailed scores for debugging
CREATE TABLE eval_sample_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  eval_run_id UUID NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
  sample_id TEXT NOT NULL,                -- Golden dataset sample ID
  category TEXT,
  
  -- Pipeline outputs
  user_input TEXT NOT NULL,
  response TEXT NOT NULL,
  retrieved_contexts JSONB NOT NULL,      -- Array of chunk texts
  reference TEXT,
  
  -- Scores
  faithfulness FLOAT,
  answer_relevancy FLOAT,
  context_precision FLOAT,
  context_recall FLOAT,
  citation_coverage FLOAT,
  decline_accuracy FLOAT,
  latency_ms FLOAT,
  
  -- Debug metadata
  num_chunks_retrieved INTEGER,
  top_rerank_score FLOAT,
  model_used TEXT,
  prompt_version TEXT,
  
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_eval_runs_tenant
  ON eval_runs (tenant_id, created_at DESC);

CREATE INDEX idx_eval_runs_git
  ON eval_runs (git_sha);

CREATE INDEX idx_eval_sample_results_run
  ON eval_sample_results (eval_run_id);

-- RLS
ALTER TABLE eval_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE eval_sample_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tenant_isolation_eval_runs" ON eval_runs
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

CREATE POLICY "tenant_isolation_eval_samples" ON eval_sample_results
  FOR SELECT
  USING (
    eval_run_id IN (
      SELECT id FROM eval_runs
      WHERE tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
    )
  );
```

---

## 9. DeepEval CI/CD Integration

### 9.1 Test File Structure

DeepEval provides pytest-compatible test execution with pass/fail thresholds. This is the primary mechanism for CI quality gates.

```python
# tests/test_rag_evaluation.py

import pytest
import json
import asyncio
from deepeval import assert_test
from deepeval.metrics import (
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
)
from deepeval.test_case import LLMTestCase
from deepeval.dataset import EvaluationDataset

from app.pipeline.orchestrator import run_query_pipeline


def load_golden_dataset(path: str = "eval/datasets/golden_v1.0.0.json"):
    """Load golden dataset and convert to DeepEval format."""
    with open(path) as f:
        golden = json.load(f)
    return golden["samples"]


def run_pipeline_sync(query: str, tenant_id: str) -> dict:
    """Synchronous wrapper for the async query pipeline."""
    return asyncio.run(run_query_pipeline(query=query, tenant_id=tenant_id))


# Load golden dataset
golden_samples = load_golden_dataset()

# Build test cases by running pipeline on each golden sample
test_cases = []
for sample in golden_samples:
    result = run_pipeline_sync(
        query=sample["user_input"],
        tenant_id=sample.get("tenant_id", "default-tenant-id"),
    )
    
    test_cases.append(
        LLMTestCase(
            input=sample["user_input"],
            actual_output=result["answer"],
            expected_output=sample["reference"],
            retrieval_context=[c["content"] for c in result["citations"]],
        )
    )

dataset = EvaluationDataset(test_cases=test_cases)


@pytest.mark.parametrize("test_case", dataset)
def test_rag_faithfulness(test_case: LLMTestCase):
    metric = FaithfulnessMetric(threshold=0.85)
    assert_test(test_case, [metric])


@pytest.mark.parametrize("test_case", dataset)
def test_rag_answer_relevancy(test_case: LLMTestCase):
    metric = AnswerRelevancyMetric(threshold=0.80)
    assert_test(test_case, [metric])


@pytest.mark.parametrize("test_case", dataset)
def test_rag_context_precision(test_case: LLMTestCase):
    metric = ContextualPrecisionMetric(threshold=0.75)
    assert_test(test_case, [metric])


@pytest.mark.parametrize("test_case", dataset)
def test_rag_context_recall(test_case: LLMTestCase):
    metric = ContextualRecallMetric(threshold=0.75)
    assert_test(test_case, [metric])
```

### 9.2 GitHub Actions Workflow

```yaml
# .github/workflows/rag-evaluation.yml
name: RAG Quality Gate

on:
  pull_request:
    branches: [main]
    paths:
      - 'app/pipeline/**'
      - 'prompts/**'
      - 'sql/**'
      - 'eval/**'
      - 'tests/test_rag_evaluation.py'

  # Allow manual triggering
  workflow_dispatch:
    inputs:
      dataset_version:
        description: 'Golden dataset version (e.g., golden_v1.0.0)'
        required: false
        default: 'golden_v1.0.0'

  # Weekly scheduled run to detect drift
  schedule:
    - cron: '0 6 * * 1'  # Every Monday at 6 AM UTC

jobs:
  evaluate:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    services:
      # If tests need a local Supabase instance
      postgres:
        image: supabase/postgres:15.1.0.117
        env:
          POSTGRES_PASSWORD: postgres
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python 3.10
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Cache pip dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install deepeval>=1.0.0

      - name: Run RAG evaluation suite
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          COHERE_API_KEY: ${{ secrets.COHERE_API_KEY }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          EVAL_DATASET: ${{ github.event.inputs.dataset_version || 'golden_v1.0.0' }}
        run: |
          deepeval test run tests/test_rag_evaluation.py --verbose

      - name: Upload evaluation report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: eval-report-${{ github.sha }}
          path: eval/reports/

      - name: Store results in database
        if: always()
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        run: |
          python eval/scripts/store_results.py \
            --git-sha ${{ github.sha }} \
            --git-branch ${{ github.head_ref || github.ref_name }} \
            --trigger ci
```

### 9.3 Threshold Configuration

Thresholds are stored in a configuration file that can be adjusted without code changes:

```yaml
# eval/config/thresholds.yaml
version: "1.0.0"

# Core Ragas metrics
faithfulness:
  threshold: 0.85
  blocking: true          # Fails CI if below threshold
  
answer_relevancy:
  threshold: 0.80
  blocking: true
  
context_precision:
  threshold: 0.75
  blocking: true
  
context_recall:
  threshold: 0.75
  blocking: false         # Warning only — non-blocking initially

# Custom metrics
citation_coverage:
  threshold: 0.90
  blocking: true
  
decline_accuracy:
  threshold: 0.80
  blocking: true
  
latency_compliance:
  threshold: 0.90
  blocking: false         # Warning only

# Aggregate rules
min_passing_rate: 0.80    # At least 80% of samples must pass all blocking metrics
```

---

## 10. API Design (Phase 3)

### 10.1 New Endpoints

#### `POST /eval/run` (New)

Trigger an evaluation run for a tenant.

**Headers**:
- `Authorization: Bearer <jwt_token>`

**Body**:
```json
{
  "dataset_version": "golden_v1.0.0",
  "tenant_id": "uuid",
  "trigger": "manual"
}
```

**Response** (`202 Accepted`):
```json
{
  "eval_run_id": "uuid",
  "status": "running",
  "message": "Evaluation pipeline started"
}
```

#### `GET /eval/runs` (New)

List evaluation runs for a tenant with scores.

**Response** (`200 OK`):
```json
{
  "runs": [
    {
      "id": "uuid",
      "dataset_version": "golden_v1.0.0",
      "trigger": "ci",
      "git_sha": "abc123",
      "status": "completed",
      "passed": true,
      "scores": {
        "faithfulness_avg": 0.91,
        "answer_relevancy_avg": 0.87,
        "context_precision_avg": 0.82,
        "context_recall_avg": 0.79,
        "citation_coverage_avg": 0.94,
        "decline_accuracy_avg": 0.88
      },
      "total_samples": 50,
      "failed_samples": 3,
      "created_at": "2026-04-14T10:00:00Z"
    }
  ]
}
```

#### `GET /eval/runs/{run_id}/samples` (New)

Get per-sample results for debugging failures.

**Response** (`200 OK`):
```json
{
  "samples": [
    {
      "sample_id": "gs-001",
      "category": "exact_match",
      "user_input": "What is the liability cap?",
      "response": "The liability cap is...",
      "scores": {
        "faithfulness": 0.95,
        "answer_relevancy": 0.92,
        "context_precision": 0.88,
        "context_recall": 1.0,
        "citation_coverage": 1.0
      },
      "passed": true
    },
    {
      "sample_id": "gs-015",
      "category": "multi_context",
      "user_input": "How do termination clauses differ?",
      "response": "...",
      "scores": {
        "faithfulness": 0.60,
        "answer_relevancy": 0.75,
        "context_precision": 0.50,
        "context_recall": 0.40,
        "citation_coverage": 0.80
      },
      "passed": false,
      "failure_reasons": ["faithfulness below 0.85", "context_precision below 0.75"]
    }
  ]
}
```

### 10.2 CLI Commands

```bash
# Run evaluation locally
python -m eval.run --dataset golden_v1.0.0 --tenant-id <uuid>

# Generate synthetic test data
python -m eval.generate --tenant-id <uuid> --size 50 --output eval/datasets/synthetic_draft.json

# View evaluation history
python -m eval.history --tenant-id <uuid> --last 10

# Compare two evaluation runs
python -m eval.compare --run-a <uuid> --run-b <uuid>
```

---

## 11. Project Structure (Phase 3 Additions)

```
rag-ingestion/
├── app/
│   ├── api/
│   │   └── eval.py                    # NEW: /eval/* endpoints
│   └── ...
├── eval/
│   ├── init.py
│   ├── run.py                         # NEW: Main evaluation runner
│   ├── generate.py                    # NEW: Synthetic test data generation
│   ├── history.py                     # NEW: Eval history viewer
│   ├── compare.py                     # NEW: Run comparison tool
│   ├── metrics/
│   │   ├── init.py
│   │   ├── citation_coverage.py       # NEW: Custom citation metric
│   │   ├── decline_accuracy.py        # NEW: Custom decline metric
│   │   └── latency_compliance.py      # NEW: Custom latency metric
│   ├── config/
│   │   └── thresholds.yaml            # NEW: Threshold configuration
│   ├── datasets/
│   │   ├── golden_v1.0.0.json         # NEW: Initial golden dataset
│   │   └── CHANGELOG.md              # NEW: Dataset version history
│   ├── scripts/
│   │   └── store_results.py           # NEW: Store eval results in Supabase
│   └── reports/                       # NEW: Generated evaluation reports (gitignored)
├── sql/
│   ├── schema.sql                     # Phase 1
│   ├── phase2_migration.sql           # Phase 2
│   └── phase3_migration.sql           # NEW: eval_runs, eval_sample_results
├── tests/
│   ├── test_rag_evaluation.py         # NEW: DeepEval CI test suite
│   └── test_custom_metrics.py         # NEW: Unit tests for custom metrics
├── .github/
│   └── workflows/
│       └── rag-evaluation.yml         # NEW: GitHub Actions workflow
└── ...
```

---

## 12. Environment Variables (Phase 3 Additions)

```env
# --- Phase 1 + Phase 2 variables remain unchanged ---

# Evaluation
EVAL_DATASET_PATH=eval/datasets/golden_v1.0.0.json
EVAL_LLM_JUDGE=gpt-4o-mini           # LLM used for metric evaluation
EVAL_FAITHFULNESS_LLM=gpt-4o         # Use stronger model for faithfulness
EVAL_TIMEOUT_SECONDS=300              # Max time per evaluation run
RAGAS_DO_NOT_TRACK=true               # Opt out of Ragas telemetry

# Thresholds (can also be set in thresholds.yaml)
EVAL_THRESHOLD_FAITHFULNESS=0.85
EVAL_THRESHOLD_ANSWER_RELEVANCY=0.80
EVAL_THRESHOLD_CONTEXT_PRECISION=0.75
EVAL_THRESHOLD_CONTEXT_RECALL=0.75
EVAL_THRESHOLD_CITATION_COVERAGE=0.90
```

---

## 13. Engineering Considerations

### 13.1 Cost Management

Evaluation is expensive because every metric computation involves one or more LLM-as-judge calls.

| Component                        | Cost per Eval Run (50 samples) | Notes                           |
|----------------------------------|--------------------------------|----------------------------------|
| RAG pipeline execution (50 queries) | ~$0.60-1.60                | 50 × $0.012-0.032 per query     |
| Faithfulness scoring             | ~$0.50-1.00                    | Multiple claims per sample       |
| Answer Relevancy scoring         | ~$0.25-0.50                    | N question generations per sample |
| Context Precision scoring        | ~$0.15-0.30                    | One LLM call per sample          |
| Context Recall scoring           | ~$0.15-0.30                    | One LLM call per sample          |
| **Total per run (gpt-4o-mini judge)** | **~$1.65-3.70**          |                                  |
| **Total per run (gpt-4o judge)**  | **~$5.00-12.00**              | Use sparingly                    |

**Cost mitigation strategies**:
- Use `gpt-4o-mini` as the default judge; `gpt-4o` only for faithfulness.
- Cache pipeline results during evaluation so re-runs don't re-execute queries.
- Run full evaluation only on PRs that touch pipeline/prompt code (path filters in GitHub Actions).
- Scheduled weekly runs can use a smaller subset (20 samples) to detect drift cheaply.

### 13.2 Reliability

- **NaN Score Handling**: Ragas can return NaN when the LLM judge produces invalid JSON. Pin Ragas version, wrap metric calls in try/except, and log failures. A sample with a NaN score should be counted as a failure, not skipped.
- **Rate Limiting**: With 50 samples × 4 metrics, evaluation generates ~200 LLM calls. Use async with concurrency limits (max 5 parallel) and exponential backoff.
- **Determinism**: LLM-as-judge is inherently non-deterministic. Expect ±2-3% score variance between identical runs. Set thresholds with this margin in mind.
- **Timeout Protection**: Set a 5-minute timeout for the entire evaluation run. If exceeded, report partial results and mark the run as `failed`.

### 13.3 Observability

- **Per-Sample Drill-Down**: Store every sample's scores in `eval_sample_results` so failed runs can be debugged at the individual question level.
- **Score Trends**: Track aggregate scores over time per tenant to detect gradual drift.
- **Category Breakdown**: Report scores segmented by category (exact_match, conceptual, unanswerable, etc.) to identify systematic weaknesses.
- **Failure Distribution**: Track which categories fail most often to guide dataset expansion.

### 13.4 Known Limitations

- **LLM-as-judge bias**: The evaluation LLM may have systematic biases. Periodically validate metric scores against human judgments.
- **Reference answer quality**: Evaluation is only as good as the golden dataset. Bad reference answers produce misleading scores.
- **Cost at scale**: Multi-tenant evaluation (running against every tenant's corpus) can be expensive. Consider sampling strategies for large tenant counts.
- **Latency variance**: Network conditions and API response times introduce noise into latency metrics. Use percentile-based thresholds (P95) rather than averages for production monitoring.

---

## 14. Deliverables (Phase 3 Completion Criteria)

| #  | Deliverable                                        | Acceptance Criteria                                                                    |
|----|----------------------------------------------------|----------------------------------------------------------------------------------------|
| 1  | Golden dataset (v1.0.0)                            | ≥50 curated samples across all 6 categories; stored in versioned JSON                  |
| 2  | Synthetic test generation pipeline                 | Ragas TestsetGenerator produces samples from ingested docs; human review workflow documented |
| 3  | Ragas evaluation pipeline                          | Computes Faithfulness, Answer Relevancy, Context Precision, Context Recall per sample   |
| 4  | Custom metrics                                     | Citation Coverage, Decline Accuracy, Latency Compliance implemented and tested          |
| 5  | DeepEval test suite                                | `test_rag_evaluation.py` runs with pass/fail thresholds via `deepeval test run`         |
| 6  | GitHub Actions CI workflow                         | PRs touching pipeline/prompt code trigger evaluation; merge blocked on failure          |
| 7  | Evaluation storage schema                          | `eval_runs` and `eval_sample_results` tables deployed with RLS                         |
| 8  | Evaluation API endpoints                           | `/eval/run`, `/eval/runs`, `/eval/runs/{id}/samples` operational                       |
| 9  | CLI tools                                          | `eval.run`, `eval.generate`, `eval.history`, `eval.compare` commands working           |
| 10 | Score tracking and comparison                      | Historical scores queryable; run comparison shows score deltas                          |
| 11 | Documentation                                      | Dataset creation guide, evaluation workflow, threshold tuning guide                     |

---

## 15. Migration Checklist

Steps to add Phase 3 to a running Phase 2 deployment:

1. Run `sql/phase3_migration.sql` to create `eval_runs` and `eval_sample_results` tables with indexes and RLS.
2. Install new Python dependencies (`ragas`, `deepeval`, `pandas`, `datasets`, `nest-asyncio`).
3. Create the `eval/` directory structure with initial golden dataset.
4. Create the `eval/config/thresholds.yaml` configuration file.
5. Add Phase 3 environment variables (eval LLM judge, thresholds, Ragas telemetry opt-out).
6. Add `tests/test_rag_evaluation.py` with DeepEval test cases.
7. Add `.github/workflows/rag-evaluation.yml` with path filters.
8. Store API keys (`OPENAI_API_KEY`, `COHERE_API_KEY`, `SUPABASE_*`) as GitHub Actions secrets.
9. Run the evaluation manually once to establish a baseline score.
10. Verify: Push a PR that modifies a prompt template → GitHub Actions triggers eval → results stored in DB.

---

## 16. Phase 4 Preview (Next Steps)

Phase 4 will build on the evaluated, quality-gated pipeline by introducing:

1. **AI SDK with Embeddable Chat Widget**: A lightweight JavaScript bundle that drops into any HTML page, connected to the RAG query pipeline via SSE streaming.
2. **PDF Viewer with Bounding Box Overlays**: When a user clicks a citation, the SDK opens a PDF viewer at the exact page and highlights the source text using bounding box coordinates from Phase 1 metadata.
3. **Multi-Deployment Architecture**: Support for Direct API Integration, Embeddable Widget, and Iframe Deployment.
4. **Next.js Frontend + Vercel AI SDK**: Production dashboard for managing knowledge bases, viewing usage analytics, and monitoring evaluation scores.
5. **Production Monitoring**: Online evaluation that samples live queries and runs Ragas metrics in the background, feeding back into the evaluation database for drift detection.

---

## 17. Key Insight

> Phases 1 and 2 built a system that *can* produce correct, cited answers. Phase 3 builds the proof that it *does*. Without automated evaluation, every change to the pipeline — a new chunking strategy, a reworded prompt, a model upgrade — is a gamble. With CI-gated quality thresholds, the team can iterate aggressively on retrieval and generation quality knowing that regressions will be caught before they reach users. The golden dataset is the contract between the engineering team and the business: "These are the questions our system must answer correctly. Here's the mathematical proof that it does."
# Golden Dataset Changelog

## v1.0.0 — 2026-04-14

Initial seed dataset (14 samples) covering all six Phase 3 categories.

| Category      | Count |
|---------------|-------|
| exact_match   | 3     |
| conceptual    | 2     |
| multi_context | 2     |
| reasoning     | 2     |
| unanswerable  | 3     |
| adversarial   | 2     |

### Expansion to production scale (≥50 samples)

The SPEC sets a minimum viable size of 50 samples and a production target
of 100–200. Before enabling blocking CI gates, expand this file to reach
the category-specific minimums in SPEC.md §6.2:

- exact_match: ≥15
- conceptual: ≥12
- multi_context: ≥8
- unanswerable: ≥8
- reasoning: ≥5
- adversarial: ≥3

Use the manual curation workflow (SPEC §6.3 Step 1) for ~60% of new
samples and `python -m eval.generate` for synthetic augmentation of the
remaining ~40%. Every synthetic sample must be human-reviewed before
landing in the file.

### Version bumping

- **Patch** (1.0.x): fix incorrect reference answers or metadata
- **Minor** (1.x.0): add new samples without removing existing ones
- **Major** (x.0.0): restructure categories, remove samples, change schema

Evaluation scores from different dataset versions are not comparable.
Always record the dataset version alongside evaluation results.

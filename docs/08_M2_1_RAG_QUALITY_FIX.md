# M2.1 RAG Quality Fix — execution record

Status: Implementation and experiments completed; Product Review pending, quality gates not all passed. M2 not Frozen. See `validation/M2_1_RAG_QUALITY_REVIEW.md`.

## Approved scope

Fix evidence consumption and material-fact coverage, separate relevance / answerability / groundedness, ablate post-RRF filtering, and index original document structure. Keep structure-v1 180/30 and bounded ±1 neighbors. No rewrite, reranker, multi-query, agent runtime, connector or M3 work.

Ponytail: reuse the existing service, embedding cache and validation runner. No new orchestration framework or vector infrastructure. Work in the existing active workspace; preserve all prior changes and history.

## Sequence and verification

1. Preserve the original code and experiment. Mark the unchanged 34-query TON set as regression. Fix a disjoint holdout corpus before reading its content or designing queries.
2. On identical baseline candidates, compare current pipeline, raw RRF and RRF with necessary authority/validity policy; record per-query evidence before choosing the minimal policy change.
3. Focused failing tests → structural retrieval representation and cache invalidation/reindex → passing tests. Original chunk text, IDs and ordinals remain stable.
4. Focused failing tests → bounded evidence packet and explicit answer assessment, including missing material facts and citation validation. Do not equate relevance with proof.
5. Rerun the regression without changing questions/gold/rubric. Lock final implementation, independently author holdout queries on the already fixed corpus, seal queries, and execute once. No tuning against holdout results.
6. Report per-case fixes/regressions, retrieval and answer metrics separately, real-provider evidence and unavailable capabilities. Stop for review.

## Model decision

The existing service had local embeddings but no answer LLM. The Product Owner explicitly chose DeepSeek Flash at https://api.deepseek.com and filled the ignored local credential file on 2026-09-10. The configured official API model ID is deepseek-v4-flash; responses identify deepseek-flash. No provider is enabled by default: an explicit configuration path is required. Only the question and bounded selected official evidence may be sent; no workspace corpus. Four real-provider gates passed. The external runs and supplemental generic checks expose residual failures, not universal semantic-coverage success.

## Immutable baseline

- Original query/gold/rubric: `docs/validation/ton-docs-v1/queries.json`.
- SHA256: `e05e26672a7847de9a411902ff5ea1707a5de9f6e84e1f712562b4fe0593241b`.
- Original service SHA256: `cb486af4870c2de00ebbfd8cab868e683f30941b8aa662ec3f0b52b517a2c2ba`.
- Original service snapshot: ignored `data/generated/validation/m2-1/baseline-source/knowledge.py`.
- Baseline results, adjudication, corpus and receipt remain untouched.

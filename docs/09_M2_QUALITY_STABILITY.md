# M2 Quality Stability execution record

Status: **Product Frozen on 2026-09-10.** Confirmed M2.1 regressions are fixed; multilingual reranker is integrated behind explicit remote configuration with deterministic RRF fallback. The general `majority-one-slot-v1` candidate selection and `authority-validity-rrf-v4` historical policy close the two remaining TON multi-source blockers. The locked set passes 16/16; M3 has not started.

Implemented production changes are limited to temporal evidence selection/status, one-slot candidate diversification, bounded citation repair, and direct-question answerability scope. No new dependency, product UI, connector, rewrite, multi-query, GraphRAG, LLM Wiki or LangGraph was added.

Freeze evidence and non-blocking limitations: `10_M2_FREEZE_RECORD.md`. Supporting reports: `validation/M2_RAG_STABILITY_AND_RERANKER_REVIEW.md` and `validation/TON_MULTI_SOURCE_VALIDATION.md`.

# TON Multi-source Official Knowledge Validation

2026-09-10 · External validation evidence only. The corpus contains no production rule and remains local/Git ignored; the manifest and locked queries are versioned. M3 has not started.

## Decision summary

The fixed 13-source corpus and 16-query set now passes all locked cases for announcement-over-docs, legacy/current selection, release supersession, current-source conflict, historical `as_of_time`, `outdated_only`, `insufficient_evidence`, and `no_authoritative_source`. Strict pass, status accuracy and required/forbidden source-selection accuracy are all 100%.

Both Freeze blockers are closed without changing chunking, the source contract or the locked evaluation set. Product Owner accepted the final evidence and M2 is **Frozen**; M3 has not started.

## Locked corpus and provenance

- Dataset: `ton-multi-source-official-v1`
- Corpus manifest SHA-256: `403cc555f4fe2799ad969da4a8820fd976f5c68e0a4f961dc41182103c0b6447`
- Query set SHA-256: `6bdd006d34cb3825a1b5b6ceede9abf6bc56981ef244eab3f56d5480f8c99b46`
- Final retrieval timestamp: `2026-09-10T09:34:12.550027Z`
- TON Docs repository: `https://github.com/ton-blockchain/docs`
- Pinned Docs commit: `0e5a346d1e69a5345d333be669576acf21c6b93a`
- Docs license: CC-BY-SA-4.0 for documentation/non-code text; MIT for code snippets.
- GitHub release text: the repository exposes LGPL source licensing, but no separate release-note prose license was found. Validation does not assume wider redistribution rights.
- Official Telegram/Medium-linked content: no explicit reuse license was found. Only hashes, metadata and small diagnostic excerpts are versioned; fetched bodies, chunks and index stay local.

The locked corpus contains four current/historical Product Docs snapshots, two whitepapers (legacy Catchain and current Simplex), two GitHub releases/changelogs, one official Telegram post carrying an official-blog/Medium excerpt, and four official announcements. `source_type` and `source_channel` remain separate; all sources entered through the generic Manual Official Source contract.

The Medium page did not expose a recoverable precise timestamp. The represented source is therefore the precisely timestamped official Telegram post that excerpted and linked it (`source_type=official_blog`, `source_channel=telegram_announcement`), not an invented Medium timestamp. The Simplex page gives only `2026-03-10`; its precise `published_at`/`effective_from` refer to the pinned Docs revision, and no same-day sequence claim relies on the date-only value.

Versioned manifests:

- `validation/ton-multi-source-v1/corpus.json`
- `validation/ton-multi-source-v1/queries.json`

Fetched content and run artifacts are ignored under `data/generated/validation/ton-multi-source-v1/`.
The final locked regression is `run-8`; earlier runs remain local audit evidence and are not aggregated into the final score.

## Locked evaluation design

The source corpus was fixed before question design. The 16 queries and gold were then hashed and frozen before the first query run; neither was edited after results were observed.

| Dimension | N |
|---|---:|
| Announcement over Docs / announcement supersession | 3 |
| Historical `as_of_time` / release `as_of_time` | 3 |
| Legacy whitepaper vs current whitepaper | 1 |
| Release/changelog supersession | 1 |
| Current Docs vs historical blog | 1 |
| Current-source conflict | 1 |
| Historical official-blog evidence | 1 |
| `outdated_only` | 1 |
| `insufficient_evidence` | 2 |
| `no_authoritative_source` | 1 |
| Additional post-effective announcement check | 1 |

The run used the formal M2 path unchanged: structure-v1, 180/30 chunks, ±1 bounded context, FTS5 + multilingual embeddings + RRF, necessary metadata policy, bounded Top20, validated multilingual reranker, and the existing answer pipeline.

## Results

| Run | Strict pass | Status accuracy | Required/forbidden source accuracy |
|---|---:|---:|---:|
| First locked run | 12/16 = 75.0% | 13/16 = 81.3% | 14/16 = 87.5% |
| Post-answer-fix regression | 14/16 = 87.5% | 14/16 = 87.5% | 15/16 = 93.8% |
| Final blocker regression | **16/16 = 100%** | **16/16 = 100%** | **16/16 = 100%** |

The final regression reused hash-verified local copies of the exact locked corpus and query set after GitHub rate limiting prevented a redundant refetch. No body, query, gold or rubric changed. All 16 reranker calls produced valid permutations; no benchmark-only judge call is included in product runtime accounting.

### What passed

- **Authority and recency:** the effective token-rename announcement wins over the older Docs snapshot; current Simplex wins over legacy Catchain; v2026.08 wins over v2026.05.
- **Supersession:** scheduled and activated TVM announcements resolve correctly on either side of the activation time; inactive supporting claims are removed when active evidence already proves the same requirement.
- **Historical RAG:** both token-name times and both release times select the source actually published/effective at the requested `as_of_time`.
- **Abstention:** both related-but-unproven questions return `insufficient_evidence`; the unrelated question returns `no_authoritative_source`; legacy-only Catchain evidence returns `outdated_only`.
- **Citation:** passed cases cite the expected source and do not use forbidden superseded evidence as the answer basis.

### General fixes proven by the locked regression

The first run exposed two framework-agnostic defects. The answer packet did not include `query_as_of_time` plus effective/supersession intervals, so the provider abstained even when deterministic policy had selected evidence valid at that historical time. It could also retain a superseded claim after active evidence already supported the same fact. The fixes only expose existing temporal metadata to answer assessment and deterministically remove the redundant inactive claim. They changed MS02 and MS11 from fail to pass without changing product contracts, queries, gold, chunking, retrieval components or provider dependencies.

## Closed Freeze blockers

### MS13 — verified historical status without a validity end

- Query: `Do current TON docs guarantee that every cross-shard message is processed instantly without delay?`
- Expected: `grounded` from current shard Docs.
- Final: `grounded` from current shard Docs. The 2022 post remains visible as historical context but is not used as an equal-priority current claim and does not create a current conflict.
- Policy: authority-policy `authority-validity-rrf-v4` does not fabricate `effective_until`, delete the source or infer age. For a current-fact query, `historical` only becomes background when the factual `validity` provenance is `source-provided` or `human-confirmed`. A past `as_of_time` can still make it eligible at that historical point. `system-derived` or `ai-inferred` historical labels do not automatically lower current priority.

### MS16 — current Release evidence missing from candidate pool

- Query: `In the current TON implementation, is the block candidate generated by the validator leader or by a separate collator?`
- Expected: `conflict` between current Simplex and v2026.08 release notes.
- Final: `conflict` between current Simplex and v2026.08 release notes; both required sources are selected.
- Fix: `majority-one-slot-v1` changes at most one item when a single source owns a strict majority of the candidate pool. It preserves the initial Top5 and replaces only the dominant source's lowest-ranked candidate with the highest-ranked unrepresented source from the deeper local retrieval pool. The remote pool remains bounded at 20 and the reranker can only reorder those candidates.
- Controlled evidence: source diversity rose from 3.97 to 4.50 unique sources per Top20, while multi-fact and long-document Recall@5 were unchanged and no locked query regressed. Hard per-source caps were rejected because they did cause regressions.

## Scope conclusion

No evidence supports query rewrite, multi-query, GraphRAG, LLM Wiki, LangGraph, larger chunks, wider neighbor context, crawler development or TON-specific routing. The two structural Freeze blockers are closed, the locked multi-source set is 16/16, and the wider retrieval/answer and generic regressions show no material regression. Product Owner accepted the evidence and **M2 is Frozen**. M3 remains out of scope.

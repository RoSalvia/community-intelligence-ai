# M2 Formal Reranker Integration and Regression

2026-09-10 · Product path integrated. The two TON multi-source Freeze blockers are closed by a controlled source-diversity experiment and authority-policy v4. Product Owner accepted the evidence and M2 is Frozen; M3 has not started.

## Outcome

The approved remote semantic path is now:

`Hybrid retrieval → necessary metadata policy → majority-one-slot-v1 candidate selection → bounded Top20 → validated multilingual reranker → Top5 → material-facts answer pipeline`

The product does not partially trust generated rankings. A remote provider that is absent, unsupported, timed out, failed, or returned an unknown/duplicate/missing ID causes the whole ranking to fall back to the original RRF Top5. The reranker cannot create a candidate, citation, or fact.

The formal regression reused the locked 34-query TON regression and 28-query document-disjoint holdout without editing query, gold, or rubric. Of 62 total queries, 50 are retrieval-answerable; answer/no-answer metrics use their applicable denominators. Run artifacts are local and Git ignored at `data/generated/validation/m2-3-formal-reranker-regression/run-6/`.

## Retrieval results

All values below use `structure-v1`, 180/30 chunks and ±1 neighbor context. The RRF fallback remains the deterministic Top5. The semantic path applies authority-policy v4 and the validated one-slot diversity rule before sending at most 20 existing candidates to the reranker.

| Path | Hit@1 / @3 / @5 | Precision@1 / @3 / @5 | Recall@1 / @3 / @5 | R-Precision | MRR | nDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| RRF Top5 | 68.0 / 78.0 / 82.0% | 68.0 / 36.7 / 24.4% | 49.0 / 69.0 / 74.3% | 63.0% | 0.736 | 0.706 |
| Reranker Top5 | **98.0 / 98.0 / 98.0%** | **98.0 / 50.7 / 32.0%** | **71.2 / 94.2 / 96.7%** | **89.7%** | **0.980** | **0.958** |

Each answerable query has 1.66 gold chunks on average, so fixed Precision@5 has a natural ceiling of 33.2% even with every gold chunk retrieved. Reranker Precision@5 reaches 32.0%; R-Precision is the complementary cardinality-aware measure.

### Language slices

| Path / language | N | Hit@1 / @3 / @5 | Precision@1 / @3 / @5 | Recall@1 / @3 / @5 | R-Precision | MRR | nDCG@5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| RRF EN | 32 | 75.0 / 84.4 / 87.5% | 75.0 / 37.5 / 25.6% | 56.3 / 75.5 / 82.8% | 66.1% | 0.798 | 0.776 |
| Reranker EN | 32 | **100 / 100 / 100%** | **100 / 50.0 / 31.9%** | **74.2 / 96.1 / 99.0%** | **90.6%** | **1.000** | **0.978** |
| RRF CN | 9 | 44.4 / 66.7 / 66.7% | 44.4 / 29.6 / 17.8% | 33.3 / 55.6 / 55.6% | 55.6% | 0.556 | 0.530 |
| Reranker CN | 9 | **100 / 100 / 100%** | **100 / 48.1 / 28.9%** | **77.8 / 100 / 100%** | **94.4%** | **1.000** | **0.991** |
| RRF ES | 9 | 66.7 / 66.7 / 77.8% | 66.7 / 40.7 / 26.7% | 38.9 / 59.3 / 63.0% | 59.3% | 0.694 | 0.630 |
| Reranker ES | 9 | **88.9 / 88.9 / 88.9%** | **88.9 / 55.6 / 35.6%** | **53.7 / 81.5 / 85.2%** | **81.5%** | **0.889** | **0.852** |

### Product-relevant slices

| Path / slice | N | Hit@1 / @3 / @5 | Precision@1 / @3 / @5 | Recall@1 / @3 / @5 | R-Precision | MRR | nDCG@5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| RRF cross-language | 18 | 55.6 / 66.7 / 72.2% | 55.6 / 35.2 / 22.2% | 36.1 / 57.4 / 59.3% | 57.4% | 0.625 | 0.580 |
| Reranker cross-language | 18 | **94.4 / 94.4 / 94.4%** | **94.4 / 51.9 / 32.2%** | **65.7 / 90.7 / 92.6%** | **88.0%** | **0.944** | **0.922** |
| RRF noisy | 5 | 40.0 / 40.0 / 60.0% | 40.0 / 20.0 / 16.0% | 26.7 / 33.3 / 43.3% | 33.3% | 0.440 | 0.388 |
| Reranker noisy | 5 | **100 / 100 / 100%** | **100 / 60.0 / 44.0%** | **61.7 / 88.3 / 100%** | **93.3%** | **1.000** | **0.989** |
| RRF multi-fact | 24 | 70.8 / 87.5 / 95.8% | 70.8 / 51.4 / 35.8% | 31.3 / 68.8 / 79.9% | 60.4% | 0.803 | 0.736 |
| Reranker multi-fact | 24 | **100 / 100 / 100%** | **100 / 70.8 / 45.8%** | **44.1 / 92.0 / 97.2%** | **82.6%** | **1.000** | **0.954** |

The final product-path result is 96.7% Recall@5, materially above RRF's 74.3%. Remote reranker output varies slightly across otherwise identical runs; the final strict-order run is the reporting baseline. Answer quality is reported separately below.

## Controlled source-diversity experiment

The locked 62-query set compared A, the prior bounded RRF Top20, with B, a minimal general rule. B first creates the same Top20, then looks deeper only in local lexical/embedding candidates. If one source owns a strict majority of the pool, it replaces exactly that source's lowest-ranked item with the highest-ranked item from an unrepresented source. The original first five candidates are preserved, the remote payload stays capped at 20, and no source type, project name or TON rule is encoded.

Hard per-source caps from 2 through 8 were screened and rejected because they reduced candidate Recall@20, including long-document, multi-fact and cross-language slices. `majority-one-slot-v1` was selected because candidate Recall@20 stayed 98.7%, multi-fact stayed 97.2%, long-document stayed 98.2%, and cross-language stayed 98.1%. Mean unique sources in Top20 rose from 3.97 to 4.50; mean dominant-source share fell from 58.0% to 55.3%.

In the final controlled reranker A/B, B kept Hit@5 and Recall@5 unchanged at 98.0% and 96.7%, improved MRR from 0.960 to 0.970 and nDCG@5 from 0.947 to 0.950. Multi-fact and long-document Recall@5 stayed at 97.2% and 98.2%; cross-language Hit/Recall/MRR/nDCG were unchanged. No individual query lost Recall@5 or MRR. Separately, the locked multi-source MS16 release chunk entered the candidate pool and the result changed from false `grounded` to the required current-source `conflict`.

## Answer and grounding results

| Metric | RRF fallback path | Reranker semantic path |
|---|---:|---:|
| Complete Answer Rate | 43/50 = 86.0% | **48/50 = 96.0%** |
| False Grounded Rate | 2/45 = 4.4% | **2/50 = 4.0%** |
| Insufficient Evidence Accuracy | **6/6 = 100%** | **6/6 = 100%** |
| No-answer Accuracy | **6/6 = 100%** | **6/6 = 100%** |
| Citation Validity | **51/51 = 100%** | **54/54 = 100%** |
| Citation repair rate | 0/62 | 0/62 |
| Answer-provider error/fallback rate | 0/62 | 0/62 |
| Reranker fallback rate | n/a | 2/62 = 3.2% |

The two incomplete reranker answers are T06 and H20: selected evidence is relevant and citations are valid, but one rubric material detail is omitted. Both are also incomplete on the RRF arm, so no locked RRF success regressed. Small answer-count changes between remote runs can include provider variance; deterministic citation validation remains 100%.

## Runtime, privacy exposure and estimated cost

These are complete product-path measurements, not reranker-only increments. Benchmark judge calls are excluded.

| Runtime item / query | RRF fallback | Reranker semantic | Delta |
|---|---:|---:|---:|
| Remote calls | 0.968 | 1.903 | +0.935 |
| Input tokens | 4,134.5 | 6,913.9 | +2,779.3 |
| Output tokens | 306.4 | 753.8 | +447.4 |
| Total tokens | 4,440.9 | 7,667.6 | +3,226.7 |
| Remote Evidence chars | 2,893.8 | 7,975.0 | +5,081.2 |
| Estimated Evidence tokens (chars/4) | 723.8 | 1,994.2 | +1,270.4 |
| p50 latency | 1.955s | 4.484s | +2.530s |
| p95 latency | 2.981s | 5.995s | +3.014s |
| Peak estimated cost | US$0.001825 | US$0.002426 | +US$0.000601 |
| Off-peak estimated cost | US$0.000913 | US$0.001213 | +US$0.000300 |

Input-token accounting uses model-reported prompt cache-hit/miss fields. The estimate applies the official DeepSeek V4 Flash rates current on 2026-09-10: peak US$0.014/M cache-hit input, US$0.44/M cache-miss input and US$1.32/M output; off-peak is half. The configured/returned alias was `deepseek-flash`, so this is an estimate, not a billing statement. Pricing is provider-specific and not part of the product contract.

Remote evidence exposure stays bounded to the selected public-test snippets. The formal median/p95 evidence payload was 7,498/15,727 characters on the reranker path versus 2,621/5,136 on RRF. No complete corpus, local path, secret, operator identity or source URL was sent. Relative to the pre-diversity formal run, mean reranker Evidence changed from 8,013 to 7,975 characters, peak estimated cost changed by less than US$0.000003/query, p50 changed by +0.011s and p95 by -0.118s. There is no meaningful remote cost or latency increase; deeper retrieval is local.

## Fallback verification

- No provider configuration: RRF Top5 retained.
- Provider exception/timeout: RRF Top5 retained.
- Unknown, duplicate or missing IDs: entire generated order rejected; RRF Top5 retained.
- Non-object/malformed ranking: rejected before product selection; RRF Top5 retained.
- The final live formal run produced two invalid permutations and deterministically retained the original RRF Top5. Separate malformed/timeout/unknown/duplicate/missing-ID tests exercised the same fallback contract.
- The final hardening change only rejects non-object responses and is covered by a focused test; it does not change valid-run metrics.

## Scope decision

Reranking and the minimal source-diversity rule are adopted because the gains address observed low-rank, cross-language, noisy-query and source-crowding failures without slice regressions. There is no evidence to add query rewrite, multi-query, GraphRAG, LLM Wiki, LangGraph, larger chunks or broader neighbors. Conditional reranking remains a future latency/cost/privacy hypothesis, not current M2 scope.

The 12-query generic Knowledge regression stayed at 91.7% Recall@5 with all five answer-status/citation gates at 100% across three repetitions; its MRR improved from 0.932 to 1.000. Final automated verification is `392 passed, 5 skipped`; the skips are explicit live-provider gates. Frontend tests, typecheck, lint and production build also pass. Full TON multi-source outcome is recorded in `TON_MULTI_SOURCE_VALIDATION.md`.

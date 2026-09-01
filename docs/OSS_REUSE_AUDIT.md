# OSS Reuse Audit

**Audit date:** 2026-09-01  
**Scope:** Offline, synthetic-first Community Intelligence MVP  
**Evidence rule:** Decisions below use official repositories, package metadata, release pages, model cards and license files. Maintenance observations are a dated snapshot, not a guarantee. No third-party source code has been copied into this repository.

## Decision summary

The MVP will reuse maintained Python libraries for parsing, tabular operations, clustering, graph calculations, statistics and the local dashboard. It will custom-build only the thin product-specific layer: normalized Community Intelligence contracts, evidence rules, Campaign judgments, conversation episodes, metric formulas and report orchestration.

`tg-monitor-v2`, Shield, TelegramStatisticsCollector and alternative export projects are references, not copied code. BERTopic, DeepEval, statsmodels, Plotly, rustworkx and a vector database remain outside the minimum dependency set until measured product needs justify them.

## Capability decisions

| Capability | Candidate | License | Maintenance / maturity evidence | Integration cost | Reuse strategy | Decision |
|---|---|---|---|---|---|---|
| Telegram export parsing | Python standard library; [`mdemyanov/tg-parser`](https://github.com/mdemyanov/tg-parser) audited as an alternative | Project-owned adapter; alternative is MIT | `tg-parser` v1.2.0 was dated 2026-01-20 but had only five repository commits and one visible PyPI maintainer | Low for the deliberately bounded Telegram Desktop `result.json` subset | Custom strict adapter with a golden fixture; no third-party parser code copied | `BUILD_CUSTOM` for V0.1; re-audit a dependency if format coverage expands |
| Telegram collection concepts | [`ali-albdaer/TelegramStatisticsCollector`](https://github.com/ali-albdaer/TelegramStatisticsCollector) | MIT | Latest observed default-branch commit 2024-07-31; no releases; script collection requiring Telethon sessions | High and mismatched with offline V1 | Read schema/SQLite ideas only | `REFERENCE_ONLY` |
| Telegram export edge cases | [`Retro-Zero/telegram-export-md`](https://github.com/Retro-Zero/telegram-export-md) | MIT | v0.4.1 dated 2026-08-15; fresh but beta and small history | Medium; Markdown conversion is not an analytics contract | Use as fixture/schema reference only | `REFERENCE_ONLY` |
| Telegram schema comparison | [`StackTheFennec/telegram-export-parser`](https://github.com/StackTheFennec/telegram-export-parser) | MIT | Latest observed commit 2025-08-13; TypeScript package v0.1.0 | High for a Python-only MVP | Reference field coverage only | `REFERENCE_ONLY` |
| Duplicate / spam design | [`redstone-md/shield`](https://github.com/redstone-md/shield) | MIT | Active Go moderation service; observed v0.1.0 in 2026 and recent August 2026 commits | High; full live bot service, no Python API | Review detector contracts and tests; copy no code | `REFERENCE_ONLY` |
| Duplicate / filler / burst evidence | Small local rules | Project-owned | No audited package covered the required offline evidence contract without large unrelated infrastructure | Medium | Unicode normalization, hashes and rolling windows with rule versions and evidence IDs | `BUILD_CUSTOM` |
| Tabular loading and aggregation | [`pandas`](https://github.com/pandas-dev/pandas) | BSD-3-Clause | Mature, active project; observed v3.0.5 release in 2026 | Low | Direct dependency | `USE_AS_DEPENDENCY` |
| Multilingual embeddings | [`sentence-transformers`](https://github.com/huggingface/sentence-transformers) | Apache-2.0 | Active production/stable project; observed v5.5.1 in 2026 | Medium due to PyTorch/Transformers footprint | Optional semantic extra, isolated behind a provider | `USE_AS_DEPENDENCY` for the evaluated semantic phase, not the deterministic baseline |
| Multilingual model | [`paraphrase-multilingual-MiniLM-L12-v2`](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) | Apache-2.0 stated in model card | Model card states 50 languages, 117.7M parameters, 384 dimensions and 128-token maximum; ARM64 INT8 ONNX artifact is available | Low–medium on a 16 GB Apple Silicon laptop; long messages require chunking | Pin exact model revision/artifact before evaluated use | `USE_AS_DEPENDENCY` in semantic phase |
| Lightweight semantic fallback | [`Model2Vec`](https://github.com/MinishLab/model2vec) and [`potion-multilingual-128M`](https://huggingface.co/minishlab/potion-multilingual-128M) | MIT | Active but beta; model card states broad multilingual coverage | Low compute, lower contextual quality | Compare only if installation/startup becomes a measured problem | `REFERENCE_ONLY` |
| Topic / behavior clustering baseline | [`scikit-learn`](https://github.com/scikit-learn/scikit-learn) | BSD-3-Clause | Mature, active; official examples cover TF-IDF plus KMeans text clustering | Low for thousands of messages | Direct dependency for TF-IDF, KMeans and evaluation metrics | `USE_AS_DEPENDENCY` |
| Advanced topic discovery | [`BERTopic`](https://github.com/MaartenGr/BERTopic) | MIT | Maintained; observed v0.17.4 in late 2025, slower cadence than core stack | Medium–high due to UMAP/HDBSCAN and extra dependencies | Add only if baseline failure is demonstrated | `REFERENCE_ONLY` for V1; later `USE_AS_DEPENDENCY` if justified |
| Conversation graph | [`NetworkX`](https://github.com/networkx/networkx) | BSD-3-Clause | Mature, active stable project | Low for synthetic MVP graph sizes | Direct dependency | `USE_AS_DEPENDENCY` |
| Large-graph alternative | [`rustworkx`](https://github.com/Qiskit/rustworkx) | Apache-2.0 | Active with macOS ARM64 wheels | Medium integration due to indexed-node API | Profile before changing graph engine | `REFERENCE_ONLY` |
| Statistical tests and association | [`SciPy`](https://github.com/scipy/scipy) | BSD-3-Clause | Mature, active scientific library | Low; assumptions and multiple testing still need product rules | Direct dependency for Spearman and uncertainty calculations | `USE_AS_DEPENDENCY` |
| Regression / time series | [`statsmodels`](https://github.com/statsmodels/statsmodels) | BSD-3-Clause | Mature; observed v0.15.0 release in 2026 | Medium and beyond minimum validation scope | Add only for a defined regression/time-series question | `REFERENCE_ONLY` for V1 |
| Local dashboard | [`Streamlit`](https://github.com/streamlit/streamlit) | Apache-2.0 | Mature and active; observed v1.62.0 in 2026 | Low | Direct dependency; local single-user dashboard | `USE_AS_DEPENDENCY` |
| Advanced charts | [`Plotly.py`](https://github.com/plotly/plotly.py) | MIT | Mature and active | Low–medium; unnecessary for first dashboard | Use Streamlit built-ins first | `REFERENCE_ONLY` for V1 |
| LLM evaluation framework | [`DeepEval`](https://github.com/confident-ai/deepeval) | Apache-2.0 | Active and fast-moving; observed v4.2.0 in 2026 | High for an offline MVP due to judge/model configuration and reproducibility controls | Build a small deterministic evaluation runner first | `BUILD_CUSTOM` for V1; re-audit when LLM/RAG evaluation is added |
| Architecture reference | [`chu0119/tg-monitor-v2`](https://github.com/chu0119/tg-monitor-v2) | No declared OSS license observed | Active architecture reference but no license granting reuse | High; FastAPI/React/MySQL/Redis/Telethon exceeds V1 | Observe separation and operational ideas only; copy no code | `REFERENCE_ONLY` |

## Minimal dependency boundary

The deterministic MVP directly needs Pydantic, pandas, NumPy, SciPy, scikit-learn, NetworkX, Streamlit, pytest and Ruff. Telegram Desktop JSON V0.1 is handled by a small project-owned standard-library adapter with golden end-to-end tests, so `tg-parser` is not installed and no parser source was copied. Sentence Transformers and the multilingual MiniLM model are a separate semantic extra; they must not be silently downloaded during tests or described as evaluated until the pinned model path, model-card license, chunking policy and golden multilingual evaluation all pass.

## Custom evidence rules

Duplicate detection will normalize a copy of text with Unicode NFKC, case folding and whitespace normalization, then calculate a SHA-256 hash while preserving original text. Filler analysis will expose measurable features such as normalized length, token count, repeated-character or punctuation ratio and a small versioned phrase list; it is a review flag, not a personal judgment. Burst detection will use rolling message counts and inter-arrival time per actor and community in UTC.

Every emitted flag must contain `rule_id`, rule version, configured threshold, raw metric, time window and supporting message IDs. Thresholds are product configuration and require labelled-fixture calibration before operational use.

## Build-versus-reuse conclusion

Reuse mature infrastructure; custom-build the Community Intelligence contract and orchestration. The repository will not import live Telegram services or combine large reference repositories. It will preserve the raw input boundary, make transformations reproducible, keep evidence joinable, and label deterministic, semantic and LLM methods separately.

## License caveat

The project owner selected Apache License 2.0 for this repository after reviewing the direct runtime dependencies and the optional semantic dependency/model. The root `LICENSE` contains the standard license text, and `pyproject.toml` publishes the SPDX expression and license file through PEP 639 metadata.

This audit records top-level licenses and dated repository evidence; it is not a legal opinion or a complete transitive software bill of materials. The final lock file and optional model artifacts require a separate dependency inventory before external distribution.

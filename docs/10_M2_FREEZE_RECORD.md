# M2 Product Freeze Record

状态：**Approved / Product Frozen**

日期：2026-09-10

范围：M2 Project Knowledge Base / RAG；M3 未开始。

## Freeze 含义

Project Knowledge contract 与 production baseline 已达到 MVP 后续模块依赖条件。后续 M3–M8 可以依赖当前 source/revision/chunk provenance、historical `as_of_time`、五类 answer status、citation validation 和 deterministic fallback。Freeze 不代表停止修复缺陷；任何改变产品 contract、baseline semantics 或 privacy boundary 的变更必须显式 version、回归并重新评审。

## 正式 baseline versions

| Concern | Frozen version |
|---|---|
| Parser | `plain-text-and-pdf-v1` |
| Chunk strategy | `structure-aware` / `structure-v1` |
| Chunk fallback configuration | `180 max tokens / 30 overlap` |
| Context expansion | `±1 bounded neighbor` |
| Retrieval representation | `title-heading-body-v1` |
| Index | `sqlite-fts5-rrf-structure-v2` |
| Local multilingual embedding | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` @ `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` |
| Authority/validity policy | `authority-validity-rrf-v4` |
| Candidate selection | `majority-one-slot-v1` |
| Remote reranker contract | `multilingual-listwise-v1`, bounded Top20, complete-permutation validation, deterministic original RRF Top5 fallback |
| Answer/grounding contract | `material-facts-evidence-v2` |

正式 semantic path：

`FTS5 + multilingual embedding → RRF → authority-validity-rrf-v4 → majority-one-slot-v1 → bounded Top20 → multilingual-listwise-v1 → Top5 → ±1 context → material-facts-evidence-v2 → citation validation`

Remote LLM 未配置或 reranker timeout/failure/非法 ID permutation 时，使用原始 RRF Top5。Reranker 只能重排既有 candidates，不能生成 Evidence 或事实。

## Freeze evidence

- Locked 34-query TON regression + 28-query document-disjoint holdout：reranker Hit@5 98.0%、Recall@5 96.7%、MRR 0.980、nDCG@5 0.958；Complete Answer 48/50、False Grounded 2/50、Insufficient 6/6、No-answer 6/6、Citation Validity 54/54。
- Source-diversity controlled experiment：Top20 平均 unique sources 3.97 → 4.50；dominant source share 58.0% → 55.3%；multi-fact、long-document、cross-language 无 Recall@5 regression；MS16 从 false grounded 修复为 required current-source conflict。
- Locked TON Multi-source：corpus SHA-256 `403cc555f4fe2799ad969da4a8820fd976f5c68e0a4f961dc41182103c0b6447`，query SHA-256 `6bdd006d34cb3825a1b5b6ceede9abf6bc56981ef244eab3f56d5480f8c99b46`；16/16 strict pass，status/source selection 均为 100%。
- Generic Knowledge regression：三轮 Recall@5 91.7%，cross-language Recall@5 100%；五类 answer status、citation、grounding/outdated gates 均为 100%。
- Automated verification：backend `392 passed, 5 skipped`；frontend tests、typecheck、lint、production build 通过。Skipped tests 是未显式配置 credentials 时的 live-provider gates。

Supporting reports：

- `docs/validation/M2_RAG_STABILITY_AND_RERANKER_REVIEW.md`
- `docs/validation/TON_MULTI_SOURCE_VALIDATION.md`
- `docs/validation/M2_1_RAG_QUALITY_REVIEW.md`

## 已知但不阻塞 Freeze

- 锁定集 T06、H20 仍可能遗漏一个 material answer detail；selected Evidence 与 citations 正确，没有观察到错误事实。作为 answer-quality optimization 进入 M9 evaluation backlog。
- Remote reranker 有 latency、成本和最小 Evidence exposure；conditional reranking 仅作为未来优化 hypothesis，当前不改变统一 remote semantic path。
- 当前没有 local multilingual reranker；无 remote provider 时 deterministic RRF fallback 保持可用但 retrieval quality 较低。Local reranker 属后续 optimization。
- TON 是当前最完整的 multi-source external validation；更多合法、独立项目数据集属于后续 external validation，不改变 frozen generic contract。
- 自动 Docs/X/Medium/Telegram/GitHub crawler、扫描 PDF OCR 不属于 M2 P0；运营继续使用 file/manual official source contract。
- 来源只有日期而没有精确时区时间时，系统保留 precision limitation，不据此宣称同日先后顺序已经验证。

以上项目不阻塞 Project Knowledge 的 MVP 核心用户价值，也不得作为继续扩展 M2 技术栈的理由。

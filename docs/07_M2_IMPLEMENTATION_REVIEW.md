# M2 Project Knowledge Base / RAG — Product Review

状态：**Ready for Product Review；尚未 Frozen；未进入 M3。**

## 1. 用户新增能完成什么

用户现在可以在任意 Workspace 中：

- 通过 `.md`、`.txt`、text-based `.pdf` 或 Manual Official Web Source 添加官方资料；
- 分开设置内容类型与发布渠道，并查看 authority、validity、版本、处理 provenance 与 metadata provenance；
- 对同一 source 添加新内容时创建 revision；相同内容不会重复 parse/chunk/embed；
- 用 original query 和 optional `as_of_time` 检索当时有效的官方事实；
- 看到 `grounded`、`outdated_only`、`conflict`、`no_authoritative_source`、`insufficient_evidence`；
- 打开 citation 对应的 source、revision、chunk 和有界相邻上下文。

确定性的 message count、reply graph、latency 与 activity trend 没有接入 RAG。

## 2. 实际 Flow

```text
选择 / 创建 Workspace
→ Add Source（文件或 Manual Official Web Source）
→ 填写 identity / authority / time / provenance metadata
→ 查看 parse、chunk、index 和 revision 状态
→ 输入 query + optional as_of_time
→ FTS5 + local multilingual embedding → RRF
→ validity / authority / recency policy
→ answer status + extractive answer context
→ 打开 citation → source / revision / chunk provenance
```

## 3. Metadata 管理

Source detail 显示 source type、source channel、URL/platform identity、language/project scope、authority/official status、owner/verification method、逐字段 metadata provenance 与 semantic tags。Revision detail 显示所有 offset-aware 时间、UTC 标准化值、原始 source timezone、hash、版本关系、parser/chunk/embedding/index version 和 processing status。

`authority_level`、`official_status`、`published_at`、`validity`、`source_type` 若标为 `ai-inferred` 会被拒绝，必须先由人确认。

## 4. 五类 Answer Status 体验

| 状态 | 页面含义 | 行为 |
|---|---|---|
| `grounded` | 当时有效、已验证的官方依据足够 | 显示 extractive context 与 citation |
| `outdated_only` | 只找到当时无效/已过期资料 | 明示不能作为当前事实，仍可打开历史 citation |
| `conflict` | 当前有效的官方材料存在结构化 material fact 冲突 | 并列显示，不自动调和 |
| `no_authoritative_source` | 没有可靠且相关的官方资料 | abstain，不生成答案 |
| `insufficient_evidence` | 找到相关材料，但不足以证明具体说法 | 显示相关 citation 与不足说明 |

## 5. Chunk / Context 策略

`structure-v1` 优先 heading、paragraph、FAQ Question+Answer、announcement bullets、release/version section。超过上限才按 token fallback 拆分；`max_tokens` 与 `overlap_tokens` 是配置，不是产品常量。Retrieval 命中小单元后，默认只扩展同 revision 每侧一个 neighbor，并受总字符上限约束。

对比了三组配置：`120/0 + no neighbor`、`180/30 + ±1 neighbor`、`260/40 + ±1 neighbor`。当前 12-query curated set 的 retrieval/status 指标相同；因此 P0 保留中间配置作为默认，但没有证据表明更大 chunk 或 overlap 更优。neighbor expansion 的价值体现在返回完整上下文，不改变该小样本的命中指标。

## 6. Evaluation 结果

评测集：`generic-knowledge-fixtures-v1`，N=12；EN 8、CN 1、ES 2、cross-language 1；覆盖 9 个 sources 与 whitepaper/docs/FAQ/announcement/blog/release/manual note。

默认配置实测：

- Retrieval Recall@5 = **1.00**；MRR = **1.00**；nDCG@5 = **1.00**；cross-language Recall@5 = **1.00**。
- Citation validity = **1.00**；grounded status accuracy = **1.00**；no-answer/abstention = **1.00**；insufficient-evidence = **1.00**；conflict detection = **1.00**；outdated detection = **1.00**；outdated-source error rate = **0.00**。

这是刻意构造的开发 benchmark，不是实际 Web3 社区效果声明。完整逐 case、模型 revision 与三组配置在 `docs/evaluation/M2_KNOWLEDGE_RAG_BENCHMARK.json`。

当前未发现需要 query rewrite、reranker 或 multi-query 的 benchmark failure case，因此没有加入。

## 7. Incremental indexing

自动化测试确认：同 source+content hash 返回原 revision；另一个 source 出现相同 chunk text 时命中 content-addressed embedding cache；仅新内容触发新的 embedding。新增 source/revision 不重建 Workspace 全量索引。

## 8. 已通过的 M2 Acceptance Criteria

- D2.1：multi-source metadata、offset-aware time、revision、hash、private artifact、关键 provenance gate。
- D2.2：MD/TXT/text PDF/manual web source、structure-aware chunk、page/section provenance、扫描 PDF unavailable、坏文件无 partial source/index。
- D2.3：复用 pinned local multilingual model、离线 checksum gate、content-addressed cache、unavailable degradation。
- D2.4：FTS5 + embedding + RRF、as-of filter、bounded expansion、可解析 citation。
- D2.5：五类 status、historical retrieval、结构化 conflict、abstention。
- D2.6：generic EN/CN/ES fixture/golden set 与分层 evaluation report。
- D2.7：可亲手完成 flow 的 internal Knowledge Review Surface。

## 9. Unavailable / degraded

- 扫描 PDF/OCR unavailable；HTML、DOCX 与自动 X/Medium/Telegram/GitHub connector 未实现。
- 没有配置本地 embedding model 时降级为 FTS5，并在 response/UI 明示；不会联网下载。
- `conflict` 的确定性 P0 gate 依赖 human/source-provided 的规范化 `fact_key/fact_value`；纯自然语言、无结构的矛盾只能作为候选，尚不能宣称可靠自动判定。
- 返回的是可核查 extractive context，不是自由生成的 Copilot 最终回答；生成式 claim/citation validation 属于后续显式 provider flow。
- Benchmark 规模小且 curated；尚无真实项目资料 external validation，不支持真实业务效果声明。

## 10. Product Review 启动

首次需要本地模型时：

```bash
uv sync --extra semantic
PYTHONPATH=src .venv/bin/python scripts/prefetch_semantic_model.py
```

本机已存在 verified model 后启动：

```bash
PYTHONPATH=src .venv/bin/python -m community_intelligence.cli serve \
  --knowledge-review \
  --semantic-model-dir data/generated/models/paraphrase-multilingual-MiniLM-L12-v2-e8f8c211 \
  --port 8892
```

访问：`http://127.0.0.1:8892/internal/knowledge-review`

建议人工覆盖：一个 current source；一个已过 `effective_until` 的 source；两个相同 `fact_key` 但不同 `fact_value` 的 current source；一个完全无关 query；一个只命中主题但没有具体答案的 query。

# M2 Quality Stability + Controlled Multilingual Reranker Experiment

2026-09-10 · 基础稳定性修复完成；reranker 对照完成。正式 retrieval path 尚未接入 reranker，等待 Product Owner 接受 latency / remote-snippet trade-off。

## 结论

三个已确认的基础问题已闭合：generic 12 题连续三轮均为 12/12 answer status 正确，`outdated_only`、release、conflict、insufficient 与 no-answer 均未退化；H18 不再把用户的操作背景扩成未知本机值；非法引用会进行一次有界修复，正常 abstention 不重试。

在同一批 50 条可回答 TON Docs query 上，只把必要 metadata policy 后的同一 Top20 从 RRF 排序改为 multilingual listwise reranker 排序：Recall@5 从 **74.3% → 98.7%**，完整答案从 **43/50 → 47/50**。代价是每题多一次显式配置的 remote LLM 调用，端到端中位延迟从 **2.11s → 4.51s**。

建议采用 reranker，但仅用于用户显式配置 remote LLM 的 semantic profile；未配置时继续使用 RRF。由于这会扩大单次远程 evidence selection 到 bounded Top20 并增加约 2.31s 中位延迟，本轮只提交采用建议，不直接修改正式 retrieval contract。

## 1. 基础质量稳定修复

### Temporal / metadata

- necessary policy 仍排除 unverified、draft/unknown 与 future。
- current query 仍优先 active source。
- 若 inactive candidate 同时被 lexical 与 multilingual semantic 找到，且其原始 RRF 排名高于所有 active candidate，则保留该 candidate；不会再被 active-first 整体挤出 Top5。
- Answer 层读取 active 与 inactive evidence，并按每条已验证 claim 的实际 citation temporal state 决定 `grounded` / `outdated_only`，不再用“候选中存在任一 active source”代替事实有效性。

### Answerability / citation stability

- Prompt 只分解用户直接询问的 material facts；操作背景、未知本机环境值和未询问的原因不再自动成为额外 requirement。
- Quote 必须是对应原始 chunk text 的逐字摘录，不能把 heading metadata 拼进 quote。
- 确定性 quote 校验失败时，允许同一 evidence packet 做一次 repair；repair 后仍不合法则保持 `insufficient_evidence`。合法的 insufficient/no-answer 不重试。

### Generic regression

`generic-knowledge-fixtures-v1` 使用固定 `structure-v1 / 180/30 / ±1` 连续运行 3 次：

| Gate | 三轮结果 |
|---|---:|
| Answer status | 12/12、12/12、12/12 |
| outdated_only | 1/1、1/1、1/1 |
| grounded | 8/8、8/8、8/8 |
| conflict / insufficient / no-answer | 每轮全部通过 |
| Citation validity | 每轮 100% |
| Recall@5 / MRR / nDCG@5 | 每轮 91.7% / 0.932 / 0.869 |

完整本地记录：`data/generated/validation/m2-2-generic-stability/run-1.json`（Git ignored）。

### 与 M2.1 的同题变化

固定 34 + 28 条 TON query 的 retrieval candidate generation 未变，因此 Current RRF 的 aggregate Recall@5 仍为 74.3%。质量修复发生在 temporal selection 与 answer 层：严格完整答案由 M2.1 的 `39/50（78%）` 提升到 `43/50（86%）`；严格 false-grounded 由 `5/44（11.4%）` 降至 `3/46（6.5%）`；insufficient `6/6`、no-answer `4/4` 保持。逐题净变化为 6 条改善、2 条由 complete 变 partial，原因见第 5 节。

## 2. Controlled reranker contract

- Query、gold、rubric 未修改：原 regression 34 题 + 原 holdout 28 题，共 62；其中可回答 50。
- Candidate generation 完全复用已锁定的 lexical Top20 + semantic Top20；没有 rewrite、multi-query 或重新召回。
- 两臂共享 necessary metadata policy 后的同一 Top20。
- Current arm：RRF policy Top5。
- Experiment arm：使用已显式配置的 `deepseek-v4-flash` 做一次 validation-only multilingual listwise ranking，再取 Top5。
- 两臂都使用相同 `material-facts-evidence-v2` answer pipeline、180/30 chunks、±1 neighbor。
- 完整答案由同一 locked rubric 的 paired AI judge 判定；不是独立人工评审。Retrieval 与 status/citation 指标为确定性计算。

Reranker 只看到 query 与 bounded candidate snippets。此次公开 TON corpus 每题 Top20 body 中位 5,549 字符、最大 9,578 字符；没有发送整份文档或私人数据。

## 3. Aggregate results

下表基于 50 条可回答 query；CN/ES 各 9 条，样本仍小。

| Slice | Current Recall@5 | Reranker Recall@5 | Current MRR | Reranker MRR | Current nDCG@5 | Reranker nDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| Overall | 74.3% | **98.7%** | 0.736 | **0.990** | 0.706 | **0.979** |
| EN（32） | 82.8% | **99.0%** | 0.798 | **0.984** | 0.776 | **0.980** |
| CN（9） | 55.6% | **100%** | 0.556 | **1.000** | 0.530 | **0.991** |
| ES（9） | 63.0% | **96.3%** | 0.694 | **1.000** | 0.630 | **0.963** |

| Answer / safety | Current | Reranker |
|---|---:|---:|
| 严格完整答案 | 43/50（86%） | **47/50（94%）** |
| Grounded 但未覆盖全部 rubric | 3/46 | 3/50 |
| Insufficient accuracy | 6/6 | 6/6 |
| No-answer accuracy | 4/4 | 4/4 |
| Retrieval Recall 降低的 case | — | **0** |

分数据集：原 regression Recall@5 `72.6% → 98.8%`，完整答案 `24/28 → 27/28`；holdout Recall@5 `76.5% → 98.5%`，完整答案 `19/22 → 20/22`。

## 4. 改善来自哪里

Reranker 改善了 16 条 query 的 gold Recall，没有降低任何 query 的 Recall。完整答案的净提升来自 4 个原已知 low-rank case：

| Case | Failure before | Result after |
|---|---|---|
| T13 | 中文 query；正确 semantic candidate 在 RRF 第 7 | complete |
| T15 | 中文 query；正确 candidate 在 RRF 第 8 | complete |
| T17 | 中文 query；正确 candidate 在 RRF 第 10 | complete |
| H03 | noisy query；正确 mnemonic candidate 在 RRF 第 7 | complete |

另外，T10/T11/T12 等 noisy query、T18/T22/H04/H20/H22 等 cross-language/multi-fact query 的 gold coverage 提高，但原答案已能由 neighbor/context 补齐，因此没有重复计入完整答案增量。

Reranker 后仍有两个非满 Recall case：T06 与 H08 各召回 3 个 gold 中的 2 个，但首个正确证据均排第一且答案所需事实已覆盖。这不是 query-level candidate miss。

## 5. Regression 与限制

- Reranker 相对 fixed Current RRF：没有完整答案 regression、没有 retrieval regression，insufficient/no-answer 不变。
- 相对 M2.1 旧答案，基础修复带来 T02/T03/T07/T12/H18/H22 改善，但 T06/H21 在原严格 rubric 下从 complete → partial。两题都回答了字面问题，遗漏的是 rubric 的额外上下文：T06 没明确复述“legacy”；H21 没补充“仅凭 client_id 不能解密”。为修 H18 而要求模型不扩写未询问背景后，这两项出现取舍。三次 prompt 尝试无法稳定兼得，继续调会针对 benchmark 过拟合，因此保留并如实计分。
- Listwise 输出有 1/62 次包含一个非候选 ID；确定性清洗丢弃该 ID，有效 Top5 顺序不变，遗漏候选按 RRF 顺序补尾。实验工具在定稿前暴露并修正了三项 runner guard：必须返回完整 permutation、实际候选少于 5、重复/非候选 ID。修正后从 checkpoint 续跑，不重算已完成 query。它们不改变产品结果，但说明生成式 reranker 必须保留 permutation validation/fallback。
- 完整答案评分来自 paired AI judge；需要 Product Owner 或独立 reviewer 才能升级为人工认可指标。
- 这仍是单一 TON Docs repository，不证明多来源 authority/time conflict 质量。

## 6. Latency 与 cost

| Runtime item | Current | Reranker path | Delta |
|---|---:|---:|---:|
| End-to-end median | 2.11s | 4.51s | **+2.31s paired median** |
| End-to-end p95 | 4.94s | 5.73s | +0.79s |
| Reranker-only median / p95 | — | 2.42s / 3.11s | +1 remote call |
| Answer model calls | 62 | 62 | 0 |
| Reranker calls | 0 | 62 | +62 |

Reranker 62 次共 205,892 tokens：117,628 cache-hit input、61,189 cache-miss input、27,075 output，平均约 3,321 tokens/query。按 [DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/) 在 2026-09-10 的 peak/off-peak 单价估算，62 题约 **US$0.064 / US$0.032**，即每题约 **US$0.00104 / US$0.00052**；这是 token 估算，不是账单。Benchmark 的 62 次 paired judge 调用不属于产品 runtime，已单独记录。

完整运行、模型 usage、latency 与原始回答位于 `data/generated/validation/m2-2-reranker-experiment/run-1/`（Git ignored）。

## 7. Recommendation / next gate

证据支持正式采用 reranker：它解决的正是已确认的 low-rank/cross-language failure，Recall 增加 24.3 个百分点、完整答案增加 8 个百分点，且无 safety status regression。对 Investigation/Copilot 这类非实时操作，约 2.31s 的中位增加是可接受的质量交换。

推荐 contract：

1. remote LLM 已由用户显式配置时，bounded policy Top20 → validated reranker Top5 → existing answer pipeline；
2. 未配置、调用失败或返回不足 5 个有效 ID 时，确定性回退 Current RRF Top5；
3. receipt 记录 reranker model/revision、latency、usage、fallback 和 candidate count；
4. 不加入 rewrite、multi-query、GraphRAG、LLM Wiki；不改变 chunk/neighbor/candidate generation。

基础 M2 已具备进入 TON Multi-source Validation 的质量条件；但 Multi-source 应在 Product Owner 确认上述 remote Top20 / latency / cost trade-off 后，以选定的正式 baseline 运行，避免又更换检索路径导致结果不可比。

## 8. Verification

- Offline full suite：`377 passed, 5 skipped`；5 个 skip 为未启用真实 provider 时的 live gates。
- 显式配置 DeepSeek 后的 live answer gates：`5 passed`。
- 新增质量 focused suite：`24 passed`；lint 与 diff whitespace 检查通过。
- 最终 production file hashes 与 reranker receipt、generic stability record 一致；配置、原始 validation 数据和结果均位于 Git ignored 路径。

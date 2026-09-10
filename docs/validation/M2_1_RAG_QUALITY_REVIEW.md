# M2.1 RAG Quality Fix — Product Review

2026-09-10 · **实现与实验已完成，但质量验收尚未全部通过。M2 不 Frozen。**

## 结论先说

答案已经从“复制第一条引用”变为“读取有限证据、逐项检查所需事实、输出可核查 claims”。这使原 TON 集的严格完整答案从 **6/28 提高到 21/28**。新的、文档不重叠的 TON holdout 为 **18/22**。

但不能说没有 regression：原集跨语言 Recall@5 从 **55% 降至 45%**，一题从部分回答变成拒答；另外单独检查原 generic 集发现 outdated-only 的稳定退化和 release 回答不稳定。建议先关闭这些基础质量缺口，再做受控 reranker 实验；现在不加入新组件、不 Frozen。

## 1. 本轮实际改了什么

1. **证据进入答案**：selected chunks 与同 revision 的 ±1 neighbor 先组成有限 evidence packet；模型列出问题所需 facts、支持/缺失情况与对应引用。回答由通过校验的 claim list 组成，不再复制首条摘录。
2. **相关不等于能答**：词法/向量分数只用于检索。`TBD`、不含具体数值的介绍、一般性诊断知识不再自动证明用户的具体说法。模型未配置、失败或引用不合法时明确降级。
3. **移除窄带二次过滤**：原 coverage/cosine 的多个 heuristic 窄带不再删除已被 RRF 找到的证据。仍保留必要 official/time policy，但其 active-first 历史场景缺陷尚未解决，见下文。
4. **结构参与检索**：title、heading hierarchy/current section（含 FAQ 问题、release/version heading）与正文一起进入词法/embedding 索引；引用原文不被拼接污染，原 chunk text/ordinal 保留。

参数保持 `structure-v1 / 180 max tokens / 30 overlap / ±1 neighbor`。没有扩大 chunk，没有 rewrite、reranker、multi-query，也未引入 GraphRAG、LLM Wiki、LangGraph 或任何 connector。

按 Ponytail 复用原 service、SQLite/FTS、local embedding、cache 与 validation runner；没有新依赖或第二套产品架构。新增的答案接口是显式配置的单次 JSON completion，不是 Agent。

## 2. 实验隔离与样本锁定

| 集合 | 文档 | Queries | 用途 |
|---|---|---:|---|
| TON 原 external → regression | 原 10 篇、662 chunks | 34；可回答 28 | 与旧结果逐题比较，原 query/gold/rubric 字节不变 |
| TON unseen holdout | 新 8 篇、497 chunks | 28；可回答 22 | 先锁文档、再设计新题，封题后只运行一次 |
| Generic development | 原 generic-knowledge-fixtures-v1 | 12 | 补充保底，单独报告；不是 external holdout |

两套 TON 数据同属 [TON 官方 Docs repository](https://github.com/ton-blockchain/docs/tree/0e5a346d1e69a5345d333be669576acf21c6b93a)，固定 commit `0e5a346d1e69a5345d333be669576acf21c6b93a`。文档许可证 [CC-BY-SA-4.0](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/LICENSE-docs)，代码片段 [MIT](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/LICENSE-code)。原始/解析正文与模型完整输出只在 Git ignored 本地目录，不提交仓库。

Holdout 的新文档是 Simplex 长文、Wallet V5、wallet mnemonics、address derivation、TON Center API v2、wallet history、TON Connect core concepts、MyTonCtrl overview，合计 120,226 原文 bytes。覆盖长篇、技术层级、历史版本、操作文档、表格/代码、相邻事实。它是 **document-disjoint，不声称同项目事实完全不重叠**。

- Holdout corpus 在读取正文前按路径/尺寸固定；`retrieved_at=2026-09-10T05:50:29.172760+00:00`。
- Holdout 28 题：EN 18、CN 5、ES 5；含 direct、paraphrase、noisy、跨语言、多事实/邻块、insufficient、完全无答案、历史拒答诊断。
- Holdout query SHA256：`996a6e47ed2e671ff3160767e2961544e9f35ea52f370ce5c67c1789e262945c`。
- 原 34 题 SHA256：`e05e26672a7847de9a411902ff5ea1707a5de9f6e84e1f712562b4fe0593241b`。
- Regression：06:05:04–06:06:37 UTC；holdout：06:09:12–06:10:26 UTC。同一产品代码、同一参数，receipt 校验代码未变。
- Gold 由本 agent 在源文档阅读后独立于检索结果制定，评分由本 agent 对照固定 rubric；**不是独立人工评审组**。未按结果改题。

来源没有足够的精确 publication/effectivity 历史，因此仍以 retrieved_at 作隔离实验的 system-derived availability proxy。T32/H28 只证明“不拿未来快照回答过去”，不能据此声称历史事实准确率。没有把这些代理时间写回真实用户 Knowledge。

## 3. 实际指标

Recall 为 gold chunk 的 macro Recall@5，不是“有没有碰到一篇相关文档”；MRR/nDCG 同样按原标注计算。Answer 完整度单独按原 rubric，不能用 returned status 代替。

| 指标 | 原 TON baseline | M2.1 同 34 题 | 新 holdout |
|---|---:|---:|---:|
| Recall@5 | 53.6% | **72.6%** | **76.5%** |
| MRR@5 | 0.500 | **0.680** | **0.807** |
| nDCG@5 | 0.460 | **0.668** | **0.754** |
| Cross-language Recall@5 | 55.0% | **45.0% ↓** | 77.1% |
| 严格完整答案 | 6/28（21.4%） | **21/28（75.0%）** | **18/22（81.8%）** |
| 不完整却标 grounded（严格口径） | 19/25 | **3/24** | **2/20** |
| Insufficient accuracy | 2/3 | **3/3** | **3/3** |
| No-answer status accuracy | 0/2 | **2/2** | **2/2** |
| 已展示 retrieval citation 完整性 | 98/98 | **165/165** | **135/135** |
| 已展示 claim quote 原文校验 | 无此链路 | **92/92** | **77/77** |
| 应能回答却拒答 | 4/28 | 4/28 | 2/22 |

严格 false-grounded 口径把缺少 rubric 明列细节也算失败，不仅指捏造事实。本轮 residual 的 3+2 题均为遗漏，未在人工核对中发现其已输出事实与引用矛盾。部分遗漏属于 rubric 超出字面问题的附加细节（T02 拆批建议、T03 校验前 34 bytes），仍保留原严格分数，没有为了好看修改 rubric。**逐字引用合法不等于答案完整或语义一定正确。** T07 有生成引用未通过校验而被拒答，并不意味着模型原始引用 100% 正确。

语言分项更能说明限制：

| 可回答子集 | 原 Recall → 新 Recall | 新完整答案 |
|---|---:|---:|
| Regression EN（18） | 52.8% → 88.0% | 14/18 |
| Regression CN（5） | 30.0% → 30.0% | 2/5 |
| Regression ES（5） | 80.0% → 60.0% | 5/5 |
| Holdout EN（14） | 76.2% | 12/14 |
| Holdout CN（4） | 87.5% | 4/4 |
| Holdout ES（4） | 66.7% | 2/4 |

ES 有些直接 gold hit 下降，但邻块补齐了正确证据，答案反而完整；不能把 Recall 与 Answer 合成一个分数。样本很小、模型一次运行，holdout 较好也不能抵消原 CN 的失败。

## 4. RRF 受控消融

固定原 body-only 索引、原 query、原 lexical/semantic candidates 与分数，只替换 post-RRF selection；没有混入新结构表示或答案模型收益。

| 路径 | Recall@5 | MRR@5 | nDCG@5 |
|---|---:|---:|---:|
| Current pipeline（原窄带 filtering） | 53.6% | 0.500 | 0.460 |
| Raw RRF | 58.3% | 0.580 | 0.539 |
| RRF + necessary metadata | 58.3% | 0.580 | 0.539 |

这支持删除原二次 relevance 窄带。必要 metadata 在当前可回答样本不损害排名，并正确排除历史诊断中的未来资料；**不代表它已经通过所有历史/过期场景**。新的结构表示 + 同一必要 policy 到 72.6%，是第二项变化，不能全算作删 filter 的收益。

权威消融记录保存在本机 ignored 的 `docs/validation/m2-1/post_rrf_ablation_controlled.json`。首次离线计算 `post_rrf_ablation.json` 还改动了并列分数排序，属于 tie-confounded 探索，保留本机审计但不用于上述结论；受控版本严格保持原并列顺序。

## 5. 成功、残余 failure 与 regression

主要修复：T04/05 的正确依据不再被二次过滤移除；T10/11 能回答口语错误场景；T14/19/20 能用英文章节回答中文/西语；T23/24/25 能组合原因、数量或前后关系；T27 的 TBD、T28/29 的证据不足、T30/31 的无答案都正确处理。原来的 6 条完整答案全部保留。

新 holdout 的 H07（认证方法 + gasless 原因）、H13（V2 safeguard + exit code）、H16（空候选的三项事实）成功，说明不只对原题有效。

| 残余类型 | Cases | 实际原因 | 不应误加的能力 |
|---|---|---|---|
| 正确 candidate 排名不足 | T12、T13、T15、T17、H03 | 已入候选集，但 RRF 排 7–14；不能进入前 5 或足够邻块 | 不是“根本没找到”，不优先 rewrite |
| 跨语言融合排序 | T13/15/17 | 正确块 semantic 分别第 2/3/5，RRF 却第 7/8/10；双通道弱相关候选挤掉单通道强相关候选 | 不加项目词表，不调题 |
| 生成引用失败 | T07 | 正确步骤已排第一，至少一条模型引用不满足原文检查，降级拒答 | 不是 chunk 小或召回差 |
| Answerability 过度分解 | H18 | 只问 dry-run option，模型却要求本机实际 env values；正确 --print-env 块已排名第一 | reranker 无法修复 |
| 完整性遗漏 | T02/03/12、H20/22 | 没覆盖严格 rubric 全部细节；其中一些是辅助说明，另一些是 context 未进入 | 不把 grounded flag 当评价 |

T07 从旧 partial → abstain，是明确 answer regression。直接 gold Recall 下降的两题是 **T13、T22**；T22 由邻块补齐且答案改善，T13 仍未解决。完整逐题前后对照见 [34 题 paired comparison](m2-1/REGRESSION_COMPARISON.md)；每题 query、expected source/section、actual Top-K、BM25、semantic score/rank、RRF score/rank、returned status 与原因见 [regression casebook](m2-1/regression/CASEBOOK.md)、[holdout casebook](m2-1/holdout/CASEBOOK.md)。

### 单独的 generic 回归警报

原 development fixture 单一 180/30/±1 配置的首轮状态正确率为 **10/12**，不是完整答案率：

- `legacy_batch_outdated`：预期 outdated_only，实际 insufficient。相同代码的诊断复跑仍失败；active-first 把相关过期资料挤出 Top-K，模型只看到弱相关当前资料。这是需要关闭的 metadata-policy regression。
- `release_fix`：首轮 insufficient，诊断复跑 grounded，候选始终正确。存在回答判断/引文生成不稳定；首轮结果保留，不用复跑替换。
- 自然语言 conflict、insufficient、no-source 在这一 curated 检查中通过；不能拿少量 curated 样本代表真实多来源质量。

上述仅保存在独立的 generic 补充记录，不合并进 TON 指标。TON Docs 仍未覆盖真正具备发布时间/生效区间的冲突与历史事实链，因此不报告真实 conflict/historical accuracy。

## 6. 是否应加新组件

**暂不加 rewrite / multi-query。** 两套外部集的每一个可回答问题都至少有一块正确 gold 进入 RRF 前 20：28/28 与 22/22。部分替代 gold 没进入候选池，但没有“整道问题的正确 candidate 全丢失”的证据。

**有足够证据提出 reranker 实验，但没有证据直接上线它。** 例如 T13/15/17 和 H03 正确证据已在候选集，排名不足。建议下一次经 review 后，用同一候选池对照原 RRF 与一个 multilingual reranker，报告 Recall/MRR、完整答案、false-grounded、时延与成本。不能用本轮 holdout 再调参数并继续叫它 unseen；下一轮需另留未用验证集。

**不扩大 chunk / overlap。** 回归 7/7、holdout 5/5 显式多单元题的必要 context 已齐全；邻块确实救回 T18/T22/H01/H12。仍缺上下文的主要根源是选择/排名，不是已证明必须增大 chunk。先处理 outdated-only、过度分解与引文稳定性，再评估 reranker；不先扩 scope。

## 7. 验收与尚未完成

| 合同 / PRD | 本轮证据 | 状态 |
|---|---|---|
| FR-KB-001 provenance | 原 text/ordinal 保留；source/revision/chunk 与邻块引用可打开 | 通过本轮 integrity 检查 |
| FR-KB-002 可核查项目事实 | 真实 provider 输出多事实 claims 与原文引文 | 实现；质量未全通过 |
| FR-KB-003 conflict | domain 双来源校验 + curated 真实模型 case | 有限验证；真实 multi-source 未做 |
| FR-KB-004 outdated/historical | future abstention 正确；generic outdated-only 退化 | **未通过** |
| FR-KB-005 无权威/不足 | 两套各 3/3 insufficient、2/2 no-answer | 本轮通过，N 很小 |
| Incremental indexing | 同 revision 不重复；新 representation 单独 cache；reindex 不改变原文/ID/hash | 自动测试通过 |
| Product Review Surface | facts、缺项、支持 quotes、邻块、metadata 与 explicit reindex | 可人工操作 |

未完成或降级：稳定的语义覆盖/引用生成、完整跨语言 Top-5 质量、上述过期 policy、真实历史有效性验证。模型不配置时只提供检索与保守降级，不宣称 grounded。扫描 PDF/OCR、自动 crawler、rewrite/reranker、多源 external validation 仍未实现。

测试：**372 passed，4 个默认跳过的真实 provider 测试另行显式运行 4 passed**；受影响代码 lint 通过。单元测试全部通过不覆盖前述 benchmark 失败。

## 8. 如何亲自 review

本轮已启动新版本：[Knowledge Review Surface](http://127.0.0.1:8893/internal/knowledge-review)。旧 8892 进程保留，避免中断你的原 review。

从 Workspace → Add Source → Metadata/Index → query → Material facts / coverage → supporting quote → original chunk，完成整个链路。页面显示 remote snippets 边界。旧 sources 若显示 reindex_required，打开 metadata，对对应 revision 点击 Reindex；不自动改旧原文。另有 `M2.1 Review Smoke (synthetic)` Workspace 供检查两秒/三次 retry 和 TBD 费用，不是 TON benchmark。

本轮实际浏览器验收已完成：创建该 synthetic Workspace、添加资料并完成索引、两项 retry 事实回答为 grounded、打开第二条支持引用查看原始 chunk；再问具体 processing fee，页面显示 insufficient_evidence、缺失的金额/单位以及原文 TBD。此 UI smoke 不计入 TON 指标。

需要重启时，在 active workspace 运行：

```sh
export COMMUNITY_INTELLIGENCE_LLM_CONFIG="$PWD/data/generated/local-llm-config.json"
PYTHONPATH=src .venv/bin/python -m community_intelligence.cli serve \
  --knowledge-review --port 8893 \
  --semantic-model-dir data/generated/models/paraphrase-multilingual-MiniLM-L12-v2-e8f8c211
```

密钥只在本机 ignored 配置中，不在报告/Git。Provider 固定 HTTPS endpoint；一次请求无工具执行、无重定向、无整库上传。外部两次实验共 60 次模型调用，实际单题原文 evidence 最大 5,668 / 6,857 字符，低于 20,000 上限；配置和返回模型名、usage 均在 receipt，密钥未记录。生成式模型即使 temperature=0 仍可能波动，generic release 的复跑已说明这一点。

本轮停在 Product Review。**不进入 Multi-source、不进入 M3、不 Frozen M2。**

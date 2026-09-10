# TON Docs External Validation — M2 baseline

## Executive Summary

本轮已完成，结论是 **M2 暂不适合 Frozen**。真实官方文档中的一些证据可以找到，也能追溯来源，但从证据到完整答案的链路明显不足。建议优先修复通用的证据使用和答案状态判定，再讨论是否需要新增检索组件；本轮没有实施这些优化，也没有进入 M3。

34 条新问题中，28 条有可验证答案。最终 Recall@5 为 **53.57%**，MRR@5 为 **0.500**；按事前 rubric 严格审读，完整答案为 **6/28（21.43%）**，另有 7 条部分回答、11 条答非所问、4 条拒答。98/98 citation 均能追溯，但 citation 有效不等于事实回答正确。

这不是 generic-knowledge-fixtures-v1 的延伸或合并分数。它是单独的 `ton-docs-external-v1 / baseline-run-1`，问题和答案标准在第一次检索前锁定。问题及审读由当前 agent 完成，**尚未经过独立人工标注；以下 Answer 指标应作为待 Product Owner 复核的外部验证结果**，不是线上用户准确率。

## 1. 我们用了哪些真实资料

来源为 [TON 官方 Docs GitHub repository](https://github.com/ton-blockchain/docs)。[固定版本 README](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/README.md) 说明文档位于 `content/`，正文适用 CC BY-SA 4.0，代码片段适用 MIT。原始许可证与作者信息已本地保留；未下载图片、视频、外部链接页面，没有运行该仓库中的任何代码。

- Repository URL: `https://github.com/ton-blockchain/docs`
- Commit SHA: `0e5a346d1e69a5345d333be669576acf21c6b93a`
- Sample selected: `2026-09-10T05:09:46Z`
- Retrieved at: `2026-09-10T05:11:10.350330+00:00`
- Queries designed: `2026-09-10T05:13:54Z`
- First experiment: `2026-09-10T05:17:33.653990+00:00` → `2026-09-10T05:17:51.076131+00:00`
- Corpus lock SHA-256: `8e2f3e7b935ca33417483c89ca426d6fb39f7baf362acae9d46b09f3a10e58e5`
- Query SHA-256: `e05e26672a7847de9a411902ff5ea1707a5de9f6e84e1f712562b4fe0593241b`

按路径、大小和结构做目的性分层抽样，**不是全库随机抽样**，也不是先拟问题再挑文档。10 份英文文档总计 178,921 bytes，当前 parser 输出 662 chunks、24,172 个含 overlap 的 whitespace tokens。

| Sample key | 原始路径（均位于固定 commit 的 content/ 下） | 结构 | Chunks |
|---|---|---|---:|
| catchain | foundations/whitepapers/catchain.mdx | 约 96 KB legacy 白皮书、形式化推导 | 215 |
| connect | applications/ton-connect/overview.mdx | Product Docs、链接与 bullets | 17 |
| faq | applications/ton-connect/faq.mdx | 问答 | 18 |
| troubleshooting | applications/ton-connect/troubleshooting.mdx | 多层 heading、错误码、代码、操作步骤 | 60 |
| addresses | foundations/addresses/formats.mdx | 格式定义、编号列表、表格 | 31 |
| highload3 | contracts/standard/wallets/highload/v3/specification.mdx | 长技术文档、嵌套 heading、表格、相邻步骤 | 163 |
| highload2 | contracts/standard/wallets/highload/v2/specification.mdx | 明确 Deprecated 的 legacy contract | 68 |
| wallet_comparison | contracts/standard/wallets/comparison.mdx | 跨钱包对比表、使用场景 | 31 |
| shards | foundations/shards.mdx | 分片、拆分/合并、技术解释 | 23 |
| whitepaper_comments | foundations/whitepapers/comments.mdx | 对旧设计的更正、未实现能力 | 36 |

MDX 通过现有 **Manual Official Source** 路径作为 UTF-8 文本传入；未增加 `.mdx` 正式 importer，没有去掉 frontmatter、执行组件、展开 imports 或追踪链接。该结果衡量的是现有纯文本路径面对真实仓库文档的表现，不是渲染后网页的表现。MDX 中的 heading、代码和 component markup 对 baseline 的影响也保留下来了。

10 份原始正文、许可证、SQLite、embedding、解析结果及完整返回文本均在 Git ignored 的 `data/generated/validation/ton-docs-v1/`；Git 可见文件仅为评测程序、manifest、问题、摘要指标和不含正文的 failure casebook。本轮没有提交 Git。

## 2. 问题覆盖与指标口径

本轮配置原封不动：`structure-v1`、180 max whitespace tokens / 30 overlap、±1 neighbor、每个 hit 至多 4,000 chars context；FTS5 BM25 + multilingual embedding（各取 20 候选）+ RRF（k=60），最终 Top-5；`authority-validity-recency-v1` / `sqlite-fts5-rrf-v1`。实际 embedding 为 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`，复用已有本地模型，非测试替身。

34 条问题：EN 24、CN 5、ES 5；其中可回答的英文问题为 18 条，CN/ES 各 5 条。类型是 direct 6、paraphrase 3、口语/噪声 3、长文档 2、legacy 1、跨语言 10、显式相邻语义块 3、insufficient 3、完全无答案 2、历史边界诊断 1。标签互斥计数；另有 7 条题目的完整答案需要多个 evidence units。

Retrieval 指标只在 **28 条有答案题** 上计算。Gold 是事前标注的 `source-key:chunk-ordinal`，包含部分等价答案块；Recall@5 是命中 gold chunk 比例的逐题平均，不是“有一块命中即算全对”。同时给出 any-hit，避免误读。MRR 截断于前 5；nDCG 使用 binary relevance、IDCG 按每题 gold 数量截断于 5。有限 gold 不是全库穷尽式相关性标注，漏标风险需人工复核。

Answer 单独按事前 rubric 审读实际 `answer`：必须完整回答用户请求的 material facts；仅在 citation/context 里存在答案不能算实际 answer 完整。历史题不计入通常的 28 条 retrieval/answer 指标，也不计入真实历史准确率。没有通过修改问题或宽松 rubric 抬分。

## 3. 实际表现：可追溯性成立，完整回答明显不足

| Retrieval（28 条可回答题） | 首轮结果 |
|---|---:|
| 最终 Recall@5 | 53.57% |
| 最终 MRR@5 | 0.5000 |
| 最终 nDCG@5 | 0.4598 |
| 最终至少命中一块 gold | 18/28，64.29% |
| 原始 RRF Top-5 Recall（后处理前） | 58.33% |
| 原始 RRF MRR / nDCG | 0.5804 / 0.5388 |
| 原始 RRF 至少命中一块 gold | 19/28，67.86% |

这不是一次消融实验：同一轮记录了 RRF 排序前后不同阶段，**后处理会丢失部分原本排在前面的正确证据**。不能用这些数值宣称“删除 policy 已验证提升”；没有运行修改版。

| 查询语言 → 英文文档 | N | Recall@5 | MRR@5 | 至少命中 | 完整答案 |
|---|---:|---:|---:|---:|---:|
| EN | 18 | 52.78% | 0.5741 | 12/18 | 5/18 |
| CN | 5 | 30.00% | 0.2667 | 2/5 | 0/5 |
| ES | 5 | 80.00% | 0.4667 | 4/5 | 1/5 |
| CN+ES | 10 | 55.00% | 0.3667 | 6/10 | 1/10 |

样本太小，且语言组的问题组合不完全相同，不能推论西语普遍优于中文。它足以提供具体的跨语言失败案例，但不是语言能力排行榜。答案语言仍是英文摘录；这里不测译文流畅度。

| Answer / Grounding | 首轮结果 | 含义 |
|---|---:|---|
| Citation validity | 98/98，100% | ID、revision、正文、section、固定 commit URL、neighbor provenance 一致；不代表 entailment |
| 完整 grounded-answer accuracy | 6/28，21.43% | 按事前 rubric；另有 partial 7、wrong 11、abstain 4 |
| 仅 grounded 状态匹配 | 24/28，85.71% | **不是答案准确率** |
| 返回 grounded 后实际完整 | 6/25，24.00% | 25 条 grounded 输出含 1 条不应回答的精确 gas 问题 |
| No-authoritative-source 状态正确率 | 0/2 | 两条都安全拒答，但错误标为“相关资料不足” |
| Insufficient-evidence 状态正确率 | 2/3，66.67% | gas TBD 题错标 grounded |
| 无充分答案题安全拒答 | 4/5，80% | 与状态分类正确率分开 |
| 多块所需证据完整进入 context | 6/7，85.71% | 此 7 题实际完整答案 0/7 |
| Historical truth / conflict accuracy | Unavailable / not evaluated | 缺精确可信时间线；本轮没有预注册 conflict query |

## 4. 成功和失败具体是什么

完整成功：T01 主网/测试网 chain ID；T06 legacy BCP Byzantine 假设；T08 普通 dApp 是否自建 bridge；T21 西语桥接重试间隔；T26 legacy genesis identifier；T34 treasury shared custody。T28/T29 分别对没有 SLA 赔偿依据、不能凭文档断定某一交易失败原因正确拒答。

最值得 Product Review 的失败：

- **T03 / T20：找到了 CRC16，却回答 Luhn 类比。** 正确内容已在 citations；用户问算法和字节数，answer 没给出。不是 citation 无效。
- **T04 / T05：正确证据被后处理移除。** set_code 留一个 slot、codepage 0 都曾在原始 RRF 第 4，但最终没保留。
- **T24：问 36 bytes 如何分配，只返回“有以下组成部分”。** 1/1/32/2 的列表在相邻 chunk、Top-K 和扩展里，却未进入 answer。
- **T25：拆分 p→p0/p1，再合并回 p。** 两块就是 RRF/最终排名 1、2，系统仍拒答。它不能用“没有检索到”解释。
- **T02 / T15 / T16：真正的候选召回失败。** maxMessages 未进 20+20 候选池；中文 codepage 的正确段落语义第 143；中文 bit_number 问题被 query ID 总容量带偏。
- **T27：gas 表写 TBD，仍返回 grounded。** 未编造一个具体 gas 数字，但“已有证据支持精确回答”的状态是错误的。
- **T30 / T31：完全无关问题被泛词命中。** 虽然拒答，没有区分“官方资料根本不相关”和“相关但不足”。

全部 34 条（包括成功）见 [逐条 Casebook](ton-docs-v1/CASEBOOK.md)。每条保留 original query、expected source/section、actual Top-K、BM25、semantic score/rank、RRF score/rank、返回状态及审读原因。完整 UUID、revision 和 text hash 只保存在本机 ignored 的 `data/generated/validation/ton-docs-v1/baseline-run-1/results.json`；未将真实文档正文或机器生成的完整结果提交 Git。

## 5. 根因：当前实现不只是一个待调参的 hybrid retriever

以下解释由实际轨迹和产品代码共同支持，尚无修改后的对照实验。

1. **Evidence 被获取，但未用于完整答案。** 当前 grounded answer 只复制第一条 citation 的 `text`，并不消费返回的 bounded neighbor context。10 条问题的首要失败归为答案选择/不完整；不是 10 条都检索失败。
2. **“相关”被当作“足够证明”。** grounded 使用词覆盖 ≥0.5 或语义相似度 ≥0.55；这既会误放行精确 gas 题，也会拒绝已有完整拆分/合并证据的题。降低阈值会使 false grounded 更危险，不能只朝一个方向调阈值。
3. **RRF 后还有较强的内容分数筛选。** 实现使用 `max(term_coverage, semantic_similarity)`，再保留接近最高分的窄带候选，最后的排序也不是单纯 RRF。即使来源权限、时间都相同，仍会把正确 RRF 高位结果挤出。要先审计这层筛选，而不是直接加第二个 reranker。
4. **Heading/结构信息没有充分进入检索文本。** `section` 单独保存，但不随正文进入 lexical/embedding；深层 parent_heading 只保存最近 heading。FAQ 的问题、错误码和 TVM 上下文经常留在标题里，短答案正文缺少检索线索。662 chunks 中有 129 个不足 10 whitespace tokens；列表引导句和列表、Callout/代码等也会按空行分开。
5. **时间元数据不足不是检索器能够补出来的。** legacy 标签和日期级备注存在，但不能确定精确的 offset-aware publication/effective timestamps。语义模型不能替我们发明这些事实。

原始正文共有 19 个重复 chunk text（662 chunks / 643 unique texts）；这些在代码/套话里可能正常，原文未去重改写。Embedding cache 按内容复用，运行中没有偷换成英文专用模型或 lexical-only。参数里的 token 实际是 whitespace count，不是模型 tokenizer token；真实 local provider 自己处理其 128-token 输入边界，首次模型加载的长度警告未造成执行失败。

## 6. 优化建议：先解决通用正确性，不直接叠组件

| 候选动作 | 本轮证据 | 建议 |
|---|---|---|
| 正确消费 bounded evidence、区分可回答/不完整 | 6/7 多段题 context 已足够，完整答案 0/7；T27 false grounded | **优先提交 M2 修复方案**；仍限定通用证据→答案链路 |
| 审计 RRF 后 relevance 筛选、保留完整 heading 上下文 | T04/T05 高位结果被删除；T02/T10/T15 标题信息缺失 | **值得做受控对照实验**，先不加新依赖 |
| Query rewrite / multi-query | T02/T15/T16 真正候选 miss，口语 T10 还混合了 heading 丢失 | 有候选 failure case，但**尚未证明 rewrite 稳定有效**；先修结构/后处理，再在同一问题集和新 holdout 比较 |
| Reranker | 多个正确块原始 RRF 已在前列；低排名案例也存在 | **暂不引入**。只有排除后处理损伤后仍持续低排名，再比较 |
| 增大 chunk/overlap/neighbor | 存在引导句/列表断裂，但多数多段证据已能扩展到 | **不支持盲目扩大**；先保持 180/30、±1，验证结构保留与 context 使用 |
| Query-sensitive authority / recency routing | 旧源被无关问题命中，但没有真实发布时间对照 | 本轮证据不足以证明复杂 routing 必要；先补真实 metadata 和正确 status 语义 |

所以不是“baseline 已足够，无事可做”，也不是“已经证明必须加 rewrite/reranker”。建议保持当前 baseline 作为不可覆盖的对照，在 Product Owner 批准后，用最小通用修复验证上述原因。任何方案变化均尚未实施。

## 7. 是否值得做第二轮 TON Multi-source

**值得，但建议先修复并复测当前 evidence→answer 链路，再做第二轮。** 否则新增 Medium/Release/Announcement 只会增加噪声，难以判断是来源冲突还是当前答案机制失败。

第二轮的价值应是不同来源的权威关系、更新/更正、可证明的时序与真正的冲突；不是扩大同类英文 docs 数量。继续采用手动、固定 corpus 的 validation 输入，不新增 crawler/connector。逐份核对官方身份、再利用许可和发布时间证据；如果仍只有日期，不声称已验证同一天公告先后。

## 8. 时间、许可与外推限制

`published_at` 与 `effective_from` 在现 contract 中必填，但样本缺乏真实精确值。本轮仅在隔离评测数据库中，用 retrieved_at 作为 **system-derived snapshot availability 代理**，所有问题默认在这个边界之后。原始时间未知的事实明确留在 manifest/provenance 中；这不是官方发布时间或真实事实开始生效时间，不写回用户 Workspace。

T32 的 2024 历史问题只检验“当时没有可证明来源时是否避免用后来资料作答”。结果 `outdated_only` 表明 baseline 把未来未可用、过去已过期都归为 inactive。**没有输出 2024 的肯定事实，但也不能正确表述时间边界。真实 historical accuracy 仍然 unavailable。** 文档里的 2020-02-19 和 2026-04-09 是日期级文本，没有擅自补午夜/UTC。

许可依据是固定 README 和 LICENSE-docs / LICENSE-code 的声明；不是对每个第三方嵌入内容的权利核验。没有遇到本轮文本本地验证必须绕过的访问限制。以后分享正文或改编材料时，仍需保留 attribution、许可证及修改说明，并核对适用的 ShareAlike 条件；不将 TON 名称或公开仓库理解为对本项目的背书。

其他边界：单仓库、10 文档、小样本、agent-written gold、一次无调参实验；不是 TON 全库能力、真实运营收益、独立测试团队成绩，也不证明不存在其他 failure。未来优化若使用此 set，它将成为已见 regression set，需要另设 holdout。没有同一提交的 MD/PDF 内容转换对照，没有测未展开的 snippet 内容，也未验证 M2 的 PDF 路径。

## 附录：复核与复现

本轮没有更改 `src/`、正式 KnowledgeSource、Telegram importer、PRD、Technical Design 或 M2 参数，没有安装依赖，也没有启用 remote LLM、LangGraph、GraphRAG、LLM Wiki 或 connector。按 Ponytail 复用实际 KnowledgeService 与现有本地 embedding provider，仅增加 validation-only runner；Data Quality / Validate Data 技能用于分母、来源和答案完整性核对。另用报告技能的现有打包器生成本地离线 HTML，不发布到外部；1440/390 宽度、内容、来源对话框及打包验证已通过。它是报告附件，不是新产品页面。

原始 evidence 目录：`data/generated/validation/ton-docs-v1/`。所有原文和解析内容均被既有 `.gitignore` 覆盖。`prepared/baseline.lock.json` 固定 src 文件、pyproject、uv.lock 的 SHA-256。实验开始/结束及本轮复核均检查这些产品文件未变。独立 notebook 重算 Recall/MRR/nDCG、检查所有原始文件/问题/产品 hash 和 98 条 citation。

从 active workspace 执行（不需要启动正式 UI）：

```bash
PYTHONPATH=src .venv/bin/python scripts/validation/knowledge_external_validation.py docs/validation/ton-docs-v1/corpus.json data/generated/validation/ton-docs-v1 --summarize
```

以上只从首轮已保存 evidence 重建安全结果和 casebook，不重跑或修改 baseline。独立复核见 [verification notebook](ton-docs-v1/verification.ipynb)。要重新进行完整实验，使用同一个已封存 corpus、同一 queries，给 `--run --queries docs/validation/ton-docs-v1/queries.json --run-name baseline-replication-2`；脚本拒绝覆盖已有实验。导入 UUID 的平分 tie-break 可能使完全等分候选顺序变化，因此比较时同时检查稳定的 source-key/ordinal，而非只看 UUID。

Corpus 再获取命令使用 corpus.json 指定 commit，仅取 10 份文本和 README/许可证；已有目录会拒绝覆盖。重新获取会产生新的 retrieval timestamp，不可拿新的 lock 冒充首轮。首轮 lock 和 queries hash 才是本报告的证据版本。

当前状态：**External Validation completed; M2 not Frozen; M3 not started.** 等待 Product Owner 对 failure 审读及后续最小修复范围的确认。

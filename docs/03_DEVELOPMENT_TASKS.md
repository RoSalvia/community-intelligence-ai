# Development Tasks 与依赖顺序

状态：M0 已批准并冻结

原则：每项任务可单独开发、review、验收；未通过前不得把能力标为 Implemented。

## 1. 依赖总览

```text
M0 Contract
  → M1 Data Foundation
      ├→ M2 Knowledge ───────────────┐
      └→ M3 Conversation Intelligence├→ M4 Signal Home → M5 Copilot
                                     │                    ↓
                                     └─────────────────→ M6 Correction
M2 + M3 + M6 → M7 Moderators
M3 + M4 + M6 → M8 Contributors
M2..M8 → M9 Evaluation → M10 Portfolio Demo
```

M2 与 M3 在 M1 后可并行；M7 与 M8 在各自依赖满足后可并行。M9 的测试框架从 M0 开始建，但完整 release gate 要等功能齐备。

## 2. 通用 Definition of Ready / Done

任务 Ready：依赖已验收；product contract 无未决 blocker；输入/输出 schema 与错误状态明确。任务 Done：focused tests 先失败后通过；相关 contract/integration tests 通过；lint/typecheck 通过；方法、限制、fallback、evidence 和版本信息已接入；无 placeholder 冒充能力。

## M0 — Product Contract

### D0.1 冻结 PRD 与接管基线

- 产物：PRD v2.1 副本、旧 commit/test 基线、能力矩阵、deprecated 清单。
- 依赖：无。
- 验收：PRD hash 可复核；旧目录未修改；新文档明确旧资产不能覆盖新 PRD。
- 状态：PO 已批准并冻结。

### D0.2 冻结 low-fi IA 与核心 flow

- 产物：五主导航、Utility Dock、Home/Conversation/Evidence/Mod/Contributor/Knowledge low-fi 与六条 flow。
- 依赖：D0.1。
- 验收：PRD 指定的所有 P0 surface 均有入口、状态、Evidence route 和 fallback。
- 状态：PO 已批准并冻结。

### D0.3 冻结 domain/API schema v1

- 工作：将 Technical Design 实体与 API 转成 JSON Schema/OpenAPI draft；定义 enums、ID、UTC window、pagination、stale/error contract。
- 依赖：D0.2。Provider 字段保持抽象，不等待 B1。
- 验收：schema contract tests 能拒绝未知字段、无效引用、未引用 claim、非法 correction transition。

### D0.4 在 legacy baseline 上建立新版工程骨架

- 工作：保留当前 Python/frontend/tests 可运行路径，渐进增加分层目录、SQLite migration runner 与新版 CI checks；以 `b5d5d02` 为 legacy provenance。
- 依赖：D0.3。
- 验收：fresh clone 仍可运行 v0.1 baseline；新版 health/shell 可并存；Git history/tag 保留；无业务功能假完成。

## M1 — Data Foundation

状态：Product Review usability items 已解决；M1 已冻结（2026-09-10）。

实现收敛：为首个 vertical slice 只提供持久化数据/API contract，不提前制作将被 Home IA 替换的临时设置页；未发布 schema 暂不维护无真实升级对象的 down migration。

### D1.1 SQLite persistence 与 migration

- 工作：Workspace、Community、SyncBatch、Message、RoleAssignment、AnalysisRun、Watermark tables；WAL/FK/transaction。
- 依赖：D0.4。
- 验收：up/down migration 在临时 DB 可复现；FK/immutable fields/unique hash/window constraints 有测试。

### D1.2 Workspace 与 EN/CN/ES Community 管理

- 工作：create/read/update workspace；配置 name/language/platform/timezone；默认 demo workspace。
- 依赖：D1.1。
- 验收：恰好支持 PRD demo 的 EN/CN/ES；重复/非法 language/timezone 被拒绝；UI 可显示 workspace scope。

### D1.3 迁移 Telegram importer 与匿名化

- 工作：从旧 commit 迁移 parser/security tests；接入 Community/SyncBatch；稳定 message ID、workspace salt、batch 幂等。
- 依赖：D1.1、D1.2。
- 验收：rich text/reply/timezone 正确；raw sender 不落库；重复 batch 不重复写；越界/过大/坏 JSON 无 partial data。

### D1.4 Mod role configuration

- 工作：RoleAssignment effective dates、manual UI/API、role resolution。
- 依赖：D1.1、D1.3。
- 验收：同一用户跨时段角色正确；修改生成审计；未配置时 Mod capability unavailable 而社区分析继续。

### D1.5 Window、freshness 与 since-last-check

- 工作：WindowSpec、baseline window、per-community freshness、user check watermark。
- 依赖：D1.3。
- 验收：since-last-check/24h/7d/30d 的 `[start,end)` 一致；无新增消息返回 No new activity；watermark 仅显式查看后推进。

### D1.6 Analysis job lifecycle

- 工作：queued/running/succeeded/failed、progress、idempotent rerun、process interruption recovery。
- 依赖：D1.1、D1.5。
- 验收：API `202` 后可轮询；失败不发布 partial read model；同 fingerprint 可复用成功结果。

## M2 — Knowledge Base

### D2.1 Knowledge metadata 与 revision store

- 工作：multi-source Source/Revision schema；分离 type/channel；完整 identity/authority/time/version/processing metadata；逐字段 metadata provenance；private artifact store；v1→v2 migration。
- 依赖：D1.1、D1.2。
- 验收：offset-aware timestamp 入库为 UTC 且保留 source timezone；相同内容幂等；新内容生成 revision；旧 revision 不覆盖；关键 AI-inferred metadata 不会自动生效；过期状态计算正确。

### D2.2 MD/TXT/PDF ingestion 与 chunk provenance

- 工作：`.md`/`.txt`/text PDF 与 Manual Official Web Source；document-type-aware `structure-v1`；configurable/versioned fallback token/overlap；parse/index status；扫描 PDF 显式 unsupported。
- 依赖：D2.1。
- 验收：FAQ、Docs、Announcement、Release/Changelog 的语义边界成立；每 chunk 可回到 source revision/section/page；prompt injection 文本仅作数据；坏文件无 partial index。

### D2.3 EmbeddingProvider 与 cache 迁移

- 工作：复用 pinned local sentence-transformer；capability probe；以 content hash + model revision 为键的 cache；不增加第二套 provider hierarchy。
- 依赖：D0.4、D2.2。
- 验收：无网络加载、hash/revision 校验、重复文本 cache hit、provider unavailable 不影响 deterministic 流程。

### D2.4 Hybrid retrieval

- 工作：FTS5 BM25 + embedding rank + RRF；workspace/as-of/authority/validity filters；fine-grained hit + bounded parent/neighbor expansion；top-k contract。
- 依赖：D2.2、D2.3。
- 验收：current/outdated/no-answer/multilingual paraphrase fixtures 报告 Recall@K/MRR/cross-language slice；引用 source/revision/chunk ID 全部可打开；整份文档不会被无界扩展。

### D2.5 Recency/authority/conflict policy

- 工作：versioned lexicographic policy、historical `as_of_time`、active/outdated selection、显式 supersession 与 conflict candidate detection、五类 answer status。
- 依赖：D2.4。
- 验收：查询历史时不会被当前资料反向覆盖；冲突并列显示；仅过期来源返回 outdated_only；相关但不足返回 insufficient_evidence；无可靠来源返回 no_authoritative_source。

### D2.6 Generic fixture pack 与 RAG evaluation

- 工作：EN/CN/ES、七类文档、结构/同义/历史/冲突/无答案/prompt-injection fixtures 与 Golden Queries；可复现 evaluation runner。
- 依赖：D2.2–D2.5。
- 验收：分别报告 retrieval 与 answer metrics，记录 dataset/config/model/chunk/index versions；没有 benchmark failure evidence 时不加入 rewrite/reranker/multi-query。

### D2.7 Knowledge Review Surface

- 工作：internal Knowledge 页面串联 add source、metadata/revision、parse/chunk/index status、query/as-of、五类 answer status、citation/source/chunk provenance。
- 依赖：D2.1–D2.6。
- 验收：Product Owner 可只通过页面完成完整 M2 flow 并人工构造 current/outdated/conflict/no-authoritative/insufficient；页面只调用 `/api/v1/*`，不包含独立业务逻辑。

### M2.1 — RAG Quality Fix（稳定性补充完成）

- 已实现：D2.3/4 structure representation + incremental reindex；移除无收益 post-RRF relevance 窄带过滤；D2.5 显式 LLM 的 material-fact assessment + 引用校验 + 本地降级；D2.7 页面展示 facts/coverage/支持 chunk。
- 已验证：原 34 条 TON queries/gold/rubric 未改的 regression；8 篇新文档先封存后锁定 28 题的单次 holdout；current/raw RRF/必要 metadata 的候选固定消融。见 `validation/M2_1_RAG_QUALITY_REVIEW.md`。
- 已闭合：outdated-only active-first regression、H18 answerability over-decomposition、非法 quote 单次 repair；generic 12 题连续三轮 answer status 12/12，release/outdated 均稳定。
- Controlled reranker：固定同一 Top20、query/gold/rubric、180/30、±1 与 answer pipeline；Recall@5 74.3% → 98.7%，完整答案 43/50 → 47/50，无 retrieval 或 safety-status regression。详见 `validation/M2_RAG_STABILITY_AND_RERANKER_REVIEW.md`。
- Product decision：是否接受显式 remote profile 每题多一次调用、Top20 bounded snippets、约 +2.31s 中位延迟；接受后再接入正式 path，失败/未配置回退 RRF。
- Stop：M2 尚未 Frozen；未进入 TON Multi-source 或 M3。

## M3 — Conversation Intelligence

### D3.1 迁移 deterministic rules/reply/hygiene/activation

- 工作：按模块迁移 v0.1；适配 DB/window/EvidenceRef；保留 deterministic regression fixture。
- 依赖：D1.5、D1.6。
- 验收：旧 fixture 的核心公式和 evidence 等价；不会修改 source；community-only 正常。

### D3.2 统一 Conversation Evidence service

- 工作：parent/child/time-neighbor context、original/translation/interpretation、related refs。
- 依赖：D1.3、D3.1。
- 验收：任何 message/evidence ID 可取有界上下文；original hash 不变；scope evidence 不伪造消息。

### D3.3 Topic candidate clustering

- 工作：embedding、noise-aware clustering、stability、representatives、cross-language distribution。
- 依赖：D2.3、D3.1。
- 验收：跨 EN/CN/ES fixture 对齐；小样本/噪声输出 uncertain；输入顺序不改变稳定 identity。

### D3.4 Topic canonical naming 与 review

- 工作：bounded representative input、structured name/description、rename、后续 merge contract。
- 依赖：D3.3、LLM provider decision。
- 验收：无模型显示 Unnamed + unavailable；有模型时未知 ID/无 evidence name 被拒绝；人工 rename 可追踪。

### D3.5 P0 Behavior pipeline

- 工作：8 类 primary/secondary/Uncertain；guardrail 独立；reply context；semantic provider adapter。
- 依赖：D2.3、D3.1、LLM provider decision。
- 验收：EN/CN/ES gold set 输出 per-class metrics；single message 可多标签；无可靠判断 abstain；原 seed rules 仅 baseline。

### D3.6 Conversations UI

- 工作：Topics/Behaviors/Support tabs、filters、compare、Evidence routes。
- 依赖：D3.2–D3.5。
- 验收：Topic/Behavior/Unanswered 可在 3 次主点击内打开原会话；URL 保留 filter；分页不一次加载全 evidence。

## M4 — Signal Home

### D4.1 Trend/fact layer

- 工作：current vs baseline、unique affected users、persistence、support status、role distribution。
- 依赖：D1.5、D3.1、D3.3、D3.5。
- 验收：每个 fact 有 numerator/denominator/window/method；零/小样本不产生无限增长误导。

### D4.2 Risk Signal recipes

- 工作：5 类 risk eligibility/trigger/severity/confidence/dedup/cooldown。
- 依赖：D2.5、D4.1。
- 验收：单消息默认不 High；severity 不接受 LLM 任意值；Potential wording；gold fixtures 可算 precision/recall/FPR。

### D4.3 Opportunity recipes

- 工作：5 类 opportunity 与 contributor hooks。
- 依赖：D4.1。
- 验收：纯 message count increase 不触发；gaming guardrail 可阻断；无可靠 opportunity 返回空。

### D4.4 Community Timeline

- 工作：从状态变化生成 begins/threshold/support 等事件。
- 依赖：D4.1、D4.2。
- 验收：事件有 occurred_at/facts/evidence；不显示原始消息流水；相同 run 可重复生成相同 timeline。

### D4.5 Brief generator

- 工作：BriefInput、LLM JSON prompt、claim/citation validator、fallback。
- 依赖：D4.2–D4.4、LLM provider decision。
- 验收：只输入 structured facts；每个 factual span 可解析；无 LLM 时 cards 可用且 Brief unavailable。

### D4.6 Home UI

- 工作：Brief、最多 5 Need Attention、Opportunities、Timeline、freshness/window。
- 依赖：D4.2–D4.5。
- 验收：Hero 风险可 Investigate/View conversations；空态不声称“一切正常”；页面读性能达目标。

## M5 — Copilot

### D5.1 Tool registry 与 typed results

- 工作：实现 15 个概念工具到 framework-agnostic query services 的映射、schema、scope、result caps；tool contract 不依赖 LangGraph 类型。
- 依赖：D2.5、D3.2、D4.4；Mod/contributor tools 可先返回 capability unavailable。
- 验收：禁止 SQL/path/URL/shell 参数；每个 fact 绑定 evidence/knowledge ref；tool contract tests 通过。

### D5.2 Bounded agent loop

- 工作：在 M5 引入 LangGraph，负责 scope state、dynamic plan、tool routing、checkpoint、max 5、timeout、interrupt/resume；不承载 Community Intelligence domain logic。
- 依赖：D5.1、LLM provider decision。
- 验收：第 6 步永不执行；后续 tool 基于前一步结果；checkpoint 可恢复同一 investigation；provider/timeout 失败 graceful；替换 workflow runtime 不改变 tool result contract。

### D5.3 Final synthesis 与 claim validator

- 工作：固定输出、material claim extraction、citation/ID/causality gates、Suggested Action taxonomy。
- 依赖：D5.2。
- 验收：不存在 ID 被拒绝；unsupported material claim 为 release failure；association 不被写成 causality。

### D5.4 Ask Community / Investigate UI

- 工作：persistent Utility Dock、signal scope、step progress、citation links、mobile full-screen。
- 依赖：D5.2、D5.3、D3.2、D4.6。
- 验收：Evidence detail 返回后 chat 不丢；刷新可恢复 investigation；键盘/移动端可用。

## M6 — Human Intervention

### D6.1 Correction proposal state machine

- 工作：typed action union、intent parse、before/after、impact preview、cancel；LangGraph 在 proposal 后 interrupt，等待显式 human confirmation，再 resume。
- 依赖：D5.3、D0.3。
- 验收：自然语言只创建 pending proposal；interrupt/checkpoint 不等于批准；未 Confirm 无业务实体变化；非法 target/action 拒绝；resume 只能携带显式 confirmation result。

### D6.2 Confirm/apply/audit transaction

- 工作：domain service 在数据库事务中执行 optimistic locking、apply、append-only audit、overlay projection、changed refs；LangGraph 只调用该 service。
- 依赖：D6.1。
- 验收：并发过期 proposal 返回 conflict；原消息不变；before/after/actor/time/reason 完整。

### D6.3 局部 recompute 与 UI receipt

- 工作：transaction 成功后由 workflow resume，触发标 stale、局部重算、query invalidation、chat receipt；checkpoint 不替代 correction audit。
- 依赖：D6.2。
- 验收：Home/target finding 更新；旧 run/audit 可追溯；失败不留下半应用 correction。

### D6.4 扩展 P0 correction types

- 工作：Behavior relabel、Topic rename、Role assignment、Contributor confirm/remove。
- 依赖：D6.2 与对应 domain task。
- 验收：每个 action 有独立 schema/authorization/impact test；Knowledge 不被 chat 静默改写。

## M7 — Moderators

### D7.1 Per-Mod facts/scorecard

- 工作：responsiveness/contribution/groundedness/engagement/anti-gaming 分维度聚合。
- 依赖：D1.4、D2.5、D3.5。
- 验收：每维有分母/window/evidence；无总分/权重/人事结论；无 role 时 unavailable。

### D7.2 Mod Report ingestion/parser

- 工作：raw report、reported topic/issue/action、span evidence。
- 依赖：D3.3、LLM provider decision。
- 验收：原 report immutable；抽取引用 raw span；无模型/低置信返回 pending/uncertain。

### D7.3 Reported vs Observed

- 工作：retrieval/matching 与五种状态。
- 依赖：D7.2、D4.2。
- 验收：只称 Potential Reporting Gap；reported-only 与无 observed evidence 区分；所有 match 可下钻。

### D7.4 Moderators UI

- 工作：Team/Reporting Coverage、scorecard、report input、Evidence/Investigate。
- 依赖：D7.1–D7.3、D5.4。
- 验收：六维完整；无黑盒总分；缺 report 只影响 coverage。

## M8 — Contributors

### D8.1 Contributor feature facts

- 工作：users helped、active days、behavior mix、trend、gaming risk。
- 依赖：D3.1、D3.5、D4.1。
- 验收：Mod/bot 排除；self-reply 不算帮助；facts 有 evidence。

### D8.2 High/Emerging candidate recipes

- 工作：eligibility gates、sustained/rising 分型、why surfaced。
- 依赖：D8.1、D4.3。
- 验收：message volume 不能单独入选；高 filler 可阻断；空结果合法；输入顺序稳定。

### D8.3 Contributor review 与 UI

- 工作：High/Emerging/Reviewed、Evidence、confirm/remove correction。
- 依赖：D8.2、D6.4。
- 验收：why/evidence 完整；review 有 audit；后续窗口可自然退出且历史不覆盖。

## M9 — Evaluation

### D9.1 Gold-set governance

- 工作：匿名/合成 fixture license、EN/CN/ES sampling、annotation guide、split/version/lock。
- 依赖：D0.3、PO data/evaluation decisions。
- 验收：无 train/test leakage；N、语言、类别、abstention 均可报告；真实数据权利明确。

### D9.2 Topic/Behavior evaluation

- 依赖：D3.3–D3.5、D9.1。
- 验收：Topic Recall@K/coherence/alignment/stability/evidence；Behavior macro/per-class P/R/F1/confusion/coverage 达冻结门槛。

### D9.3 Signal/RAG evaluation

- 依赖：D2.5、D4.3、D9.1。
- 验收：Signal precision/recall/FPR/latency/evidence；RAG retrieval/citation/grounding/outdated/conflict/no-answer 达门槛。

### D9.4 Agent evaluation

- 依赖：D5.3、D7.3、D9.1。
- 验收：tool relevance、≤5、citation validity、usefulness；material unsupported claim 达 release gate。

### D9.5 Human productivity protocols/pilot

- 工作：review time、issue lead time、human agreement 的盲测 protocol 与真实 pilot。
- 依赖：D4.6、D5.4、PO pilot access decision。
- 验收：protocol 预先定义样本、baseline、计时、reviewer、排除条件；只有真实执行后填写数值。

### D9.6 Performance/privacy/recovery gates

- 依赖：M1–M8。
- 验收：10k benchmark、UI p95、provider cost、no-secret logs、prompt injection、failed job/correction recovery 均有可复现报告。

## M10 — Portfolio Demo

### D10.1 固定 Hero dataset 与 Knowledge pack

- 依赖：M9 gates。
- 验收：EN/CN/ES、wallet issue、confusion、contributor、Mod、KB conflict/correction 场景可复现且明确 synthetic。

### D10.2 90 秒 Hero 与 3–5 分钟 walkthrough

- 依赖：D10.1。
- 验收：fresh install 后一次命令启动；Home → Investigate → Evidence → Correction 完整；所有 fallback/限制真实。

### D10.3 Release package

- 工作：README、privacy、provider setup、evaluation report、license/notices、built frontend、smoke test。
- 依赖：D10.2。
- 验收：陌生用户可 clone/install/run/understand；full tests/build/demo 通过；未实现项明确。

## 3. 首个可演示 vertical slice

为尽早验证产品价值，M1–M5 不等全部页面完工才联调。首个 slice 依次取 D1.2/D1.3/D1.5、D3.1/D3.2/D3.3/D3.5、D4.1/D4.2/D4.6、D5.1–D5.4，并只实现 CN Wallet issue 的真实 pipeline。它必须使用通用 contract 和真实 Evidence，不得写死 UI 结果；通过后再扩 5 类 risk、opportunity、Mod/Contributor。

## 4. 任务优先级规则

1. 数据与 Evidence contract 先于页面。
2. deterministic facts 先于 LLM synthesis。
3. provider/fallback 与 evaluation fixture 同时落地。
4. 每个新写路径都必须先有 audit/transaction 设计。
5. Deprecated 模块只在主路径稳定后迁移，不得挤占 M1–M8。

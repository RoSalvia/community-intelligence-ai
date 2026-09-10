# Technical Design — Community Intelligence AI MVP v2.1

状态：M0 已批准并冻结，不代表已实现

目标：在复用 v0.1 已验证内核的前提下，落地 PRD v2.1 的 local-first Copilot

## 1. 架构结论

采用 **local-first modular monolith**：一个 FastAPI 进程承载 API、application services、analysis jobs 与 provider adapters；React/Vite 是独立开发、生产时可打包进 Python；SQLite 保存业务状态与审计；私有 content-addressed 目录保存导入源、解析文本和 embedding cache。MVP 不引入微服务、Redis、Celery、Kafka 或独立向量数据库。

```text
React UI
  │  /api/v1 resources + analysis job polling
FastAPI
  ├─ Application services
  │   ├─ Import / Workspace / Knowledge
  │   ├─ Analysis orchestration
  │   ├─ Investigation / Correction
  │   └─ Read models for UI
  ├─ Domain
  │   ├─ deterministic analytics (migrated v0.1)
  │   ├─ Topic / Behavior / Signal
  │   ├─ RAG / Evidence
  │   └─ Mod / Contributor
  ├─ Provider interfaces
  │   ├─ EmbeddingProvider
  │   ├─ LLMProvider
  │   └─ DocumentParser
  └─ SQLite + private artifact store
```

理由：10k messages / 3 communities / 7 days 的目标规模不需要分布式基础设施；SQLite 事务可覆盖 correction/audit；模块边界足够支持将来替换 provider 或拆服务；现有 Python 引擎、FastAPI 和 React 壳可迁移，不必重写算法基础。

## 2. 目标代码结构

```text
src/community_intelligence/
  domain/             # immutable entities, enums, rules
  analytics/          # hygiene, reply, activation, trend
  intelligence/       # topic, behavior, signal, brief
  knowledge/          # parse, chunk, index, retrieve, conflict
  agent/              # tools, planner loop, synthesis, validators
  moderation/         # roles, Mod Report, scorecard
  contributors/       # High/Emerging candidates
  evidence/           # refs, context assembly, claim validation
  application/        # use cases and job orchestration
  infrastructure/     # SQLite repos, migrations, providers, artifact store
  api/                # FastAPI v1 routes and DTOs only
frontend/src/
  app/                # shell/router/query client
  features/           # home, conversations, moderators, contributors, knowledge
  components/         # CopilotDock, EvidenceDrawer, states
tests/
  unit/ integration/ contract/ evaluation/
```

现有 `pipeline.py` 先保持可运行；逐项把可复用 domain 函数与 tests 接到新 application services，再缩小旧 report builder 的职责。禁止先删除旧流水线再重写。

## 3. 持久化与数据模型

### 3.1 技术选择

- SQLite WAL，foreign keys on；SQLAlchemy Core 与应用内版本化 migration 管理 schema。
- Pydantic v2 作为 API/provider contract；domain entity 尽量 immutable。
- FTS5 保存 Knowledge 与可选 message lexical index。
- embedding 以 `float32` content-addressed cache 保存，数据库记录 model/version/hash/path；不在 P0 引入向量数据库。
- 私有数据根目录权限 `0700`，默认不在仓库内；所有 source path 均经 root containment 与 symlink 检查。

### 3.2 核心实体

| 实体 | 关键字段 | 不变量/用途 |
|---|---|---|
| Workspace | id, project_name, created_at, settings_version | MVP 单 workspace UI，但 schema 不写死 singleton |
| Community | id, workspace_id, name, language, platform, timezone, active | language 为配置主语言，消息保留自身 language |
| SyncBatch | id, community_id, source_type, window_start/end, imported_at, content_hash, status, error | 同 community+hash 幂等；成功后 immutable |
| Message | id, community_id, language, user_id_hash, timestamp, original_text, reply_to_id, reply_to_source_key, source_batch_id | 原文 immutable；reply target 使用跨 batch 稳定 key，允许 parent 后补解析 |
| ActorIdentity | user_id_hash, workspace_id, community_id, display_name?, platform_handle?, pseudonym, updated_at | local-only PII；operator-facing，默认不进入模型或 export |
| RoleAssignment | id, workspace_id, user_id_hash, role, valid_from/to, source, version | 按消息时间解析角色；变更可审计 |
| AnalysisRun | id, workspace_id, window_kind/start/end, baseline_run_id, status, methods, started/finished_at | 输出版本绑定明确 window 与 method version |
| UserCheckWatermark | workspace_id, checked_through, updated_at | `since-last-check` 只在用户确认查看后推进 |
| Topic | id, run_id, canonical_name, method, confidence_level, review_status | 不稳定/无名 cluster 可保留，不能强命名 |
| TopicMembership | topic_id, message_id, score, membership_status | `member/noise/uncertain`；支持 evidence |
| BehaviorJudgment | id, run_id, message_id, primary, secondary_json, method, confidence_level, context_ids, review_status | P0 8 类 + Uncertain；guardrail 独立字段/表 |
| Signal | id, run_id, type, risk_or_opportunity, detected_at, severity, confidence_level, status, recipe_version, trigger_facts_json | severity 来自版本化 recipe，不由 LLM自由生成 |
| SignalLink | signal_id, target_type, target_id | 连接 topics/behaviors/KB/evidence/community |
| EvidenceRef | id, evidence_type, target_type/id, message_id?, source_revision_id?, context_spec, method/version | 统一引用；不复制或改写原文 |
| Brief | id, run_id, content_json, provider, prompt_version, status | 每个 factual span 引用 finding/signal/evidence |
| TimelineEvent | id, run_id, community_id, event_type, occurred_at, facts_json | 只保存业务事件，不保存 UI 文案流水 |
| KnowledgeSource | id, workspace_id, title, source_type/channel, URL/platform identity, language/scope, authority/official status, metadata provenance | logical multi-source identity；type 与 channel 分离 |
| KnowledgeRevision | id, source_id, precise publication/effective/observed/superseded timestamps, version/hash/status, supersession refs, processing versions/status | 每次内容变化创建 revision，不覆盖旧版本 |
| KnowledgeChunk | id, source/revision_id, ordinal, section/heading/page, language, text/token_count, validity/authority | fine-grained retrieval unit，provenance 完整 |
| ModReport | id, community_id, author_hash?, period_start/end, raw_text, parse_status | 原始 report immutable |
| ModReportItem | id, report_id, item_type, normalized_text, topic_ref?, evidence_span | reported topic/issue/action |
| ModPerformanceSnapshot | id, run_id, moderator_hash, dimension_facts_json | 分维度快照，无 total score |
| ContributorCandidate | id, run_id, user_hash, community_id, candidate_type, trend_json, why_json, review_status | High/Emerging 分开；无候选合法 |
| Investigation | id, workspace_id, thread_id, question, scope_json, status, finding_json, confidence_level, provider/method versions | 保存审计所需输入输出 |
| AgentStep | id, investigation_id, step_no, tool_name, args_json, result_ref, status, latency_ms | step_no 1..5；只保存安全摘要与引用 |
| CorrectionProposal | id, actor, target_type/id/version, action_type, previous/new JSON, scope, reason, status, created_at | pending 时不改变 read model |
| HumanCorrection | id, proposal_id, confirmed_at, applied_version, audit_json | Confirm 后原子写入；append-only |

### 3.3 统一 provenance

所有派生实体至少带：`analysis_run_id`、`method_name`、`method_version`、`input_fingerprint`、`created_at`、`review_status`。AI 结果额外带 `provider`、`model`、`prompt_version`；不记录 API key，不默认记录完整远程请求 payload。

### 3.4 数据不变量

1. `Message.original_text`、source batch 与 Knowledge revision 不可原地修改。
2. correction 通过 overlay/read-model projection 生效，历史派生结果不删除。
3. 所有 `EvidenceRef` 必须解析到真实 Message、KnowledgeRevision/Chunk 或明确的 aggregate scope；scope evidence 不得伪装成原始消息。
4. 分析窗口使用 workspace timezone 解释 UI，数据库统一 UTC；`[start, end)`。
5. 重复 batch 幂等；相同 source message 在同 community 内映射稳定 ID。
6. 任何显示为 current 的结果必须匹配最新 successful run、当前 correction version 和相关 Knowledge index version，否则标 `stale`。
7. `reply_to_message_id` 只引用 workspace 内稳定 Message ID，不带 SyncBatch 等值约束；未到达 parent 先保存稳定 `reply_to_source_key`，后续 batch 到达时解析。
8. `display_name` / `platform_handle` 仅保存在本地 ActorIdentity；原始 Telegram sender ID 不持久化。无 identity 时使用稳定 pseudonym；默认 demo/benchmark export 和 remote-provider payload 排除这些字段。

## 4. 端到端数据流

```text
Import Telegram JSON
  → validate / normalize / hash / deduplicate
  → persist SyncBatch + immutable Message
  → resolve RoleAssignment by effective time
  → create AnalysisRun(window, baseline)
  → deterministic facts (count/reply/hygiene/trend/support)
  → embeddings cache
  → Topic + Behavior judgments
  → Signal Engine + Timeline + Mod/Contributor projections
  → Brief input contract
  → optional LLM Brief
  → versioned read APIs
  → UI / Agent tools / Evidence Drawer
```

Analysis 使用 in-process bounded worker（默认 concurrency 1）与持久 `AnalysisRun` job 状态。API 返回 `202 + run_id`，前端轮询；进程中断后 run 标 failed，可安全 rerun。MVP 不实现通用任务队列。

## 5. Topic pipeline

1. **Scope**：按 workspace/window 取有效 messages，保留语言、community、reply context。
2. **Preprocess**：NFKC 与 whitespace 只用于计算；原文不变；剔除纯 filler/scam guardrail 对 topic 的污染但仍保留其 Behavior/Evidence。
3. **Embed**：使用 `EmbeddingProvider`；缓存 key 为 `model_revision + normalized_text_hash`。
4. **Candidate clusters**：对单位化 embedding 使用支持 noise 的密度聚类；首选 scikit-learn HDBSCAN（欧氏距离在单位向量上等价于 cosine 排序）。最小 cluster size/样本由配置和 evaluation 冻结。
5. **Stability gate**：bootstrap/subsample 重跑，检查 member overlap；低稳定 cluster 输出 `Uncertain`，不强制进入 Global Topic。
6. **Canonicalization**：候选 cluster 由 LLM 基于有界代表消息生成英文 canonical name 和短描述；相似 cluster 再做 merge candidate。无 LLM 时保留 `Unnamed topic` + representative evidence，明确 semantic naming unavailable。
7. **Trends**：deterministic 计算 current vs baseline 的 message share、unique users、per-language trend；低 denominator 显式 insufficient。
8. **Evidence**：用离 centroid 最近且覆盖多语言/多 community 的 medoid messages，不能只挑最“好看”的样本。

现有 TF-IDF/KMeans 作为 baseline 与 regression comparator，不作为生产 Global Topic。

## 6. Behavior pipeline

P0 taxonomy 固定为 8 个业务行为：Question/Help Request、Product Issue/Bug、Confusion、FUD/Misinformation、Complaint/Concern、Peer Support/Explanation、Project Discussion、Content Creation/Advocacy；Spam/Scam/Filler/Duplicate/Repetitive/Burst 是独立 guardrail。

```text
message + bounded reply context
  ├─ deterministic guardrail rules
  ├─ semantic classifier candidate(s)
  └─ optional LLM adjudication for ambiguous/material cases
       → primary + secondary[] + confidence level + Uncertain
```

规则层永远运行。语义层通过 `BehaviorProvider` contract 返回结构化 labels，不直接写数据库；validator 检查 taxonomy、message/context IDs 和 explanation refs 后才持久化。阈值通过 EN/CN/ES locked gold set 校准；内部可保存 raw score，UI 只显示 High/Medium/Low/Uncertain/Insufficient Evidence。

## 7. Project Knowledge 与 RAG

### 7.1 Ingestion

`KnowledgeSource` 与 `KnowledgeRevision` 分离。Source 保存 workspace identity、`source_type`、`source_channel`、canonical URL/platform identity、language/project scope 和 authority ownership；Revision 保存内容 hash、offset-aware publication/effective/observed/superseded 时间、状态、版本关系和 processing provenance。关键 factual metadata 使用逐字段 provenance map；AI semantic tags 独立存储，不能覆盖 human-confirmed metadata。

P0 支持 UTF-8 `.md`/`.txt` 与可抽取文本的 `.pdf`，以及 Manual Official Web Source 文本输入；扫描件/OCR 显式 unavailable。原始内容存入 workspace 私有 artifact store，不进入 Git。相同 source+content hash 幂等；内容变化创建新 revision，只 parse/chunk/embed 新 revision。

`structure-v1` 按 document type 切块：Docs/Whitepaper/Blog 使用 heading+paragraph，FAQ 保持 Q+A，Announcement 保留标题+规则/bullets，Release/Changelog 按 version section。token limit/overlap 只是 configurable/versioned 的 fallback。Chunk 保存 source/revision、section/parent heading/page/ordinal/language/token count、validity/authority。解析或索引失败在事务内回滚，不发布 partial index。

### 7.2 Retrieval

采用 fine-grained hybrid retrieval：FTS5 BM25 + 已有 pinned local multilingual embedding provider，使用 Reciprocal Rank Fusion 合并，不使用随意加权“事实分数”。先召回小语义单元，再按相同 revision 的 parent/neighbor 做有界扩展（P0 默认每侧最多 1 个相邻 chunk、总字符数可配置），不得传入整份 document。之后执行确定性的 metadata policy：

1. optional `as_of_time`（默认当前时间）决定 revision 在该时刻的 active/outdated/future 状态；比较 `effective_from/effective_until/published_at/superseded_at`。
2. 非 official 或未验证来源不能产生 `grounded`。
3. 必要 policy 排除未验证、draft/unknown 与未来来源；已有 supersession/effective 时间决定 active/inactive。current query 优先 active，但若 inactive candidate 同时由 lexical/semantic 命中且原 RRF 高于全部 active，则保留该 candidate，避免 `outdated_only` evidence 被整体挤出。
4. Answer status 按每条已验证 claim 的 citation temporal state 判定，而不是按候选集合中是否存在 active source。Generic 180/30/±1 连续三轮已通过 current/outdated/conflict/insufficient/no-answer gate；本阶段仍不增加 query-sensitive router。

policy version 与每次结果一起返回。P0 保存完整 source type/channel/authority/recency/validity，但不实现 AI query router；query-sensitive routing 只在 benchmark failure case 证明必要时加入。

### 7.3 Answer/conflict contract

RAG 返回五类 answer_status、claim list、answerability（requirements/missing facts）、grounding、原始 citations/context、retrieval methods、as_of_time 和 policy version。`material-facts-evidence-v2` 使用显式配置的 JSON completion provider，读取问题与有限 evidence，只分解用户直接询问的事实并评估支持/缺失/冲突；仅引用校验通过的 claims 可展示。非法 quote 可在同一 evidence 上 repair 一次，合法 abstention 不重试。Semantic tags 不自动决定事实冲突。

代码确定性检查 requirement/claim 对应、缺项、chunk ID、原文逐字 quote（仅规范空白）及冲突两侧 source ID；语义蕴含由模型判断并由独立于返回状态的 rubric evaluation 检验。逐字引用合法不等于语义判断必然正确。模型过度分解和 quote-generation failure 均已观察到，仍属质量限制。无配置或模型错误时降级为 insufficient，不回退到相似度冒充 grounded。

Provider 通过 `COMMUNITY_INTELLIGENCE_LLM_CONFIG` 指向本地 ignored JSON 显式启用（enabled/base_url/model/api_key；没有默认 provider）。标准库 HTTPS JSON 请求、禁重定向、无 tools、无新增依赖。每题最多 20,000 字符原文、每个 hit 最多 4,000，重复邻块去重；不传整库、operator identity、密钥、系统路径或作者身份。源文件仍本地保存，provider 自身的保存政策不由本应用保证。用户批准 DeepSeek Flash 作为本轮配置实例，不写入产品 contract。请求模型 `deepseek-v4-flash`、实际返回 `deepseek-flash` 均记录于实验 receipt。

Retrieval representation 版本 `title-heading-body-v1`：title + heading hierarchy/current section + 原始正文。FAQ question 与 release/version heading 来自结构本身，不加入项目词表。180/30 切块内容与 ordinal 不变；只改变派生 parent hierarchy 和索引输入。Embedding cache key 包含 representation version/text hash 与 pinned model revision。旧 revision 使用显式 representation-only reindex，先核对原文 hash 和 chunk text/ordinal/section 不变，再事务更新索引；不创建伪内容 revision。旧索引返回 reindex_required，不静默全库重算。

Community chat 和 document text 统一以 untrusted data envelope 输入模型；tool/system 指令只由应用代码定义。检索内容中的 URL、代码或指令均不得触发工具。

### 7.4 API、frontend state 与 evaluation

`/api/v1/workspaces/{workspace_id}/knowledge-sources` 支持 multipart file 或 JSON manual source；source/revision/chunk 均有只读 detail endpoint。`/knowledge-query` 接收 original query、optional `as_of_time`、top-k 和 bounded expansion 配置，返回 candidate hits、status、citations 与 limitations。

Knowledge Review Surface 只消费上述 `/api/v1/*`，状态为 source list → metadata/revision detail → processing status → query result → citation provenance。固定 fixture/golden set 与产品代码分离；Retrieval 计算 Recall@K、MRR/nDCG 和 cross-language slice，Answer 层计算 citation validity、grounded、abstention、insufficient evidence、conflict、outdated error。每个 run 固化 dataset/config/model/chunk/index versions。

M2.1 页面增加 facts/coverage、缺项、支持引用与 bounded context；`POST /api/v1/knowledge-revisions/{id}/reindex` 仅升级派生索引。External regression、document-disjoint holdout、generic curated 保底结果分别记录，不能合并宣传。M2/M2.1 均未 Frozen。

Query rewrite、multi-query、GraphRAG、RAPTOR、HyDE 与 agentic retrieval 在 M2 默认不存在。Controlled TON experiment 显示 remote multilingual listwise reranker 在同一 policy Top20 上将 Recall@5 从 74.3% 提升到 98.7%，但增加一次 remote call 与约 2.31s 中位延迟；正式接入等待 Product Owner 接受 privacy/latency/cost contract，未配置时必须保留 RRF fallback。

## 8. Signal Engine

Signal 是可解释 recipe 的结果，不是 LLM 生成的 alert。每种 recipe 版本化，输入仅为已验证 facts：topic/behavior trend、unique users、persistence、role distribution、support status、hygiene、KB grounding 和 evidence strength。

```text
SignalRecipe
  type
  eligibility gates
  trigger conditions
  severity decision table
  confidence/evidence policy
  cooldown/dedup window
  explanation template
  version
```

P0 risk：Security/Scam、Product/Asset Issue、FUD/Misinformation、Information/Campaign Confusion、Support/Mod Coverage Failure。P0 opportunity：Organic Discussion Rising、Peer Support Rising、Content/Advocacy Rising、High Contributor、Emerging Contributor。

约束：单条消息默认不能得到 High severity；message count increase 不能单独触发 opportunity；严重度采用决策表而非加权总分；高风险措辞默认为 Potential/Possible；阈值在 signal gold set 上冻结前只标 candidate。Signal dedup 使用 `type + communities + topic + rolling window`，状态为 open/acknowledged/dismissed/resolved/stale。

## 9. Brief generator

Brief 输入是有界 `BriefInput`：top risk signals、opportunities、关键 trend facts、代表 EvidenceRef、必要时的 Knowledge retrieval result。禁止传整份 corpus。LLM 输出严格 JSON：sections、sentence spans、claim refs、uncertainty。validator 拒绝无引用事实、未知 ID、未允许 severity 或越界建议；失败时 Home 仍显示 structured cards，并标 AI Brief unavailable。

## 10. Investigation Agent 与 tools

Agent 是单 orchestrator，不拆 multi-agent。planner 每一步只能从注册的只读 tool 中选一个；server 强制 `max_steps=5`、timeout、每 tool 返回量和 token budget。工具直接调用 application query services，不让 LLM 生成 SQL、文件路径、URL 或 shell 命令。

M5 才引入 LangGraph 作为可替换的 workflow runtime，边界见 `docs/adr/0001-langgraph-agent-and-human-interrupt.md`。它只负责 Agent state、tool routing、checkpoint、interrupt/resume；Topic、Behavior、Signal、RAG、Evidence、tool contract 与 evaluation 保持 framework-agnostic。M1–M4 不依赖 LangGraph，也不提前增加相关 package 或 adapter hierarchy。

统一 `ToolResult`：

```text
tool_name, scope, facts[], evidence_refs[], knowledge_refs[],
status, limitations[], method_version, latency_ms
```

P0 tools 映射：activity/topic/behavior/role/unanswered/latency/reply/hygiene/community compare/Mod/contributor/timeline/reported-vs-observed/conversation evidence/project knowledge。相同事实服务同时供 UI 与 Agent 使用，避免两套分析逻辑。

最终合成固定为 Finding、Why/Analysis Chain、Evidence、Knowledge Sources、Confidence、Possible Cause、Suggested Next Action。Suggested action 使用小型 taxonomy（Update FAQ、Ask Mod、Review unanswered、Publish clarification、Escalate Product/Engineering、Review Mod coverage、Contact contributor、Monitor、Check KB freshness）加可选说明；不执行动作。

Agent 输出经过三道 gate：schema validator、ID/citation referential validator、material-claim entailment evaluator。关联不得改写为因果；失败返回 Insufficient Evidence/Conflicting Signals，而非补写答案。

## 11. Human Correction

自然语言 correction 只产生 `CorrectionProposal`。proposal schema 使用 discriminated union，包含 action、target、target_version、scope、before/after、reason、impact preview。Confirm API 在单个事务中执行 optimistic version check、写 append-only HumanCorrection、更新 correction overlay version、标记受影响 read models stale，并入队局部 recompute。

M6 可由 LangGraph 编排 `proposal → interrupt → human confirmation → resume`，但 Confirm 之后的 version check、apply、audit 与 recompute 始终调用 domain service 和数据库事务；workflow checkpoint 不是业务事实源。

P0 顺序：Signal reclassify/dismiss → Behavior relabel → Topic rename → Role assignment → Contributor confirm/remove。Topic merge 后置到 Topic identity contract 稳定。Knowledge update 只提出“新增/替换 source”建议，仍经 Knowledge 页面确认导入。

## 12. Mod 与 Contributor 计算

Mod scorecard 按有效 RoleAssignment 聚合：responsiveness、meaningful contribution、answer groundedness、user engagement、anti-gaming、reporting coverage。各维度保留 numerator/denominator/window/evidence，不计算总分，不输出人事动作。

Mod Report parser 先提取 reported topic/issue/action + raw spans，再用 topic/evidence retrieval 与 observed findings 匹配；输出 matched、observed-but-not-reported、reported-only。没有充分匹配只称 Potential Reporting Gap。

Contributor 先使用可解释 eligibility gates（非 Mod、最低 active days/users helped/evidence、gaming guardrail），再分别生成 sustained High 与 rising Emerging。趋势由 deterministic window comparison 产生；semantic contribution 类型来自 Behavior。任何 gate 不满足可返回空列表。

## 13. API v1

| 方法与路径 | 用途 | 主要返回 |
|---|---|---|
| POST `/api/v1/workspaces` | 创建本地项目 | Workspace |
| GET/PATCH `/api/v1/workspaces/{id}` | settings/authority policy | versioned Workspace |
| POST `/api/v1/workspaces/{id}/communities` | 配置 EN/CN/ES community | Community |
| POST `/api/v1/communities/{id}/imports/telegram` | 导入 batch | SyncBatch + validation summary |
| GET `/api/v1/workspaces/{id}/actors` | Mod/Contributor operator identity | local-only label + stable `user_id_hash` |
| GET `/api/v1/workspaces/{id}/freshness` | 数据新鲜度 | per-community freshness |
| POST `/api/v1/workspaces/{id}/analysis-runs` | 发起 window analysis | `202`, AnalysisRun |
| GET `/api/v1/analysis-runs/{id}` | 轮询状态 | status/progress/error |
| GET `/api/v1/home?workspace_id&window` | Home read model | brief/signals/opportunities/timeline |
| GET `/api/v1/topics` | topic browse/filter | paged topics |
| GET `/api/v1/behaviors` | behavior browse/filter | paged judgments/aggregates |
| GET `/api/v1/conversations/{message_id}` | evidence context | original/translation/context/refs |
| GET `/api/v1/signals/{id}` | signal facts | recipe/trigger/evidence/status |
| POST `/api/v1/investigations` | Ask/Investigate | Investigation result or job |
| GET `/api/v1/investigations/{id}` | steps/result | bounded trace + citations |
| POST `/api/v1/correction-proposals` | 解析或显式创建 proposal | preview only |
| POST `/api/v1/correction-proposals/{id}/confirm` | 原子应用 | HumanCorrection + changed refs |
| POST `/api/v1/correction-proposals/{id}/cancel` | 取消 | status |
| GET/POST `/api/v1/knowledge/sources` | 列表/导入 | source + revision/index status |
| GET `/api/v1/knowledge/conflicts` | 冲突/过期 | grouped source refs |
| PUT `/api/v1/workspaces/{id}/role-assignments` | Mod 配置 | versioned assignment |
| POST `/api/v1/mod-reports` | 输入 report | parse job/result |
| GET `/api/v1/moderators` | scorecards | dimensions + evidence |
| GET `/api/v1/contributors` | High/Emerging | candidates + why/evidence |

分页使用 cursor；所有读 API 返回 `schema_version`、`generated_at`、`analysis_run_id`、`stale`。错误采用稳定 machine code + 用户可读 detail。文件上传限制类型、大小和 private storage boundary。

## 14. Frontend state

- React Router 管理页面与可分享 filter URL；一级页 lazy load。
- TanStack Query 管理 server state、polling、cache invalidation；不把完整 report/evidence 常驻一个组件。
- Workspace/window/filter 属于 URL + WorkspaceContext；Evidence detail stack 与 Copilot thread 分离保存。
- Correction 使用显式状态机：idle → proposing → awaiting_confirmation → applying → applied/conflict/failed。
- Analysis job：idle → queued → running → succeeded/failed；刷新页面可由 run ID 恢复。
- 仅将 drawer/panel/selection 之类短暂 UI state 放本地 reducer；业务事实以 API 为准。
- 点击 correction confirm 后按 changed refs 精确 invalidate Home/Signal/Topic/Behavior/Contributor，而非全页重载。

## 15. Provider 与 fallback

`EmbeddingProvider`、`LLMProvider`、`DocumentParser` 都有 capability probe 与版本信息。默认 deterministic profile 在无模型时仍运行 import/reply/hygiene/count/trend；semantic profile 需要本地 embedding；Brief/Agent/语义 adjudication 需要显式配置 LLM。远程 provider 只接收最少 Evidence/Knowledge snippets，allowlist 默认排除 ActorIdentity 的 display name、handle 与 pseudonym，调用前在设置页展示数据边界。

禁止在生产 UI 用测试 fake 冒充结果。Synthetic demo 可使用固定数据，但仍必须调用真实 pipeline/provider；若 provider 不可用，对应卡明确 unavailable。

## 16. Evaluation architecture

```text
tests/unit                 pure rules, formulas, schemas
tests/integration          DB/import/index/job/correction transactions
tests/contract             API/provider/tool/citation compatibility
tests/evaluation/fixtures  locked EN/CN/ES gold sets + KB conflict cases
eval/topic                 alignment/coherence/stability/evidence validity
eval/behavior              macro/per-class P/R/F1 + confusion + abstention
eval/signal                precision/recall/FPR/latency/evidence validity
eval/rag                   Recall@K/citation/grounding/outdated/conflict/no-answer
eval/agent                 tool relevance/≤5/unsupported claim/citation/usefulness
eval/product               review-time and lead-time experiment protocols
```

每次 evaluation 记录 dataset version、sample size、language/class distribution、provider/model/prompt/method versions、abstention coverage 和 failures。material unsupported claim rate 是 release blocker；“接近 0”的具体门槛需在 M0 冻结。Synthetic fixture 只验证流程，不声称真实世界效果。

## 17. 性能与可观测性

- 关键阶段记录 structured event：run/import/index/tool step、duration、count、method version、error code；不记录 raw private text 或 key。
- 对 10k messages 建立固定 benchmark：deterministic、embedding、topic、behavior、signal 分阶段计时；目标整轮 p95 ≤60s。
- Home 读 model 和分页列表走索引；页面切换使用 query cache，p95 <500ms；conversation context 单独查询，p95 <1s。
- Brief/Investigation 记录/成本由 provider adapter 强制；Investigation 超时返回已完成 steps 与 unavailable 状态。

## 18. 安全与隐私

- API 默认只绑定 loopback；CORS 不开放任意来源。
- 上传内容与 KB 都是不可信数据；不执行宏、脚本、链接或 embedded instructions。
- remote LLM request 做 allowlisted field serialization、size cap 与 secret redaction；日志不含原文 payload。
- 不建立人格画像；用户级查询只为 contributor/Mod 业务用途，受 role 和 evidence 边界约束。
- 提供 workspace export/delete 在真实数据 pilot 前完成；删除语义、备份/恢复策略需要 PO policy。

## 19. 迁移策略

1. 在当前仓库和既有 history 上建立 v2 schema/API/evaluation contracts；v0.1 baseline 为 `b5d5d02`。
2. 按模块原地适配 importer、models、message rules、reply episodes、hygiene、activation、semantic provider 及对应测试；每次记录基线文件/commit 和 contract 变化。
3. 旧 pipeline/report/frontend 保持可运行，逐步由 adapters 与新 read models 接管；用 regression fixtures 证明迁移前后确定性结果一致后，才把旧路径标为 internal/deprecated。
4. Campaign/Metric Lab 保存在 `internal` 包或后续单独迁移，不阻塞 P0。
5. 新能力按 M1–M9 逐层接入，不以“大重写”作为里程碑。

---
artifact: prd
product: Community Intelligence AI
version: 2.2
date: 2026-09-11
status: Ready for Technical Design
owner: Product
primary_use_case: Web3 multilingual community operations
mvp_platform: Telegram
mvp_languages:
  - EN
  - CN
  - ES
---

# Community Intelligence AI — MVP PRD v2.2

> **一句话定位：** 面向多语言 Web3 社区运营的 AI Community Copilot。系统持续理解社区聊天与项目知识，主动发现风险和机会；运营人员可通过对话让 Agent 解释、调查和修正判断，并将任何结论定位回原始聊天证据。

---

## 0. 文档目的

本文档用于冻结 MVP 产品范围，并作为以下后续工作的唯一产品输入：

1. Low-fidelity Wireframe
2. Technical Design
3. API / Data Contract
4. Development Task Breakdown
5. Test Plan
6. AI Evaluation Plan
7. Portfolio Demo Script

本文档描述 **What / Why / Acceptance**。具体代码结构、模型选择、数据库、接口实现方式由 Technical Design 决定。

---

# 1. 背景与问题定义

## 1.1 业务背景

Web3 Community Lead 经常同时管理多个语言区、多个时区和多名 Moderator（以下简称 Mod）/ Ambassador。

以 MVP 目标场景为例，一个项目同时存在：

- EN Community
- CN Community
- ES Community

各社区持续产生大量 Telegram 聊天。运营负责人无法完整阅读全部消息，现实工作通常依赖：

- Mod 主动汇报社区情况；
- 运营人员人工抽查各语言区；
- Discord 问题反馈频道；
- Mod 工作群；
- Combot 等基础统计工具；
- message count / active users 等传统 KPI。

这些方式存在三个核心问题。

### P1. 人工巡检成本过高

跨语言、跨时区社区持续产生消息，Community Lead 无法保持对所有 Community 的实时认知。

### P2. Mod 汇报存在天然延迟与信息偏差

Mod Report 是重要信息源，但可能存在：

- 某些问题没有被 Mod 注意；
- 某些问题只在本地语言区出现；
- 用户直接询问本地 Mod，不会进入统一反馈渠道；
- Mod 关注程度不同；
- 问题上报时已经发酵。

### P3. 传统 KPI 无法衡量真实运营价值

`Message Count` 容易被 gaming。

高发言量可能来自：

- 高频短句；
- 重复内容；
- 无意义回复；
- 最低标准打卡。

这些行为不能证明：

- 用户问题被解决；
- 用户真正参与活动；
- 用户开始自发讨论；
- 社区形成健康互动；
- Mod 真正创造运营价值。

---

# 2. Primary JTBD

> **当我管理多个时区、多个语言区的 Web3 社区时，我希望系统持续读取社区聊天，并主动告诉我自上次查看以来发生了什么、哪些风险或机会值得注意、用户在讨论什么和做什么、Mod 实际表现如何，以及系统为什么这么判断，从而减少人工巡检，并更早、更准确地做运营决策。**

---

# 3. 产品定位

## 3.1 主定位

**Community Operations Management Tool**

社区分析是基础能力，但分析不是终点。产品服务于：

- 社区动态监测；
- 社区问题诊断；
- Mod 管理；
- 用户反馈回流；
- 贡献者运营；
- 后续运营策略决策。

## 3.2 AI 产品定位

MVP 是完整 AI Community Copilot 的第一阶段：

```text
Sense
Community Intelligence
        ↓
Prioritize
Risk / Opportunity Signals
        ↓
Investigate
Community Evidence + Official Knowledge Grounding
        ↓
Explain / Correct
Investigation + Ask Community + Human Intervention
        ↓
Recommend
Strategy / Intervention Agent（下一阶段）
        ↓
Act
Human Approval + Tools（未来）
        ↓
Learn
Outcome Feedback（未来）
```

当前 MVP 范围：

> **Sense + Prioritize + Investigate + Explain + Human Correct**

其中 Project Knowledge / RAG 不作为独立终点，而作为 Investigation 的官方事实层：

> **Community 侧告诉系统“发生了什么”，Project Knowledge 告诉系统“官方怎么说”。**

RAG 的主要价值不是替 Community Lead 回忆项目常识，也不是直接回答社区成员的零散问题，而是在系统发现值得关注的社区问题后，自动关联可追溯的官方口径、规则、公告与历史版本，帮助 Community Lead 判断问题性质并采取下一步行动。

Standalone Knowledge QA / conversational follow-up 可以存在，但属于 secondary surface，不是 M2 的主要产品价值。

当前 MVP 不做完整 Strategy / Execute。

---

# 4. 产品核心原则

1. **Message Volume ≠ Community Health**
2. **Moderator Activity ≠ User Activation**
3. **High Activity ≠ High Contribution**
4. **能确定性计算的，不交给 AI 猜**
5. **需要语义理解和动态调查的地方才使用 AI / Agent**
6. **重要判断必须 Evidence-first**
7. **无法可靠判断时允许 Uncertain / Insufficient Evidence**
8. **AI 不直接替代人完成绩效、人事和处罚决策**
9. **Project Knowledge 是事实基准，不把模型记忆当 Source of Truth**
10. **聊天入口不仅用于问答，也是解释、调查和人工纠错入口**
11. **MVP 优先证明“几步内产生运营价值”，而不是堆叠功能**
12. **功能模块可以稳定，指标 / taxonomy / threshold 后续持续迭代**
13. **Community Evidence 与 Official Knowledge 必须分层：前者描述社区实际发生了什么，后者提供官方事实基准。**
14. **RAG 默认服务于 Investigation grounding，不要求 Community Lead 先提出一个自然语言知识问题。**

---

# 5. MVP Hero Experience

## 5.1 Hero Moment

Community Lead 早上打开产品。

系统已经分析最近一次数据更新后 EN / CN / ES 的新聊天：

> **过去 8 小时有 3 件事值得关注。**
>
> - CN：Quest reward 相关 Question / Confusion 明显上升，涉及 18 名用户，11 个问题尚未得到有效回复。
> - ES：Staking eligibility 出现集中 confusion。
> - EN：无明显风险，但 User A31 进入 High Contributor 候选。

Community Lead 不需要先阅读数百条聊天，也不需要自己想好一个问题去问知识库。

用户点击 CN Signal 的：

> `Investigate`

系统形成 Investigation Context：

- 当前 Signal；
- 相关 Topic / Behavior；
- 受影响用户与趋势；
- 代表性 Community Evidence；
- 社区中反复出现的 claim / confusion；
- 分析时间窗口；
- `as_of_time`；
- 当前调查目标。

Investigation Agent 根据中间结果调用分析工具，并在需要项目事实时自动调用 Project Knowledge：

```text
Topic / Behavior
→ affected users
→ unanswered questions
→ Mod response
→ observed community claims
→ retrieve relevant official knowledge
→ compare community evidence with official context
→ identify supported / conflicting / unknown facts
```

Investigation 页面固定呈现三层信息：

### What we see in the community

社区正在发生什么，包括趋势、用户范围、Behavior、回复情况及原始 Evidence。

### What official sources say

自动关联与当前问题相关的官方 Blog、Announcement、Docs、FAQ、规则或历史版本，并保留 citation、时间和 provenance。

### What we know / what remains unknown

明确区分：

- 社区说法与官方信息一致；
- 社区存在误解；
- 官方信息不足或未明确；
- 官方规则发生过变化；
- 已有官方维护 / known issue；
- 当前可能是新的产品问题；
- 当前 claim 缺少 authoritative evidence。

Community Lead 再据此决定是否：

- 统一 Mod 回复口径；
- 发布 clarification；
- 更新 FAQ；
- 升级 Product / Engineering；
- 继续观察；
- 查看原始 Conversation Evidence。

如果需要继续深挖，用户可以在 Ask Community 中追问：

> “官方有没有明确说过奖励会立即到账？”
>
> “这个规则和 7 月那次活动一样吗？”
>
> “只看 8 月 1 日以前的官方信息。”
>
> “根据现有官方证据，整理一版给 Mods 的回复口径。”

因此：

> **自动 grounding 是主路径，对话式 RAG 是 follow-up。**

---

# 6. MVP 范围

## 6.1 P0 — 必须实现

### A. Workspace & Data

- 一个 Workspace = 一个 Web3 项目；
- EN / CN / ES 三个 Community；
- Telegram Desktop JSON batch import；
- Synthetic demo data；
- Mod 人工角色配置；
- Mod Report 输入；
- 分析时间窗口；
- source freshness；
- since-last-check comparison。

### B. Project Knowledge Base / RAG

- 项目白皮书；
- 官方 Docs；
- FAQ；
- Tokenomics；
- Product Guides；
- Community Rules；
- Campaign Rules；
- Official Announcements；
- Official Blog；
- Release Notes / Changelog；
- Maintenance Notice；
- 手工补充并确认的官方项目知识。

P0 RAG 主要用于：

- 为 Signal / Investigation 自动补充 Official Context；
- 核查社区 claim 是否有官方依据；
- 核查规则、活动、产品说明；
- 识别历史规则变化；
- 查询 maintenance / known issue / release context；
- 为 Mod response guidance 提供官方 grounding；
- Agent 调查中的 project-specific factual verification。

Community Lead 不需要为了触发 RAG 先手工输入一个自然语言问题。

Standalone Project Knowledge QA 可以作为 secondary capability，但不是 P0 Hero Flow。

### C. Intelligence Engine

- Cross-language Topic；
- Behavior；
- Community Pulse；
- Reply / Support；
- Hygiene；
- Risk Signals；
- Opportunity Signals；
- Mod Evaluation；
- Contributor Radar。

### D. Copilot Experience

- AI Brief；
- Need Attention；
- Opportunities；
- Community Timeline；
- Ask Community；
- Signal → Investigate；
- Signal → Investigation Context；
- Investigation → Official Context；
- Human Correction / Intervention；
- Evidence → Original Conversation。

### E. Investigation Agent

- Signal-driven investigation；
- Investigation Context assembly；
- bounded tool calling；
- dynamic investigation；
- Community Evidence retrieval；
- Project Knowledge grounding；
- community claim vs official fact verification；
- evidence-grounded diagnosis；
- explicit unknown / insufficient evidence；
- suggested immediate action。

## 6.2 P1 — 下一版本

- Telegram scheduled / connected sync；
- Discord ingestion；
- human review persistence；
- expanded languages；
- Open-set Behavior Discovery；
- contributor history；
- scheduled weekly brief；
- alerts / notification delivery。

## 6.3 P2 — Campaign Intelligence

- Campaign Brief；
- Atomic Claims；
- multilingual semantic coverage；
- drift / incorrect propagation；
- campaign response analysis。

## 6.4 P3 — Community Strategy Agent

- Goal input；
- audience selection；
- current community state；
- historical operation outcome；
- Project Knowledge；
- external competitor / language-region trends；
- intervention / activity recommendation；
- metrics-to-watch；
- human approval。

---

# 7. 非目标

MVP 不做：

- 自动发 Telegram / Discord 消息；
- 自动封禁 / 踢人；
- 自动判断 Mod 是否应该开除；
- 自动算工资 / 奖金；
- 黑盒 Mod 总分；
- 黑盒 Community Health Score；
- 自动执行运营活动；
- 完整活动策划 Agent；
- External Trending；
- CRM；
- Retention / Revenue prediction；
- 多项目 SaaS；
- Enterprise RBAC；
- 自动模型训练。

---

# 8. 信息架构

## 8.1 一级结构

推荐一级入口：

```text
Home
Conversations
Moderators
Contributors
Knowledge
```

全局固定入口：

> **Ask Community**

全局公共组件：

> **Conversation / Evidence Drawer**

## 8.2 为什么不把 Evidence 作为主导航

Evidence 是横跨所有功能的公共下钻能力。

任何：

- Brief；
- Signal；
- Topic；
- Behavior；
- Mod Judgment；
- Contributor；
- Agent Answer

均能进入 Evidence。

---

# 9. Home — Brief-first Experience

## 9.1 AI Brief

### FR-HOME-001

Home 首屏展示一段短 AI Brief，回答：

> 自上次查看以来最值得关注的事情是什么？

Brief 输入只允许使用：

- structured signals；
- metrics；
- topic / behavior trends；
- selected representative evidence；
- Project Knowledge（仅在解释需要事实判断时）。

禁止直接把整个 corpus 无约束塞给 LLM 总结。

### FR-HOME-002

Brief 必须区分：

- Risks / Need Attention
- Opportunities

### FR-HOME-003

Brief 每条事实必须可映射到 structured finding / evidence。

---

## 9.2 Need Attention

P0 风险类型：

1. Security / Scam Signal
2. Product / Asset Issue
3. FUD / Misinformation
4. Information / Campaign Confusion
5. Support / Mod Coverage Failure

每张卡：

```text
Title
Affected community
Detected at
Trend
Affected users
Evidence count
Confidence
Why it matters

[View conversations]
[Investigate]
```

### FR-HOME-010

Need Attention 默认最多展示 5 个最高优先级 Signal。

### FR-HOME-011

Severity 不能由 LLM 自由生成，必须结合：

- trend magnitude；
- affected users；
- persistence；
- support status；
- evidence strength；
- risk type。

### FR-HOME-012

高风险内容统一使用 Potential / Possible wording，除非事实已经由权威 Source of Truth 明确验证。

---

## 9.3 Opportunity Signals

P0 Opportunity：

- Organic Project Discussion Rising；
- Peer Support Rising；
- Content Creation / Advocacy Rising；
- High Contributor Detected；
- Emerging Contributor Detected。

### FR-HOME-020

Opportunity 不得仅由 message count increase 触发。

---

## 9.4 Community Timeline

### FR-HOME-030

Timeline 展示“有业务意义的事件”，不展示原始消息流水。

例如：

```text
02:10  Wallet issue discussion begins
03:05  Unique affected users reaches 10
04:20  Unanswered rate crosses threshold
05:10  First Mod response
```

### FR-HOME-031

每个 timeline event 可进入相关 evidence。

---

# 10. Conversation Intelligence

## 10.1 Cross-language Topic

### FR-TOPIC-001

系统需要跨 EN / CN / ES 统一语义 Topic。

例如：

```text
质押奖励
staking rewards
recompensas de staking

→ Global Topic: Staking Rewards
```

### FR-TOPIC-002

Topic 输出：

```text
topic_id
canonical_name
message_count
unique_users
share_of_discussion
global_trend
per_language_trend
representative_message_ids
method
confidence
```

### FR-TOPIC-003

用户点击 Topic，可查看：

- EN/CN/ES breakdown；
- representative conversations；
- behavior mix；
- trend；
- unresolved questions；
- related signals。

### FR-TOPIC-004

Topic 样本不足时输出 Low Evidence / Uncertain，不强制命名。

---

## 10.2 Behavior

Topic = What people talk about.

Behavior = What people are doing.

MVP P0：

### Tier 1 — 直接影响运营动作

1. Question / Help Request
2. Product Issue / Bug Report
3. Confusion / Misunderstanding
4. FUD / Misinformation
5. Complaint / Concern

### Tier 2 — 社区价值行为

6. Peer Support / Explanation
7. Project Discussion
8. Content Creation / Advocacy

独立 Guardrail：

- Spam
- Scam
- Filler
- Duplicate
- Repetitive Content
- Burst Posting

### FR-BHV-001

行为识别支持：

- primary behavior；
- optional secondary behavior；
- Uncertain。

### FR-BHV-002

Behavior 可按：

- Topic；
- Community；
- Role；
- User；
- Period

查看。

### FR-BHV-003

任何重要行为判断可以下钻原始聊天。

---

# 11. Project Knowledge Base / RAG

## 11.1 产品目的

Knowledge Base 不是为了增加一个“和白皮书聊天”的功能，也不是社区成员问答机器人。

它提供：

> **Project-specific Source of Truth**

其主要职责是在 Community Intelligence 已经发现值得关注的问题后，为 Investigation 自动补充官方事实上下文。

产品中的两种证据必须明确分层：

### Community Evidence

回答：

> **社区正在发生什么？**

来源包括：

- Conversation；
- Topic；
- Behavior；
- Reply / Support；
- Trend；
- affected users；
- Mod response；
- observed community claims。

### Project Knowledge

回答：

> **官方怎么说？**

来源包括：

- Official Blog；
- Announcement；
- Docs；
- FAQ；
- Campaign Rules；
- Maintenance Notice；
- Release Notes；
- 其他经验证的官方来源。

M2 的核心价值是将两者在 Investigation 中关联起来，但不得混淆来源。

典型用途包括：

- 社区出现大量 confusion 时，检查官方规则是否已经说明；
- 社区传播某个 claim 时，核查当前是否有 authoritative evidence；
- 用户认为规则发生变化时，恢复历史官方版本；
- Product Issue 激增时，检查是否存在 maintenance / known issue / release context；
- Mod 准备回复用户时，提供可引用的官方口径；
- Agent 需要做 project-specific factual judgment 时提供事实依据。

Knowledge Base 可以返回：

- supported official fact；
- conflicting official sources；
- historical rule change；
- outdated-only evidence；
- no authoritative source；
- insufficient evidence。

没有官方证据本身也是有效调查结果。

---

## 11.2 P0 Knowledge Sources

Project Knowledge 是通用的 multi-source official knowledge layer，不假设来源一定是 Docs，也不绑定任何具体 Web3 项目。

`source_type` 表达内容性质，至少支持：`whitepaper`、`product_docs`、`faq`、`official_announcement`、`official_blog`、`release_notes`、`changelog`、`governance_proposal`、`maintenance_notice`、`campaign_rules`、`community_rules`、`manual_official_note`。

`source_channel` 表达发布渠道，至少支持：`docs`、`website`、`medium`、`x`、`telegram_announcement`、`github`、`governance`、`manual`。渠道不能代替内容性质；例如 Medium 上发布的维护公告表示为 `source_channel=medium`、`source_type=maintenance_notice`。

P0 正式 ingestion 支持 UTF-8 `.md`、`.txt` 和可抽取文本的 `.pdf`。扫描 PDF / OCR 显式显示 unavailable。另提供 Manual Official Web Source，使运营人员以 `content + source URL + source type + source channel + publication metadata` 导入官方网页、Medium、X、Telegram Announcement 或 Governance 页面内容。

后续 crawler / connector 只负责转换成相同 `KnowledgeSource` contract，不改写 RAG 核心逻辑；URL auto-sync 不属于 M2。

---

## 11.3 Knowledge Metadata

Metadata 是一等公民，不得把 Knowledge Base 实现成“文件 + embedding”。每个 source/revision 至少需要：

```text
source_id / workspace_id / title
source_type / source_channel
canonical_url / platform / platform_content_id / author
language / project_scope
authority_level / official_status / source_owner / verification_method
published_on / published_at / temporal_precision
updated_at / effective_from / effective_until
ingested_at / observed_at / superseded_at / source_timezone
version / revision_id
content_hash
status
supersedes_source_id / supersedes_revision_id
superseded_by_source_id / superseded_by_revision_id
parser_version / chunk_strategy / chunk_strategy_version
embedding_model / embedding_revision / index_version
```

Publication metadata 必须保留来源真实提供的时间精度，不得为了 schema 伪造更高精度。

至少支持：

- `published_on`：来源只提供日期；
- `published_at`：来源提供精确 timestamp；
- `temporal_precision = day | second`；
- nullable `effective_from / effective_until`。

Blog 等 date-only source 不得伪造 midnight timestamp。

Publication time 与 validity time 必须分开：

> **published ≠ effective**

只有来源明确提供或经人工确认时，才写入 validity metadata。

`as_of_time` evaluation 必须尊重 source temporal precision；day-precision source 在同日精确时刻查询中不得冒充已知具体发布时间。

精确时间字段必须为 offset-aware timestamp；内部统一保留 UTC，同时保留原始 `source_timezone`。`status` 至少支持 `current | superseded | expired | historical | draft | unknown`。

会影响事实排序的关键 metadata（至少 authority、official status、validity、publication metadata〔`published_on / published_at / temporal_precision`〕、source_type）必须逐字段记录 provenance：`source-provided | human-confirmed | system-derived | ai-inferred`。AI 推断不能未经人工确认直接成为有效事实。AI semantic tags 与 factual provenance metadata 分层存储。

### Authority 与历史有效性

RAG contract 从 M2 开始支持 optional `as_of_time`。系统基于 publication metadata（`published_on / published_at / temporal_precision`）、`effective_from`、`effective_until` 与 `superseded_at` 判断 source 在查询时间点是否已经发布且有效，不能用今天的资料倒推历史事实。`temporal_precision=second` 时按精确 timestamp 判断；`temporal_precision=day` 时只能做日期级判断，在同日带具体时刻的 `as_of_time` 下不得推断 source 已经发布，必须保留 temporal uncertainty。

对于 current-fact query，`historical` status 只有在其 `validity` metadata provenance 为 `source-provided` 或 `human-confirmed` 时，才降低为历史背景，不与 current official source 以相同优先级竞争，也不仅因措辞不同触发 current conflict。系统不得伪造 `effective_until`、删除 historical source 或把“看起来很旧”的 AI/system 推断直接生效。带 past `as_of_time` 的 query 中，只要该 source 在当时已经发布且满足已有 verified 时间边界，它仍可参与当时事实判断。该规则必须属于 versioned metadata policy。

每个 chunk 保留：

```text
chunk_id / source_id / revision_id
section / parent_heading / page / ordinal
language / token_count / validity / authority
```

Chunking 采用 structure-aware / document-type-aware 策略：Whitepaper/Docs 按 heading 与语义段落，FAQ 保持 Question+Answer，Announcement 保持标题和 material rules/bullets，Release Notes/Changelog 按版本段，Blog/Medium 按 heading 与段落组。token size/overlap 只用于二次拆分与 fallback，必须 configurable、versioned 且可通过 evaluation 比较。

---

## 11.4 Recency / Conflict Policy

如果 Project Knowledge 之间冲突，不允许简单“相似度最高即答案”，也不采用固定的 `Announcement > Docs > FAQ > Whitepaper` 解决所有问题。不同 query 类型可能需要不同来源；M2 P0 不做 AI query router，但保存完整 type/channel/authority/recency/validity，并使用 versioned authority policy。

P0 retrieval baseline：

```text
original query
→ BM25 / FTS lexical retrieval + multilingual embedding retrieval
→ Reciprocal Rank Fusion
→ authority + validity + recency metadata policy
→ bounded source-diverse candidate selection
→ bounded Top-20 candidates
→ validated multilingual reranker（仅显式配置 remote LLM 时）
→ Top-5 fine-grained chunks
→ bounded parent / neighbor context expansion
→ answer status + citations
→ citation validation
```

不使用随意加权的“综合事实分”。Source diversity 只能对已有 local hybrid candidates 做通用、有界、versioned 的选择，不得按项目或 source type 写专用规则，也不得用硬 cap 牺牲长文、多事实或跨语言召回；远程候选总量仍受 Top-20 限制。Context expansion 有明确数量/字符上限，不无界发送整份文档。Reranker 只能重排已有 candidate，返回未知、重复、缺失 ID 或 provider timeout/failure 时确定性回退 RRF Top-5；remote LLM 未配置时同样走 RRF Top-5。Query rewrite、multi-query 仍须等待新的固定 benchmark failure evidence。

Answer status contract：`grounded | conflict | outdated_only | no_authoritative_source | insufficient_evidence`。`conflict` 必须并列展示当前有效且互相冲突的官方依据；“检索相关”不等于“事实被证明”。

M2.1 质量细化（不新增产品 scope）：最终回答消费 selected citation chunks 与 bounded neighbor context，而非首条摘录；区分 retrieval relevance、answerability、groundedness。逐项检查问题要求的 material facts，`TBD` 或仅相关材料不足以产生 `grounded`。结构信息用于派生 retrieval representation，citation 仍指向原始 source/revision/chunk。答案模型须显式配置；未配置或校验失败时不得以相似度代替语义覆盖判断。原 34 条 TON external queries 固定为 regression set，另设先固定文档、再锁题且只运行一次的 document-disjoint holdout。

Incremental indexing：新 source 只处理自身；内容变化创建新 revision 并只索引新 revision；相同 `content_hash` 不重复 parse/chunk/embed。

### FR-KB-001

RAG retrieval 必须保留 source metadata 和 chunk provenance。

### FR-KB-002

回答项目事实时，Agent 必须引用 Knowledge Source。

### FR-KB-003

当两个官方来源冲突时，Agent 必须显示冲突，不自行编造统一结论。

### FR-KB-004

过期知识不得无提示用于当前事实判断。

### FR-KB-005

没有可靠官方知识时，允许输出：

> No authoritative project source found.

---

## 11.5 RAG 使用边界

### Primary use — Investigation Grounding

RAG 默认在 Investigation 需要项目事实时调用。

典型场景：

#### Community Claim Verification

社区集中传播一个说法时，检查：

- 官方是否真的说过；
- 截至 `as_of_time` 是否已经发布；
- 当前是否存在 conflicting source；
- claim 是否 unsupported。

#### Rule / Campaign Clarification

社区对活动条件、奖励、eligibility、deadline、规则产生 confusion 时，自动关联相关官方说明。

#### Historical Rule Verification

用户声称“以前规则不是这样”时，检查：

- 历史 source；
- 新旧规则；
- publication / validity 时间；
- supersession 关系。

#### Incident Context

Product Issue / Complaint 突然上升时，检查近期：

- maintenance；
- known issue；
- release；
- product change；
- official acknowledgement。

如果没有相关官方信息，也要明确返回：

> No related authoritative source found.

#### Response Guidance Grounding

在 Community Lead / Mod 准备统一回复口径前，提供：

- 可以确认的官方事实；
- 不应宣称的未确认内容；
- 对应 source citation。

### Secondary use — Conversational Follow-up

Community Lead 可以在 Investigate 后继续追问 Project Knowledge，但对话不是 RAG 的唯一或主要入口。

### 不需要 RAG

以下事实仍由 deterministic / statistical layer 直接计算：

- message count；
- unique users；
- reply graph；
- response latency；
- duplicates；
- participation trend；
- user concentration；
- activity mode。

原则：

> **能从社区数据直接计算的，不调用 RAG；需要核查项目官方事实时才调用 RAG。**

---

# 12. Risk & Opportunity Signal Engine

## 12.1 Signal 结构

Signal 由多类事实组合生成：

```text
Topic / Behavior
+
Trend
+
Unique Users
+
Persistence
+
Role distribution
+
Response status
+
Hygiene
+
Evidence
```

Signal 默认基于 Community Evidence 产生，不要求每个 Signal 在触发前完成 RAG。

Signal 需要为后续 Investigation 提供：

- affected subject / Topic；
- Behavior；
- observed claims；
- representative Evidence；
- trend / persistence；
- affected communities；
- time window；
- `knowledge_check_needed`；
- `knowledge_check_reason`。

`knowledge_check_reason` 是解释 M4 为什么要求 Investigation 调用 M2 的版本化 reason code。`knowledge_check_needed=true` 时必须记录，`false` 时为空；它不得保存模型隐藏推理。示例：

```text
community_claim_requires_official_verification
product_issue_requires_maintenance_context
```

只有明确依赖官方事实才能定义的 recipe 可以执行轻量 Knowledge check；完整 Official Context enrichment 默认发生在 Investigate。

这避免 Knowledge latency 阻塞 Sense / Signal，同时确保需要事实核查的问题在 Investigation 阶段获得官方 grounding。

### FR-SIGNAL-001

单条消息默认不能生成 High-severity community incident。

### FR-SIGNAL-002

每个 Signal 至少记录：

```text
signal_id
type
risk_or_opportunity
community_ids
detected_at
window
trigger_metrics
topic_ids
behavior_types
observed_claims
knowledge_check_needed
knowledge_check_reason
knowledge_refs（optional）
evidence_ids
confidence
status
```

### FR-SIGNAL-003

用户必须能知道“为什么触发”。

---

# 13. Ask Community — Follow-up Copilot Surface

Ask Community 是 Community Lead 的自由调查、解释与人工纠错入口，但不是 RAG 的主要触发方式。

Hero Flow 优先：

> Signal → Investigate → automatic Official Context

Ask Community 主要承担：

- 对 Investigation 继续追问；
- Explain；
- cross-community comparison；
- Project Knowledge follow-up；
- Human Intervention / Correction。

## 13.1 Explain

用户可以问：

- 为什么这是 Product Issue？
- 为什么 CN 被标记 Needs Attention？
- 这条 FUD 和官方文档是否一致？
- 为什么 A31 被识别成 Contributor？

Agent 基于：

- analysis tools；
- Evidence；
- Project Knowledge

解释。

---

## 13.2 Investigate

Investigation 可以从两类入口开始：

### Signal-driven

Community Lead 从 Need Attention / Opportunity 点击 `Investigate`。

系统自动继承 Signal 和 Community Evidence，不要求用户重新描述问题。

### Free-form

Community Lead 也可以主动提出调查问题，例如：

- 最近为什么 Quest reward confusion 上升？
- 哪些问题没有被 Mod 处理？
- CN 和 ES 是否出现同一种产品问题？
- 官方是否承认了这个 issue？

两类入口最终都转换成统一的 `InvestigationContext`。

Project Knowledge retrieval 是 Investigation 内部工具调用，不要求用户手动提出一个 RAG query。

---

## 13.3 Human Intervention / Correction

Chat 也是人工纠错入口。

示例：

> “这不是 Bug，是计划内维护。”

系统应提出结构化修改：

```text
Proposed correction

Finding:
Product Issue
→ Planned Maintenance

Scope:
Current incident

Reason:
Human review

[Confirm] [Cancel]
```

其他支持的 correction：

- User → Moderator；
- Topic Rename；
- Topic Merge；
- Behavior Relabel；
- Signal Dismiss；
- Contributor Remove / Confirm；
- Project Knowledge Update suggestion。

### FR-CHAT-001

Chat 不允许直接静默修改系统状态。

流程必须是：

```text
Natural language instruction
→ Agent interprets intent
→ Structured proposed action
→ Human confirmation
→ State change
→ Audit record
```

### FR-CHAT-002

原始聊天永远不可修改。

### FR-CHAT-003

所有人工 correction 记录：

```text
actor
timestamp
previous_value
new_value
scope
reason
source = human_review
```

---

# 14. Investigation Agent

## 14.1 定义

Investigation Agent 是 MVP 的主要 Agent。

它不是“总结聊天”，也不是“Knowledge Chatbot”。

它的任务是：

> **从一个值得关注的 Community Signal / 调查目标出发，组织 Community Evidence、自动补充 Official Context，并帮助 Community Lead 判断现在已知什么、未知什么以及下一步应该检查什么。**

Investigation 的核心不是生成一个听起来合理的解释，而是建立：

```text
Community State
+
Community Evidence
+
Official Context
+
Known / Unknown boundary
```

---

## 14.2 Agent 入口

A. Need Attention → `Investigate`

B. Opportunity → `Investigate`

C. Ask Community free-form investigation

Signal-driven Investigation 为 MVP Hero Path。

---

## 14.3 Investigation Context

Investigation 开始时必须形成 versioned `InvestigationContext`：

```text
source_type = signal | free_form
signal_id（optional；仅 Signal-driven）
community_ids[]
analysis_window
as_of_time

topic_ids[]
behavior_types[]

observed_claims[]
community_evidence_ids[]

trigger_fact_ids[]
affected_scope

investigation_goal
knowledge_check_needed
knowledge_check_reason

context_version
```

其中：

- `observed_claims` 来自 Community Evidence，不得冒充官方事实；
- `as_of_time` 默认继承被调查社区事件的时间边界；
- `investigation_goal` 可以由 Signal recipe 产生，也可以来自 Lead free-form intent；
- `knowledge_check_reason` 在 `knowledge_check_needed=true` 时必须继承或生成可审计的版本化 reason code；
- Knowledge retrieval 可以将 Context 转换成内部 retrieval intent，但不得改写原始 Community Evidence。

---

## 14.4 Tool Contract

MVP 概念工具：

```text
get_activity_trend
get_topic_trend
get_behavior_distribution
get_role_concentration
get_unanswered_questions
get_response_latency
get_reply_graph_summary
get_hygiene_signals
compare_communities
get_mod_performance
get_contributor_candidates
get_community_timeline
compare_reported_vs_observed
retrieve_conversation_evidence
retrieve_project_knowledge
```

实际函数拆分由 Technical Design 决定。

---

### Official Context

`retrieve_project_knowledge` 返回的不只是搜索结果列表，而是 Investigation 中的 `OfficialContext`：

```text
as_of_time

source_ids[]
revision_ids[]
chunk_ids[]

supported_facts[]
conflicting_facts[]
historical_changes[]

unsupported_community_claims[]
unknowns[]

answer_status
citation_refs[]
```

Official Context 必须保留真实 Source / Revision / Chunk provenance。

没有匹配官方资料时，`unknowns` / `no_authoritative_source` 是合法输出，不得为了给 Investigation 一个结论而补全不存在的官方事实。

---

## 14.5 Agent Limits

### FR-AGENT-001

一次 Investigation 最多 5 个工具步骤。

### FR-AGENT-002

Agent 必须根据前一步结果决定后续步骤，不固定全量调用。

### FR-AGENT-003

最终输出固定结构：

```text
Finding

What we see in the community
Community Evidence

What official sources say
Official Context + citations

What we know
What remains unknown

Confidence
Possible Cause
Suggested Next Action
```

### FR-AGENT-004

所有 material factual claims 必须来自：

- analysis tool result；
- source evidence；
- Project Knowledge。

### FR-AGENT-005

没有足够证据时输出：

> Insufficient Evidence

### FR-AGENT-006

不得输出不存在的 message ID / source ID。

### FR-AGENT-007

不得将 association 直接描述为 causality。

### FR-AGENT-008

Signal-driven Investigation 中，如果 `knowledge_check_needed=true`，Agent 必须记录 `knowledge_check_reason`，并在形成 project-specific factual diagnosis 前尝试 Project Knowledge grounding；Knowledge unavailable 时必须显式标记，不得使用模型记忆替代。

---

# 15. Suggested Next Action — MVP 边界

Investigation Agent 可以提供 **低风险、直接、可人工执行的下一步建议**。

允许：

- Update FAQ
- Ask a Mod to respond
- Review unanswered questions
- Publish clarification
- Escalate to Product / Engineering
- Review Mod coverage
- Contact a contributor
- Monitor for another period
- Check Project Knowledge freshness

不属于 MVP：

- 设计一整场 Campaign；
- 生成复杂拉新方案；
- 自动决定预算；
- 自动执行活动。

---

# 16. Community Strategy / Activity Recommendation — 后续功能定义

用户此前设想的“根据社区状态推荐活动”正式定义为：

> **Community Strategy Agent / Intervention Recommendation**

它是当前 MVP 的自然下一层，不取消。

## 16.1 Future Input

```text
Goal
+
Current Community State
+
Audience
+
Topics & Behaviors
+
Historical Operation Results
+
Project Knowledge
+
External Web3 / Language-region Trends
```

## 16.2 Future Output

```text
Recommended Intervention
Target Audience
Why Now
Mechanism
Required User Behavior
Incentive
Channel
Duration
Expected Outcome
Metrics to Watch
Risks
Evidence
```

例如：

```text
Goal:
Reactivate inactive users

Recommendation:
Low-barrier Return Quest

Why:
Staking discussion rising
+ returning-user participation low
+ FAQ confusion already resolved

Audience:
14–30 day inactive users

Metrics:
Reactivation Rate
7-day Continued Engagement
```

## 16.3 Future Principle

不是：

> Goal → LLM brainstorm

而是：

```text
Goal
+
Community State
+
Historical Response
+
Audience
+
External Context
→ Intervention
```

---

# 17. Mod Evaluation

Mod 是 Community 中的特殊角色视角。

## 17.1 使用场景

Community Lead 会根据结果进行：

- 奖金；
- 扣款；
- 培训；
- 警告；
- 调整任务；
- 分配更多职责；
- 淘汰 / 更换。

由于各项目制度不同，系统不自动输出人事决定。

---

## 17.2 P0 Scorecard

### Responsiveness

- Questions Encountered
- Questions Answered
- Question Response Rate
- Median Response Time
- Unanswered Questions

### Meaningful Contribution

- Question Answering
- Project Explanation
- Information Clarification
- Discussion Guidance
- Community Support
- Meaningful Reply Ratio

### Answer Quality / Groundedness

当回答涉及项目事实时，可使用 Knowledge Base 判断：

- Grounded in official knowledge
- Possibly outdated
- Unsupported
- Conflicting official sources
- Not enough evidence

### User Engagement

- Unique Users Engaged
- Follow-up Replies
- Conversation Continuation
- User-to-user Discussion Triggered（可阶段实现）

### Anti-gaming

- Duplicate
- Filler
- Repetitive short messages
- Burst posting

### Reporting Coverage

- Reported
- Observed
- Matched
- Observed-but-not-reported
- Reported-only

---

## 17.3 Mod Report vs Observed

输入：

```text
community
period
raw_mod_report
author optional
```

系统抽取：

```text
reported_topics
reported_issues
reported_actions
```

比较：

```text
Reported
vs
Observed
```

输出：

> Potential Reporting Gap

不得推断：

> Mod 故意隐瞒。

---

# 18. Contributor Radar

## 18.1 High Contributors

已经持续创造明确价值。

运营动作：

- 优先联系；
- 项目代币奖励；
- 内测；
- Discord Title；
- Contributor / Ambassador pipeline。

信号：

- Peer Support
- Knowledge Contribution
- Content Creation
- Unique Users Helped
- Project Relevance
- Consistency
- Low Gaming Risk

---

## 18.2 Emerging Contributors

近期贡献趋势明显增长。

运营动作：

- Watchlist；
- 活动机会时联系；
- 继续观察。

信号：

- contribution trend；
- users-helped trend；
- active-day consistency；
- advocacy growth；
- low gaming risk。

### FR-CONTRIB-001

不得把 message volume 作为唯一排序依据。

### FR-CONTRIB-002

必须展示 Why Surfaced。

### FR-CONTRIB-003

必须可以查看代表性聊天。

### FR-CONTRIB-004

无可靠候选时返回空结果。

---

# 19. Evidence / Original Conversation

这是全产品核心公共能力。

## 19.1 Conversation Drawer

每个 Finding 可打开：

```text
Original Message
Optional Translation
Author
Role
Community
Timestamp
Parent / Child Reply Context
Topic
Behavior
Status
Method
Confidence
Related Finding
Knowledge Source（如适用）
```

### FR-EVID-001

默认展示 conversation context，不只展示单句。

### FR-EVID-002

Original 与 Translation 必须清楚区分。

### FR-EVID-003

AI Interpretation 不得覆盖原文。

### FR-EVID-004

用户可以在 Related Evidence 中前后切换。

---

# 20. AI / Deterministic Responsibility Boundary

## Deterministic / Statistical

- message count；
- unique users；
- role share；
- reply graph；
- response latency；
- duplicates；
- burst；
- time comparison；
- concentration；
- metric aggregation。

## Semantic / AI

- cross-language topic；
- behavior；
- confusion vs complaint；
- FUD / misinformation；
- meaningful contribution；
- Mod Report extraction；
- knowledge-grounded answer quality；
- AI Brief；
- Agent planning；
- final synthesis。

## RAG

只在需要核查项目官方事实时调用。

RAG 的默认调用方是 Investigation，而不是 raw community message。

Raw Conversation 不直接自动进入 Project Knowledge QA。

正确主路径为：

```text
Conversation
→ Topic / Behavior / Reply
→ Signal
→ Investigation Context
→ Project Knowledge retrieval
→ Official Context
→ Diagnosis
```

Conversational Knowledge QA 是 secondary follow-up。

---

# 21. AI Uncertainty UX

统一状态：

```text
High confidence
Medium confidence
Low confidence
Uncertain
Insufficient Evidence
```

原则：

- 不使用未经校准的“87%准确率”式 confidence；
- High-risk Signal 必须 Evidence-backed；
- 用户能低成本查看原文；
- RAG conflict 必须显式展示；
- Agent 不确定时不强答。

---

# 22. Prompt Injection / Trust Boundary

Community Chat 和 Knowledge Document 都视为：

> **Untrusted Input**

必须防止：

- `ignore previous instructions`
- embedded tool instructions
- fake system prompts

Agent 只把内容作为分析数据。

不得执行文档 / 聊天中的指令。

---

# 23. Privacy

P0 原则：

- local-first；
- user IDs hash；
- private chats 不进入 Git；
- remote LLM 需要明确配置；
- remote LLM 只发送必要 Evidence / Knowledge snippets；
- 不把完整 corpus 默认上传；
- API key 不进入 report / log / evidence；
- 不建立敏感人格画像。

---

# 24. Evaluation Plan

## 24.1 Product Success Metrics

必须最终测：

1. **Human Review Time Reduction**
2. **Issue Detection Lead Time**
3. **Human Agreement**

所有数值必须真实测试后填写。

---

## 24.2 Topic Evaluation

- Recall@K / retrieval quality
- cluster coherence
- cross-language alignment
- representative evidence validity

---

## 24.3 Behavior Evaluation

P0 8 类 + Uncertain。

- Macro F1
- Per-class P/R/F1
- Confusion Matrix
- N
- language distribution
- class distribution

---

## 24.4 Signal Evaluation

- precision
- recall
- false-positive rate
- detection latency
- evidence validity

---

## 24.5 M2 Knowledge Component Evaluation

M2 继续保留组件级 regression，用于证明 Knowledge retrieval engine 本身没有退化。

该 evaluation 不等同于 Community Lead 的最终业务价值评价。

固定覆盖：

- multi-source official knowledge；
- EN / CN / ES；
- cross-language retrieval；
- long document；
- FAQ；
- Official Announcement；
- Official Blog；
- Release Notes；
- conflicting / superseded sources；
- historical `as_of_time`；
- no-answer；
- prompt injection。

组件级固定报告：

### Retrieval

- Hit@1 / @3 / @5
- Precision@1 / @3 / @5
- Recall@1 / @3 / @5
- R-Precision
- MRR
- nDCG@5

### Answer / Grounding

- Complete Answer Rate
- False Grounded Rate
- Insufficient Evidence Accuracy
- No-answer Accuracy
- Citation Validity
- conflict / outdated handling
- unsupported answer rate

### Runtime

- remote calls/query
- tokens/query
- estimated cost/query
- p50 / p95 latency
- bounded Evidence payload

2026-09-10 冻结的 M2 Retrieval / Ranking production baseline 继续作为 component regression。2026-09-11 的 backward-compatible temporal metadata contract v3 compatibility update 不重新打开 chunking、embedding、RRF、reranker 或 authority policy 优化。

除非新的固定 component benchmark 发现明确 regression，不因 Investigation evaluation 调整 chunking、embedding、RRF、reranker 或 authority policy。

---

## 24.6 Investigation Grounding Evaluation

M2 的主要业务价值在 M3 / M4 / Investigation 联动后评价。

Primary business benchmark 不再使用：

> raw community utterance → direct RAG answer

作为 P0 主评测。

新的 evaluation unit 是：

> **真实 Community Signal / Investigation Context → 正确 Official Context**

Evaluation case 来自真实社区事件或 Signal，不从 Knowledge 反向生成。

每个 case 至少包含：

```text
signal / investigation goal
community window
community evidence refs
observed claims
as_of_time

required official facts
acceptable evidence set(s)
forbidden future / invalid evidence

expected:
supported / conflict / historical change /
no authoritative evidence / insufficient evidence
```

Gold 采用 fact-first contract：每个 required official fact 可以对应一个或多个 acceptable evidence set。只要系统找到该事实，并引用任一有效、可追溯且时间正确的官方证据，即可满足该项；不得把命中预先指定的唯一 source 或 chunk 作为通过条件。

核心指标：

```text
Official Context Recall@K
Required Fact Coverage
No-authoritative-evidence Accuracy
Historical Correctness
Conflict Detection Accuracy
Citation Validity
Unsupported Official Claim Rate
Investigation Grounding Latency
Investigation Grounding Cost
```

并拆分：

- rule / campaign clarification；
- misinformation verification；
- historical rule change；
- incident context；
- maintenance / known issue；
- Blog-only；
- Telegram-only；
- multi-source；
- cross-language。

特别要求：

> Signal/Investigation 与 Gold Official Context 必须独立于待测 product retrieval 建立。

此前冻结的 `60 real-community raw queries` 与 Gold Protocol v1/v2 失败实验保留为 research asset，用于说明 message-level QA 与 Community Lead 主工作流不匹配，不再作为 P0 primary RAG business benchmark（`deprecated as primary P0 RAG business benchmark / retained research asset`）。

---

## 24.7 Agent Evaluation

Benchmark Question 示例：

- Why did CN activity rise?
- Are wallet complaints spreading?
- Which Mod needs review?
- Is this claim inconsistent with official docs?
- Why is ES support pressure rising?

评价：

- tool selection relevance；
- max-step compliance；
- unsupported claim rate；
- evidence citation validity；
- knowledge citation validity；
- answer usefulness；
- Investigation Context completeness；
- community evidence / official evidence separation；
- knowledge tool invocation relevance；
- Official Context coverage；
- known / unknown boundary correctness；
- unnecessary RAG invocation rate；
- knowledge-check reason validity；
- project-specific unsupported claim rate。

Material unsupported claim：

> 必须接近 0。

---

# 25. Cost / Latency Targets

以下是产品目标，需开发后 benchmark。

## Local UI

- page transition p95 < 500ms
- Evidence Drawer p95 < 1s

## Analysis

目标规模：

```text
3 communities
7 days
~10k messages
```

目标：

- deterministic + local semantic p95 ≤ 60s

## Brief

- p95 ≤ 15s

## Investigation

- max 5 tool calls
- p95 ≤ 30s
- remote LLM target ≤ $0.10 / investigation

成本不应通过删除 Evidence / safety 验证来优化。

---

# 26. Fallback

## Semantic unavailable

- deterministic 正常运行；
- semantic feature 明确 unavailable。

## LLM unavailable

- structured analysis 继续；
- Brief / Agent unavailable；
- 不伪造 AI result。

## Knowledge Base empty

- community analysis 正常；
- project-specific factual judgment 标记 unavailable。

## Conflicting knowledge

- 输出 conflict；
- 不自行决定“官方真实答案”。

## Mod 未配置

- community analysis 继续；
- Mod Evaluation unavailable。

## Mod Report 缺失

- Reported vs Observed unavailable。

---

# 27. Edge Cases

| Scenario | Expected |
|---|---|
| 数据量过少 | Insufficient Data，不强诊断 |
| 某语言区无新增消息 | No new activity |
| 同一 Topic 跨 EN/CN/ES | 合并 Global Topic |
| 同一消息兼具 Question + Product Issue | primary + secondary |
| “我也遇到了” | 结合 thread context |
| Mod self-reply | 不计 user engagement |
| 重复公告 | repetitive signal，不直接认定作弊 |
| Mod 没汇报某问题 | Potential Reporting Gap |
| Mod 汇报问题但数据未观察到 | Reported-only / insufficient observed evidence |
| 用户纠正 AI | Proposed structured change → Confirm |
| KB 旧文档与新公告冲突 | 展示冲突，优先提示 recency |
| Agent 无法找到原因 | Insufficient Evidence + next check |
| Agent tools 结果矛盾 | Conflicting Signals |
| LLM timeout | graceful unavailable |
| Chat 中 Prompt Injection | ignore as instruction |
| Knowledge doc 中 Prompt Injection | ignore as instruction |
| Contributor volume 高但 filler 高 | 不自动进入 High Contributor |
| Emerging 之后下降 | 从 Watchlist 自然退出 |

---

# 28. 数据模型（产品层 Contract）

## Workspace

```text
workspace_id
project_name
created_at
```

## Community

```text
community_id
workspace_id
name
language
platform
timezone
```

## Message

```text
message_id
community_id
language
user_id_hash
user_role
timestamp
text
reply_to_message_id
source_batch_id
```

## SyncBatch

```text
source_batch_id
community_id
source_type
window_start
window_end
imported_at
content_hash
```

## KnowledgeSource

```text
source_id / workspace_id / title
source_type / source_channel
canonical_url / platform / platform_content_id / author
language / project_scope
authority_level / official_status / source_owner / verification_method
metadata_provenance / semantic_tags
created_at
```

## KnowledgeRevision

```text
revision_id / source_id / version / content_hash / status
published_on / published_at / temporal_precision
updated_at / effective_from / effective_until
ingested_at / observed_at / superseded_at / source_timezone
supersedes_source_id / supersedes_revision_id
superseded_by_source_id / superseded_by_revision_id
parser_version / chunk_strategy / chunk_strategy_version
embedding_model / embedding_revision / index_version
parse_status / index_status / error
```

## KnowledgeChunk

```text
chunk_id / source_id / revision_id
section / parent_heading / page / ordinal
language / token_count / text
validity / authority / embedding_ref
```

## Topic

```text
topic_id
canonical_name
message_ids
community_distribution
language_distribution
trend
representative_message_ids
method
confidence
review_status
```

## BehaviorJudgment

```text
message_id
primary_behavior
secondary_behaviors[]
confidence
method
context_message_ids[]
review_status
```

## Signal

```text
signal_id
signal_type
risk_or_opportunity
community_ids[]
detected_at
analysis_window
trigger_metrics
topic_ids[]
behavior_types[]
observed_claims[]
knowledge_check_needed
knowledge_check_reason
knowledge_refs[]（optional）
evidence_ids[]
confidence
status
```

## ModReport

```text
report_id
community_id
author_user_id_hash
period_start
period_end
raw_text
reported_topics[]
reported_issues[]
reported_actions[]
```

## ModPerformance

```text
community_id
moderator_id
analysis_window
responsiveness
meaningful_contribution
answer_groundedness
user_engagement
anti_gaming
reporting_coverage
evidence_ids[]
```

## ContributorCandidate

```text
user_id_hash
community_id
candidate_type
signals[]
trend
why_surfaced
evidence_ids[]
review_status
```

## InvestigationContext

```text
investigation_context_id

source_type = signal | free_form
signal_id（optional；仅 Signal-driven）

community_ids[]
analysis_window
as_of_time

topic_ids[]
behavior_types[]

observed_claims[]
community_evidence_ids[]
trigger_fact_ids[]

investigation_goal
knowledge_check_needed
knowledge_check_reason

context_version
created_at
```

## OfficialContext

```text
official_context_id
investigation_context_id

as_of_time

source_ids[]
revision_ids[]
chunk_ids[]

supported_facts[]
conflicting_facts[]
historical_changes[]
unsupported_community_claims[]
unknowns[]

answer_status
citation_refs[]

retrieval_method
retrieval_version
created_at
```

## Investigation

```text
investigation_id
investigation_context_id

tool_steps[]

finding
community_evidence_ids[]
official_context_id

known_facts[]
unknowns[]

confidence
possible_cause
suggested_next_action

model
prompt_version
method_version

question（optional；仅 free-form Investigate）
```

## HumanCorrection

```text
correction_id
actor
timestamp
target_type
target_id
previous_value
new_value
scope
reason
```

---

# 29. 现有代码复用

当前本地项目：

```text
/Users/enm1cuarto/Documents/Codex/community-intelligence-ai
```

P0 应优先复用：

```text
Telegram JSON importer
anonymization
synthetic generator
hygiene
activation
reply episodes
seed behavior baseline
TF-IDF/KMeans baseline
semantic provider
evidence records
FastAPI local app
React app shell
test suite
```

旧功能降级但不删除：

- Campaign Intelligence
- Metric Lab
- standalone Response Patterns
- research-heavy Behavior Explorer

它们可保留作：

- internal analysis；
- future feature；
- evaluation baseline。

---

# 30. 需要新增 / 重构的技术能力

Technical Design 必须覆盖：

1. Workspace + Community model
2. SyncBatch / freshness
3. Mod role configuration
4. Project Knowledge ingestion
5. RAG index / retrieval
6. knowledge version / recency policy
7. period comparison
8. cross-language Topic pipeline
9. P0 Behavior classifier
10. Signal engine
11. Brief generator
12. Ask Community
13. Investigation Agent
14. tool layer
15. structured human correction
16. Mod Report parser
17. Reported vs Observed
18. per-Mod aggregation
19. Contributor Radar
20. global Evidence Drawer
21. frontend IA migration
22. evaluation fixtures

---

# 31. Development Milestones

不预估时间，仅定义依赖顺序。

## M0 — Product Contract

- PRD freeze
- Wireframe
- Technical Design
- API / schema freeze

## M1 — Data Foundation

- Workspace
- Communities
- Mod config
- SyncBatch
- freshness
- period comparison

## M2 — Knowledge Base

**状态：M2 Retrieval / Ranking production baseline Frozen（2026-09-10）；temporal metadata contract 于 2026-09-11 完成 backward-compatible v3 compatibility update。** Freeze 表示 retrieval/ranking baseline 已达到 MVP 后续依赖条件；正式版本、验收证据和不阻塞限制记录于 `docs/10_M2_FREEZE_RECORD.md`。本次 temporal metadata update 支持 `published_on / published_at / temporal_precision`，未重新打开 chunking、embedding、RRF、reranker 或 authority policy 优化。后续对冻结 baseline 的改变仍需通过独立 evaluation evidence 和版本升级进入 backlog。

M2 Retrieval / Ranking baseline Freeze 表示该检索组件可被后续模块依赖，不代表 temporal metadata contract 永久不可演进，也不代表其 Community Lead 业务价值已独立完成验收。

M2 的业务级 acceptance 与 M3/M4/M5 联动，在 Signal-driven Investigation 中完成。

- multi-source file/manual ingestion 与完整 metadata
- versioned revision、historical validity、incremental indexing
- structure-aware chunking 与 bounded context expansion
- FTS5 + multilingual embedding + RRF retrieval
- citation provenance 与五类 answer status
- generic EN/CN/ES fixture/evaluation
- Knowledge Product Review Surface

## M3 — Conversation Intelligence

- Global Topic
- Behavior
- Evidence

## M4 — Signal Home

- deterministic facts
- Risk / Opportunity Signals
- Brief
- Need Attention
- Opportunities
- Timeline
- observed claims
- knowledge-check-needed flag + reason
- Investigation Context handoff

## M5 — Investigation / Copilot

- Signal → Investigation Context
- Community Evidence tools
- Project Knowledge grounding
- Official Context
- known / unknown synthesis
- Ask Community follow-up
- bounded Agent

## M6 — Human Intervention

- correction proposal
- confirmation
- audit record

## M7 — Mod

- scorecard
- answer groundedness
- Mod Report
- Reported vs Observed

## M8 — Contributor

- High
- Emerging
- Evidence

## M9 — Evaluation

- Topic
- Behavior
- Signal
- M2 component regression
- Signal-driven Investigation Grounding
- Agent
- human productivity

## M10 — Portfolio Demo

- fixed reproducible dataset
- 90-second Hero Flow
- 3–5 min full walkthrough

---

# 32. MVP Definition of Done

只有以下全部满足，才能声称 MVP 完成。

## Data

- [ ] EN/CN/ES workspace 可运行
- [ ] Telegram JSON 可导入
- [ ] Mod 可人工配置
- [ ] 分析支持 since-last-check / 24h / 7d / 30d
- [ ] freshness 可见

## Knowledge

- [ ] 白皮书 / Docs / FAQ / Announcement 至少一种真实格式可导入
- [ ] retrieval 返回 source citation
- [ ] outdated / conflicting source 可识别
- [ ] 无 source 时不编答案
- [ ] Knowledge 可以由 Investigation Context 自动调用，不要求 Lead 手写 query

## Conversations

- [ ] 跨语言 Topic 对齐
- [ ] P0 Behavior 可识别
- [ ] Uncertain 可输出
- [ ] Topic / Behavior 可定位到原始对话

## Home

- [ ] AI Brief
- [ ] Need Attention
- [ ] Opportunity
- [ ] Timeline
- [ ] 每个重要 Finding 可下钻 Evidence

## Agent

- [ ] Ask Community 可用
- [ ] Need Attention → Investigate 可用
- [ ] Signal → Investigate 自动继承 Community Evidence
- [ ] ≤5 tool calls
- [ ] 支持 Knowledge retrieval
- [ ] `knowledge_check_needed` 时记录 `knowledge_check_reason` 并可生成 Official Context
- [ ] Community Evidence 与 Official Context 分开展示
- [ ] 能明确展示 What we know / What remains unknown
- [ ] 无 authoritative source 时不使用模型记忆补答案
- [ ] unsupported material claim 不允许
- [ ] Evidence 可打开

## Human Intervention

- [ ] Chat 可提出至少一种结构化 correction
- [ ] 必须 Confirm 后写入
- [ ] 原始聊天不可修改
- [ ] correction 有 audit trail

## Mod

- [ ] Scorecard 不使用黑盒总分
- [ ] Mod Report 可输入
- [ ] Reported vs Observed
- [ ] answer groundedness 可在有知识源时展示
- [ ] 判断可看 Evidence

## Contributor

- [ ] High 与 Emerging 分开
- [ ] Why Surfaced
- [ ] Evidence
- [ ] 可返回空候选

## Evaluation

- [ ] Topic benchmark
- [ ] Behavior benchmark
- [ ] Signal benchmark
- [ ] M2 component regression
- [ ] Signal-driven Investigation Grounding benchmark
- [ ] Agent benchmark
- [ ] human review time experiment protocol
- [ ] issue lead-time experiment protocol

---

# 33. Open Questions for Wireframe / Technical Design

以下不阻塞 PRD，但必须在对应开发前冻结：

1. Ask Community 是右侧持久 Copilot Panel，还是独立页面？
2. 推荐：桌面端使用右侧 persistent panel；移动端 full-screen。
3. Evidence Drawer 与 Ask Community 是否共用右侧区域？
4. Knowledge P0 格式已冻结为 `.md` / `.txt` / text-based `.pdf`；OCR unavailable。
5. Knowledge Source 允许人工设置 offset-aware validity period，并记录 metadata provenance。
6. Brief 最终是“一段总结 + 卡片”，还是完全 structured？
7. Risk Severity P0 是否用 High / Medium / Low？
8. Topic 是否允许用户手工 Merge / Rename 在 P0 就落盘？
9. Human Correction 先支持哪些 action？
10. Mod Report 是否需要历史列表？
11. RAG P0 使用 versioned authority/validity/recency lexicographic policy；query-sensitive routing 由 benchmark failure case 决定。
12. P0 是否需要机器翻译，还是先只显示 original + optional generated translation？
13. Investigation 的 Suggested Next Action 是否需要预定义 action taxonomy？
14. Agent chat history 是否跨 session 保留？
15. Project Knowledge 更新后是否自动重新检查相关旧 Finding？

---

# 34. Future Strategy Agent — 保留的长期产品故事

当前 MVP 解决：

```text
发生了什么？
为什么？
依据是什么？
```

下一阶段解决：

```text
那我应该做什么？
```

最终：

```text
Goal
↓
Community State
↓
Audience
↓
Project Context
↓
Historical Outcome
↓
External Trend
↓
Intervention Recommendation
↓
Human Approval
↓
Execution
↓
Outcome
↓
Learning
```

产品长期目标不是“做一个聊天数据分析工具”，而是：

> **把 Community Lead 日常重复的感知、调查、判断、策略和执行工作逐步 Workflow 化、Agent 化。**

---

# 35. Hero Demo Script

### 0–15s

打开 Home。

> “系统已经读完了昨晚 EN / CN / ES 的社区聊天。”

### 15–30s

显示：

```text
CN — Quest reward confusion spike
18 users affected
11 unresolved
```

社区里多名用户认为：

> “完成 Quest 后奖励应该立即到账。”

### 30–60s

点击 `Investigate`。

系统自动继承 Signal，不要求 Community Lead 输入问题。

Agent：

```text
check topic / behavior
→ inspect affected users
→ inspect unanswered questions
→ inspect Mod response
→ extract observed community claims
→ retrieve relevant official knowledge
→ compare official context
```

页面显示：

What we see in the community

- Quest reward 相关 confusion 明显增加；
- 多名用户预期完成后即时到账；
- 当前存在未回复问题。

What official sources say

- 官方 Announcement / Blog 明确说明参与条件和奖励规则；
- 当前没有找到“完成后即时到账”的官方承诺。

What remains unknown

- 当前反馈是单纯理解偏差，还是实际发放异常，官方资料不足以确认。

Suggested Next Action

- 统一 Mod 回复口径；
- 向 Product team 确认实际 reward distribution 状态；
- 必要时发布 clarification。

### 60–75s

点击 Official Context：

查看真实 Blog / Telegram Announcement citation。

点击 Community Evidence：

查看对应 CN 原始聊天。

### 75–90s

Community Lead 继续追问：

> “根据当前官方信息，帮我整理一版给 Mods 的回复口径。”

或者进行 Human Correction：

> “这个问题已经确认是计划内维护。”

系统提出 structured correction，等待人工 Confirm。

这 90 秒展示：

- Community Sense；
- Signal prioritization；
- Investigation；
- automatic RAG grounding；
- official/community evidence separation；
- Agent；
- Human-in-the-loop。

---

# 36. Revision History

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-09-09 | Community Pulse / Conversation / Mod / Contributor 初版 |
| v2.0 | 2026-09-10 | Brief-first、Signal-first、Investigation Agent、Reported vs Observed |
| **v2.1** | **2026-09-10** | **新增 Project Knowledge / RAG、Ask Community 解释与人工干预入口；明确 Suggested Next Action 与 Future Strategy Agent；重构为 Ready-for-Technical-Design PRD** |
| **v2.2** | **2026-09-11** | **重新定位 RAG 为 Signal-driven Investigation 的官方事实层；新增 Investigation Context / Official Context；明确 automatic grounding 为主、conversational RAG 为 follow-up；将 RAG 业务评测从 raw-message QA 改为 Signal/Investigation Grounding Evaluation。** |

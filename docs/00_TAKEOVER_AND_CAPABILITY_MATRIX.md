# 项目接管与能力矩阵（PRD v2.1）

状态：M0 已批准并冻结

日期：2026-09-10

唯一 active workspace：`/Users/enm1cuarto/Documents/ChatGPT/community intelligence`

只读备份：`/Users/enm1cuarto/Documents/Codex/community-intelligence-ai`

## 1. 接管结论

当前工作区已继承 v0.1 的完整 Git 历史与全部已跟踪代码，并成为后续唯一 active development workspace。现有实现作为已验证的 legacy baseline 原地保留：确定性分析、数据安全边界、证据引用完整性和本地运行壳按模块渐进适配；不清空重建。旧的七页面信息架构、Campaign/Metric-first 产品中心和整份 `report.json` 交付方式不应原样延续。PRD v2.1 是唯一产品依据。

继承基线为 commit `b5d5d02`、tag `v0.1.0-alpha`。迁移前的只读验证结果：Python `332 passed, 2 skipped`；React/Vitest `3 passed`；Python/前端 lint 与 TypeScript typecheck 均通过。只读备份中原有未跟踪文件 `docs/REAL_WORLD_VALIDATION_PLAN.md` 保持不变。本结论只证明 legacy assets 在其自身 v0.1 契约下可运行，不代表 PRD v2.1 已实现。

## 2. 状态定义

| 状态 | 含义 | 新项目处理方式 |
|---|---|---|
| Existing | 当前仓库的 v0.1 baseline 已有且本轮验证通过 | 原地保留，但仍需适配 v2.1 contract |
| Reusable | 核心逻辑和边界可直接保留 | 小步重构/接线，保留测试与 Git provenance |
| Needs Refactor | 有价值，但数据模型、语义或接口不符合 v2.1 | 保留算法/测试意图，重构外围 contract |
| New | v0.1 baseline 没有 | 在目标架构中新增并独立验收 |
| Deprecated-but-keep | 不再属于新版主路径，但未来仍有价值 | 保留为 internal/future 模块，不放入主导航 |

## 3. Existing / Reusable / Needs Refactor / New / Deprecated-but-keep

| 能力 | 旧实现证据 | 判定 | PRD v2.1 落地动作 |
|---|---|---|---|
| Telegram Desktop JSON import | `importers/telegram.py`；rich text、reply、UTC、大小限制测试 | Reusable + Needs Refactor | 保留解析与安全校验；输入改为 Workspace/Community/SyncBatch；支持多社区连续 batch、去重和 freshness |
| 用户匿名化 | importer 对 sender 做 community-scoped SHA-256 | Reusable | 保留不可逆 hash；增加 workspace salt/version 与迁移规则，不存 raw sender ID |
| Source immutable/create-only | `io.py` 的 checksum、atomic publish、symlink/race 防护 | Reusable | 用于 raw import/analysis artifact；持久业务状态改用事务数据库，不强行 create-only |
| Synthetic generator | 4 社区、4 语言、3 campaign、已知场景 | Needs Refactor | 保留可复现生成框架；重做 EN/CN/ES Hero 数据、KB、signal、Mod、contributor、correction 场景 |
| Message contract | Pydantic frozen `MessageRecord` | Needs Refactor | 增加 workspace、source batch；去除主路径对 campaign 的依赖；消息实体保持不可变 |
| Community/Workspace | 仅 manifest 中 community ID 列表 | New | 新建 Workspace、Community 实体、timezone/language/platform 配置 |
| SyncBatch/freshness | manifest 有 source hash/generated_at，但无多批次状态 | New | 新建 batch window、imported_at、content_hash、status；计算 source freshness 与 since-last-check |
| Mod role configuration | Telegram 导入全部默认 user | New | 人工维护 workspace-scoped RoleAssignment；支持有效期和审计 |
| 时间窗口/period comparison | campaign window 内聚合；无用户查看水位 | Needs Refactor | 统一 WindowSpec：since-last-check/24h/7d/30d/custom；保存 user check watermark |
| 文本标准化 | NFKC/casefold/空白归一化、多语言 filler | Reusable | 作为 deterministic preprocessing；不覆盖原文 |
| Reply graph validation | `message_rules.py` + NetworkX | Reusable | 保留图完整性和跨 community 禁止规则；输出上下文查询能力 |
| Conversation episodes | reply-tree 指标、问题/候选回答、latency/depth | Needs Refactor | 作为 support/reply 工具和 timeline 输入；不再作为一级页面；补 thread context 和窗口边界 |
| Hygiene | duplicate/filler/repetitive/burst + evidence/threshold | Reusable + Needs Refactor | 规则内核保留；统一到 Behavior guardrail 与 Signal Engine，阈值配置化/版本化 |
| Activation | meaningful interaction、peer support、response latency | Reusable + Needs Refactor | 保留公式和分母；映射到 Community Pulse、Mod、Contributor 与 Agent tools |
| Seed behavior rules | 多语言词法规则、单标签、规则 evidence | Needs Refactor | 只作为 baseline/guardrail；P0 改为 8 类、primary+secondary+Uncertain，不冒充语义分类器 |
| TF-IDF/KMeans clusters | 稳定 cluster、代表消息、pending review | Deprecated-but-keep | 保留 evaluation baseline/internal explorer；不作为 Global Topic 的生产实现 |
| Local sentence-transformer provider | 固定模型/revision/hash、离线加载、chunk pooling、rank | Reusable + Needs Refactor | 抽象为 EmbeddingProvider；用于 Topic/RAG；重新 benchmark 10k 规模与 EN/CN/ES 质量 |
| Cross-language Global Topic | 未实现；现有 cluster 不统一可靠语义 topic | New | embedding clustering + stability/noise + canonical naming + per-language trend + review |
| P0 Behavior semantic classifier | 未实现通用语义模型 | New | provider-independent multi-label pipeline；规则、semantic、LLM judge 分层，允许 abstain |
| Campaign claim baseline | curated alias/incorrect/contradiction，证据完整 | Deprecated-but-keep | 移出主路径，保留 future Campaign Intelligence 与 RAG factual-eval fixtures |
| Metric catalog/statistical validation | 10 个指标、分母、缺失、Spearman、Holm、CI | Deprecated-but-keep | 保留 internal Metric Lab/evaluation；不进入 P0 Home 或黑盒综合评分 |
| Evidence records | source_message/claim_judgment/analysis_scope，引用完整性校验 | Needs Refactor | 升级为统一 EvidenceRef + ConversationContext + KnowledgeCitation；支持 finding/tool/chat/correction |
| Original conversation UI | 单条 source evidence dialog | Needs Refactor | 改为全局 Conversation/Evidence Drawer，展示父子上下文、原文/译文、角色、方法、关联 finding |
| Knowledge ingestion | 无 | New | PDF/MD/TXT 导入、hash、版本、authority、validity、private object store |
| RAG index/retrieval | 仅有通用 embedding rank，无 KB | New | hybrid retrieval、metadata filter、recency/authority lexicographic policy、citation/conflict/no-answer |
| Community Pulse | 若干 activation/hygiene 指标，无统一 pulse contract | Needs Refactor | 形成结构化 pulse facts，不生成黑盒 health score |
| Risk/Opportunity Signal Engine | 无 | New | 版本化 deterministic recipes；组合 trend/users/persistence/support/evidence/KB；severity 非 LLM 自由生成 |
| Home AI Brief | 旧 Overview 为统计 dashboard | New | 仅消费 structured findings + representative evidence + 必要 KB；事实逐项可追溯 |
| Need Attention | 无 | New | 最多 5 项；risk taxonomy、severity、why、investigate/evidence actions |
| Opportunities | 无 | New | peer support/discussion/advocacy/contributor 信号；禁止只看消息增长 |
| Community Timeline | 无业务事件 timeline | New | 从 topic/signal/support 状态变化生成可下钻事件 |
| Ask Community | 无 | New | 全局 Copilot；Explain、free-form Investigate、Correction intent |
| Investigation Agent | 无 | New | 最多 5 步、白名单只读工具、动态规划、claim/citation validator、structured answer |
| Human Correction | 仅 UI 显示 pending，无持久修改流程 | New | proposal → confirm → apply → audit；派生判断可覆盖，原始消息不可变 |
| Mod Report | 无 | New | raw report 输入、结构化抽取、Reported vs Observed、Potential Reporting Gap |
| Per-Mod scorecard | 仅 community-level 指标 | New | 分维度展示 responsiveness/contribution/groundedness/engagement/anti-gaming/reporting，不给总分 |
| Contributor Radar | 无 | New | High/Emerging 分开、why surfaced、低 gaming 风险、evidence、空结果合法 |
| FastAPI local app | demo/import/get report/get evidence | Reusable + Needs Refactor | 保留 loopback/local packaging；改为 versioned resource API + analysis jobs + correction transaction |
| React/Vite shell | 七页导航、loading/error/mobile、Radix drawer | Reusable + Needs Refactor | 保留组件与可访问性基础；迁移到五主导航 + persistent Copilot utility dock |
| Frontend state | 单组件 `useState` 持有整份 report/evidence | Needs Refactor | server-state query cache + route/filter UI state + chat/correction finite state；按资源加载 |
| Capability fallback | available/not_available/not_implemented | Reusable | 扩展 semantic/LLM/KB/Mod/Report unavailable；禁止伪造 fallback 结果 |
| Evaluation | 规则/统计单测充分；语义真实模型仅少量 rank 测试 | Needs Refactor | 新建 Topic/Behavior/Signal/RAG/Agent/Human-productivity 分层 benchmark 与 gold set |
| Local packaging/CLI | one-command serve、wheel 内嵌前端 | Reusable | M10 前恢复一键 demo；开发期先保持前后端可独立运行 |

## 4. 当前数据流

```text
Telegram result.json ─┐
                      ├─> CommunityDataset (6-file immutable artifact)
Synthetic generator ──┘       │
                               ├─ deterministic Hygiene / Activation
                               ├─ reply Episodes
                               ├─ curated Campaign rules（可选）
                               ├─ seed Behavior + TF-IDF/KMeans
                               └─ Metric adapters/statistics（Outcome 可选）
                                        │
                                        v
                          report.json + evidence.jsonl
                                        │
                               FastAPI whole-report API
                                        │
                               React seven-view dashboard
```

关键限制：一次分析等于一个不可变目录；没有跨 batch 的 Workspace 状态；前端一次加载完整 report 与 evidence；semantic provider 没接入主流水线；没有 Knowledge/RAG、Signal、Agent 或 correction 写路径。

## 5. 当前后端、前端与 Evidence 现状

后端是 Python modular engine 加薄 FastAPI adapter。分析模块之间通过 dataclass/Pydantic 和完整 dataset/report 文件衔接，确定性强、测试严密，但 `pipeline.py` 已承担编排、序列化、capability reporting、evidence joining、metric 构建等过多职责。新版应拆分 application services，但不拆微服务。

前端是 React 19 + TypeScript + Vite。现有 AppShell 具备响应式导航、空/错/加载态、数据来源提示和 evidence dialog；ReportViews 直接依赖旧 report schema。可复用视觉/交互骨架，不应复用旧七页产品 IA。

Evidence 的优点是每个引用都能验证到 source message/claim/scope，且 confidence 语义与 review status 显式。缺口是仅支持单条证据弹窗，缺原始会话上下文、作者/角色/时间、关联 finding、KB citation、Agent tool trace 与 correction lineage。

semantic provider 是安全的本地 embedding 适配器，不是完整 semantic pipeline。它固定 `paraphrase-multilingual-MiniLM-L12-v2` 的 revision 和文件 hash，支持离线 embedding/ranking；旧主流水线明确标记 `semantic_provider_used_by_pipeline: false`。新版应复用 provider contract，不把已有模型测试误报为 Topic/Behavior/RAG 已实现。

## 6. 迁移原则

1. 在现有仓库与 Git history 上先建立 v2.1 contract，再按能力原地迁移旧模块；不清空或另起代码树。
2. 任何迁移都保留原测试意图、基线 commit 和 license/attribution 记录。
3. 原消息与 source batch 永久不可变；topic/behavior/signal 等均是可版本化派生记录。
4. deterministic facts、semantic judgments、LLM synthesis、human corrections 分层存储，UI 明确方法与状态。
5. 旧 Campaign/Metric/Response/Behavior Explorer 不删除，但在新版只作为 internal/future 路由或离线 evaluation 工具。

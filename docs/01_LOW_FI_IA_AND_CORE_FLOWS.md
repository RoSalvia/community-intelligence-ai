# Low-fi Information Architecture 与核心用户 Flow

状态：M0 已批准并冻结

产品依据：PRD v2.1

## 1. 导航与全局交互

桌面端采用五个一级入口，右侧使用一个可持久展开的 Utility Dock。`Ask Community` 与 `Evidence` 共用该区域但保持两套状态：打开 Evidence 时进入 detail stack，返回后恢复原 chat；避免两个右抽屉互相遮挡。移动端两者均为 full-screen sheet。

```text
┌──────────────┬──────────────────────────────────────┬──────────────────────┐
│ Workspace    │ Page                                 │ Utility Dock         │
│              │                                      │                      │
│ Home         │ selected page content                │ Ask Community        │
│ Conversations│                                      │   or                 │
│ Moderators   │                                      │ Evidence detail      │
│ Contributors │                                      │                      │
│ Knowledge    │                                      │ Back → preserves chat│
│              │                                      │                      │
│ Freshness    │                                      │                      │
└──────────────┴──────────────────────────────────────┴──────────────────────┘
```

全局顶部栏固定展示 Workspace、分析窗口、last checked、source freshness、analysis status；无数据或 semantic/LLM/KB/Mod 不可用时就地解释，不伪造结果。

## 2. 信息架构

| 一级入口 | 二级内容 | 用户要回答的问题 | 主动作 |
|---|---|---|---|
| Home | AI Brief、Need Attention、Opportunities、Community Timeline | 自上次查看后最值得关注什么？ | Investigate、View conversations、Mark reviewed |
| Conversations | Topics、Behaviors、Support/Replies、Community compare | 大家在谈什么、做什么、哪些问题未解决？ | 筛选、比较、打开 Evidence、Investigate |
| Moderators | Team、Scorecard、Reporting Coverage | Mod 实际做了什么，是否及时/正确覆盖问题？ | 选 Mod、看 evidence、导入 report、Investigate |
| Contributors | High、Emerging、Watchlist/Reviewed | 谁在持续或开始创造社区价值？ | 查看 why/evidence、Confirm、Remove |
| Knowledge | Sources、Conflicts、Freshness、Ingestion | 系统用什么官方事实判断？有没有过期或冲突？ | Add source、查看版本、解决 metadata 问题 |
| Ask Community | Explain、Investigate、Correction | 为什么？还能查什么？如何修正？ | Send、open citation、confirm correction |
| Evidence | Conversation context、translation、interpretation、related evidence | 原话是什么、上下文是什么、系统如何判断？ | 前后切换、Investigate、propose correction |

Campaign Intelligence、Metric Lab、standalone Response Patterns、research Behavior Explorer 不进入 P0 一级导航；保留为 `/internal/*` 或 future feature flag。

## 3. Home Brief low-fi

```text
┌ Home ───────────────────────────────────────────────────────────────┐
│ Since last check · 8h     Updated 09:10     EN/CN/ES     [Change]  │
│                                                                    │
│ Good morning. Three items need attention; one opportunity emerged. │
│ [fact-linked sentence ↗] [fact-linked sentence ↗]                  │
│                                                                    │
│ Need Attention (max 5)                      Opportunities           │
│ ┌ CN · Product/Asset Issue ──────────────┐  ┌ High Contributor ─┐ │
│ │ Wallet connection rising              │  │ A31 · EN           │ │
│ │ 18 users · 11 unresolved · High       │  │ peer support ↑     │ │
│ │ Why: trend + persistence + no support  │  │ Why surfaced       │ │
│ │ [Conversations] [Investigate]          │  │ [Evidence] [Review]│ │
│ └────────────────────────────────────────┘  └────────────────────┘ │
│                                                                    │
│ Community Timeline                                                │
│ 02:10 issue begins ─ 03:05 10 users ─ 04:20 threshold crossed      │
└────────────────────────────────────────────────────────────────────┘
```

Brief 不是自由文本总结。每个 factual span 绑定 `finding_id` 和 citation；风险与机会分区；最多显示 5 个风险，空状态为“当前窗口无足够证据的风险”，不是“一切正常”。

## 4. Conversations low-fi

```text
┌ Conversations ─────────────────────────────────────────────────────┐
│ [Topics] [Behaviors] [Support]    Community: All  Window: 7d       │
│                                                                    │
│ Global Topic: Staking Rewards        Trend +34%   Medium confidence │
│ EN 42% · CN 35% · ES 23%       56 users       8 unresolved         │
│ Representative conversations [1] [2] [3]      [Investigate]        │
│ Behavior mix: Question 38% · Confusion 24% · Peer Support 18% ...  │
│                                                                    │
│ Low-evidence cluster                                               │
│ Unnamed topic · 3 messages · Uncertain      [View conversations]    │
└────────────────────────────────────────────────────────────────────┘
```

Topics 展示 canonical topic、语言分布、趋势和代表对话；不够稳定时保留 unnamed/uncertain。Behaviors 支持 Topic/Community/Role/User/Period 过滤，并展示 primary、secondary 和 guardrail。Support 复用 reply graph，重点呈现 unanswered、latency 与 conversation context，不宣称语义上已解决。

## 5. Conversation / Evidence Drawer

```text
┌ Evidence 2 of 7 ───────────────────────────────┐
│ Finding: Wallet connection issue rising       │
│                                               │
│ CN · 03:12 · User #A91                        │
│ Original: 钱包一直连不上，有人也是吗？         │
│ Translation (generated): ...                  │
│   ↳ CN Mod · 03:19: 请先等待……                 │
│   ↳ User #B22 · 03:24: 我也遇到了              │
│                                               │
│ Topic: Wallet Connection                      │
│ Behavior: Product Issue + Help Request         │
│ Method / confidence / review status            │
│ Related KB: Troubleshooting v3 [open]          │
│                                               │
│ [Previous] [Next] [Investigate] [Correct]      │
└───────────────────────────────────────────────┘
```

原文永远优先，翻译必须标注 provider/version。Drawer 默认取 parent、selected message、children 和相邻时间片的有界上下文；AI interpretation 与原文视觉分离。聚合 scope evidence 不能冒充 source message。

## 6. Ask Community / Investigate

```text
┌ Ask Community ────────────────────────────────┐
│ Scope: CN · since last check                  │
│ User: Why is this a Product Issue?            │
│                                               │
│ Agent steps 3/5                               │
│ ✓ topic trend                                 │
│ ✓ unanswered questions                       │
│ ✓ retrieve official knowledge                │
│                                               │
│ Finding                                       │
│ ...                                           │
│ Why / Analysis Chain                          │
│ ...                                           │
│ Evidence [3 conversations]                    │
│ Knowledge [Troubleshooting v3]                │
│ Confidence: Medium                            │
│ Possible Cause: ...                           │
│ Suggested Next Action: Escalate to Product    │
└───────────────────────────────────────────────┘
```

从 Signal 进入时自动携带 signal/window/community scope；自由提问时先做 scope resolution。工具步骤按执行顺序展示，但不暴露隐藏推理；每一步显示 tool、参数摘要、结果摘要和引用。超过 5 步、证据不足、工具矛盾或 provider 失败时返回明确状态。

## 7. Human Correction flow

```text
User: 这不是 Bug，是计划内维护。
  ↓ intent parsing（不改状态）
Proposed correction
  target: signal_123
  Product Issue → Planned Maintenance
  scope: current incident
  reason: human review
  impact preview: Home card/Brief classification will update
  [Confirm] [Cancel]
  ↓ Confirm + target version check
Apply correction overlay → recompute affected findings → audit record
  ↓
Chat receipt + links to changed finding and audit detail
```

若目标已被其他 correction 更新，Confirm 返回 conflict 并要求重新预览。P0 首批写操作是 `Signal reclassify/dismiss`、`Behavior relabel`、`Topic rename`、`Role assignment`、`Contributor confirm/remove`；Topic merge 在数据 contract 稳定后加入。Knowledge Update 在 P0 只生成 ingestion suggestion，不由 chat 静默改文档。

## 8. Moderators low-fi

```text
┌ Moderators ─────────────────────────────────────────────────────────┐
│ [Team] [Reporting Coverage]     Window: 7d                          │
│ Mod A · CN                                                           │
│ Responsiveness        24/35 answered · median 8m   [Evidence]       │
│ Meaningful Contribution  explanation 8 · support 11                │
│ Answer Groundedness   14 grounded · 2 outdated · 1 conflict        │
│ User Engagement       31 users engaged · follow-up 18              │
│ Anti-gaming           duplicate 3% · filler 5%                     │
│ Reporting Coverage    4 matched · 2 observed-not-reported          │
│ No overall score. Human decision required.       [Investigate]      │
└─────────────────────────────────────────────────────────────────────┘
```

所有分维度指标都展示分母和 evidence。Reporting Coverage 使用 `Reported / Observed / Matched / Observed-but-not-reported / Reported-only`，只称 `Potential Reporting Gap`，不推断动机。

## 9. Contributors low-fi

```text
┌ Contributors ───────────────────────────────────────────────────────┐
│ [High] [Emerging] [Reviewed]                                       │
│ User A31 · EN · Emerging                                           │
│ Why surfaced: peer support ↑, 7 users helped, 5 active days        │
│ Guardrail: low filler/duplicate risk                               │
│ Representative conversations [3]          [Confirm] [Remove]       │
└─────────────────────────────────────────────────────────────────────┘
```

High 强调持续价值，Emerging 强调近期变化；排名不使用 message volume 单因子，也不生成个人敏感画像。没有可靠候选时返回空列表并解释门槛。

## 10. Knowledge low-fi

```text
┌ Knowledge ──────────────────────────────────────────────────────────┐
│ 8 sources · 1 outdated · 1 conflict          [Add source]           │
│ Title                 Type          Authority      Validity          │
│ Wallet FAQ v3         FAQ           official_faq  current            │
│ Maintenance notice    Announcement  official...  09/09–09/10        │
│ Tokenomics v1         Whitepaper    whitepaper    superseded         │
│                                                                    │
│ Conflict: Eligibility                                              │
│ Docs v4 says X ↔ Announcement 09/10 says Y     [View both]          │
└─────────────────────────────────────────────────────────────────────┘
```

首版支持 `.md`、`.txt` 与文本型 `.pdf`；扫描 PDF/OCR 显式 unavailable。用户可设置 authority、published_at、valid_from、valid_to、version。系统不自动把“相似度最高”当成最终事实。

## 11. 核心用户 Flow

### Flow A：Morning Brief → Investigation → Evidence

1. 用户打开 Home，默认 `since last check`。
2. 查看短 Brief 与最多 5 个 Need Attention。
3. 点击 CN Wallet signal 的 `Investigate`。
4. Agent 在 5 步内查询 topic、affected users、unanswered、Mod response、KB。
5. 用户打开 3 组 conversation evidence 和官方 source。
6. 用户据此选择人工执行的 Suggested Next Action；系统不自动执行。

完成标准：从 Home 到原始证据不超过 3 次主点击；所有事实引用可解析。

### Flow B：Ask Community 自由调查

1. 用户从任意页面打开 Copilot，当前页面 filter 自动成为候选 scope。
2. 用户询问“EN/CN/ES 是否都出现 wallet complaints？”
3. Agent 先确认/解析窗口，再按中间结果动态选工具。
4. 输出跨社区 finding、分析链、证据、置信状态和下一步建议。
5. 用户点击引用进入 Evidence，再返回原 chat。

完成标准：工具调用 ≤5；无引用 material claim 为 0；工具冲突显示 `Conflicting Signals`。

### Flow C：Human Correction

1. 用户在 chat 或 finding 上说“这是计划内维护”。
2. 系统生成结构化 proposal 与 impact preview。
3. 用户 Confirm 后才写 correction。
4. 受影响 signal/brief 重新派生，旧版本仍可审计。

完成标准：未 Confirm 时数据库无业务状态变化；原消息 hash 不变；audit 可追溯前后值。

### Flow D：Mod Review

1. 用户配置 Mod role 或导入 role mapping。
2. 选择 Mod/Community/Window，查看分维度 scorecard。
3. 导入 Mod Report，系统抽取 reported items。
4. 对照 observed findings，展示 reporting gap 类别。
5. 用户查看 Evidence/KB，做人工管理判断。

完成标准：无总分、无处罚建议、无动机推断；每个异常维度有分母与证据。

### Flow E：Contributor Review

1. 用户切换 High/Emerging。
2. 查看 why surfaced、趋势、guardrail 和代表聊天。
3. Confirm 或 Remove 产生 review record。
4. 后续窗口基于新证据重新计算，历史 review 不被覆盖。

### Flow F：Knowledge → Grounded Judgment

1. 用户导入官方 source 并填写 authority/validity。
2. 系统解析、chunk、index，显示可检索状态。
3. Agent 或 Mod groundedness 查询执行 hybrid retrieval。
4. 过期、冲突、无结果分别输出显式状态。
5. 用户从回答打开具体 chunk 和原 source metadata。

## 12. IA 验收口径

- 五个一级页面与全局 Ask Community 可从键盘访问。
- 任一 Brief/Signal/Topic/Behavior/Mod/Contributor/Agent claim 可进入统一 Evidence Drawer。
- `Original`、`Translation`、`AI Interpretation` 三者视觉和字段均分离。
- desktop utility dock 与 mobile full-screen 均保留 chat/filter 状态。
- 缺 KB、Mod、Mod Report、semantic 或 LLM 时，相关模块独立 unavailable，不阻塞 deterministic community analysis。
- 旧功能不删除，但不得占据新版 P0 主导航或改变 Hero Flow。

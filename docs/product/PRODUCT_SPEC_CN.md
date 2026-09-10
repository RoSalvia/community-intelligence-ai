# Community Intelligence AI 产品需求文档（PRD）

> **Legacy v0.1 reference（已被替代）：** 本文保留用于历史与资产追踪。当前唯一产品依据是 [`COMMUNITY_INTELLIGENCE_AI_PRD_V2_1.md`](COMMUNITY_INTELLIGENCE_AI_PRD_V2_1.md)，不得用本文覆盖 v2.1 方向。

> Legacy notice：本文件是 v0.1 历史产品文档，仅用于理解已有实现与迁移资产。当前唯一产品依据为 [`COMMUNITY_INTELLIGENCE_AI_PRD_V2_1.md`](COMMUNITY_INTELLIGENCE_AI_PRD_V2_1.md)，冲突时以 v2.1 为准。

> 本文同时记录长期产品方向与 V0.1 范围。当前可运行能力、验证证据和明确未实现项分别以仓库根目录 `README.md` 与 `docs/EVALUATION.md` 为准；愿景描述不代表相关 AI 方法已经实现。

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 产品名称 | Community Intelligence AI |
| 产品类型 | AI 原生多语言社区智能分析平台 |
| 当前阶段 | v0.1.0-alpha / Portfolio Project |
| 首期场景 | Telegram 多语言社区 |
| 长期场景 | Telegram、Discord、Reddit、游戏社区、AI 产品用户群、开发者社区、客服社区和社交媒体评论区 |

## 2. 产品背景

本项目来源于真实的 Web3 多语言社区运营经历。Product Owner 曾同时管理十多个不同语言的 Telegram 社区，需要协调 Moderator 维护秩序和聊天氛围、回答问题、引导项目讨论、执行 Campaign、翻译和本地化总部信息、进行内容创作，并推动用户参与和社区增长。

早期考核主要依赖 message count 和 activity volume。这种做法简单，却很快产生指标 gaming：大量短句、重复发言、无意义回复和高频刷屏都能制造“高活跃”，但消息数量好看并不代表宣传完整、用户理解准确、问题得到解决或讨论质量更高。换言之，`Message Count ≠ Community Quality`。

之后曾使用 Python 获取 Telegram 聊天数据，并通过 keyword hit rate 检查 Moderator 是否完成宣传任务。这比单纯消息计数更接近业务目标，但多语言翻译后可能完全不用原词，同一含义可以有多种表达，关键词出现也不代表日期、奖励、资格和截止时间准确。关键词方法还无法判断宣传之后用户是否回应、提问、参与或继续讨论。

因此，Moderator 考核只是最早暴露出来的表层需求。真正的问题是：面对大量、多语言、碎片化、非结构化的社区聊天，运营人员缺乏低成本方式去理解社区里真正发生了什么。

## 3. 核心问题与产品定位

产品不再定位为 Telegram Moderator 考核工具，而是回答：

> 如何利用 AI，从大量多语言非结构化社区对话中发现行为类型、社区响应模式和用户反馈，检查 Campaign 跨语言传播的一致性，从这些行为中提出值得关注的运营指标，再用统计分析验证哪些指标真正具有业务价值？

产品最终定位为 **AI-native Multilingual Community Intelligence Platform**。一句话描述是：

> Community Intelligence AI 利用多语言语义分析、行为发现、社区响应模式分析和数据验证，将海量非结构化社区聊天转化为可解释、可验证、可行动的社区洞察。

核心分析链路如下：

```text
非结构化多语言社区聊天
          ↓
行为发现
          ↓
社区响应模式
          ↓
多语言语义一致性
          ↓
Hygiene / Activation / Feedback 信号
          ↓
候选指标
          ↓
统计验证
          ↓
Community Intelligence
          ↓
运营 / 产品 / Campaign 决策
```

## 4. 产品目标

产品的核心目标是帮助社区运营负责人从“群里今天说了多少话”升级到“群里发生了什么、为什么发生、用户如何响应、哪些行为真正值得关注”。

V1 需要回答七组问题。第一，Moderator 和普通用户主要在做什么，哪些行为与项目相关，哪些只是闲聊、刷量或 spam，是否出现预设 taxonomy 之外的新行为。第二，Campaign 的核心信息是否在各语言区被完整、准确、一致地传达，哪里缺失、错误或发生语义漂移。第三，信息发布后是沉默、提问、回答、多人加入还是负面升级。第四，活跃来自 Moderator 还是来自真实用户，是否形成用户之间的持续互动。第五，用户最关心什么，为什么不满，有哪些反复出现的问题、建议和无人回答的问题。第六，消息量是否被 duplicate、filler、repetitive content、burst posting 或 spam 污染。第七，现有 KPI 是否有意义，哪些新信号可能形成候选指标，哪些指标真正得到数据支持。

## 5. 目标用户

第一优先级是 Community Lead、Global Community Manager、Community Operations、Ecosystem Operations、用户运营和社区增长负责人。他们无法逐条阅读十几个语言区，需要快速识别值得关注的社区、Campaign 和问题。

第二优先级是 Campaign 与 Marketing 负责人。他们需要知道总部内容是否在各语言社区被正确传播，以及用户对内容产生了什么反应。

第三优先级是产品团队。他们需要从对话中发现产品问题、真实疑问、功能需求和未满足需求。

第四优先级是 Moderator 管理者。他们需要基于 evidence 复核执行情况，而不是只看 message count。Moderator Evaluation 是平台能力的下游应用，不是产品中心。

## 6. 用户痛点

信息量过大和多语言是第一组痛点。十几个语言区持续产生聊天内容，运营人员既要找到重要信息、翻译，又要判断内容是否与项目相关以及是否正确，传统人工方式无法扩展。

传统活跃指标容易被 gaming。message count、active messages 和 daily activity 一旦成为 KPI，参与者就可能优化指标本身，而不是业务目标。关键词分析虽有进步，却无法理解语义：一句正确的本地化表达可能完全不含原关键词，而一条包含所有关键词的消息也可能写错关键截止日期。

普通 Dashboard 往往只能告诉用户消息数、用户数和谁最活跃，无法解释用户为什么开始讨论、为什么负面情绪上升、哪个 Campaign 引发了大量疑问，以及哪种行为真正激活了社区。许多运营 KPI 又来自经验判断，缺少稳定性、区分度和 outcome association 的验证。

## 7. 核心产品原则

第一，不从既有 KPI 出发，不预先设定 Coverage、Activity、Sentiment 的权重再强迫数据解释这套体系，而是从真实行为中发现信号。第二，AI 负责分类、聚类、发现模式和提出候选指标，数据与统计分析负责验证，人负责最终业务判断。第三，重要 AI 判断必须尽量可复核，用户能查看原始 claim、当地语言原文、必要的翻译、evidence、confidence 和 review status。第四，相关性不得解释为因果；例如 Peer Support Ratio 与 retention 正相关，只能表述为 associated with retention。

## 8. V1 产品范围与用户流程

V1 的核心输入首先是 Community Messages。当前 Public Alpha 支持由系统生成并明确标注的 synthetic multilingual dataset，以及 Telegram Desktop chat-history 导出的 `result.json`；标准 CSV 仍是后续兼容项。真实历史公司聊天不进入仓库，V1 暂不接入实时 Telegram API。

Campaign 和 Outcome 是可选能力模块，不是运行整个产品的前置条件。只有 messages 时，系统按 Community-only 模式运行现有的 Overview、Hygiene、Activation、回复图、Response Episode、Behavior、已实现的 Community Feedback seed 和不依赖 Campaign/Outcome 的候选指标；Campaign Intelligence 显示 `not_available: No campaign data provided`。提供 Campaign 与 Claims 后进入 Campaign-aware 模式；进一步提供 Outcome 后才启用 outcome association。没有 Outcome 时可以继续计算候选指标，但不得伪造 conversion、retention 或业务结果验证。

报告必须严格区分三种状态：`available` 表示当前输入允许运行且能力已实现；`not_available` 表示用户没有提供该能力所需的数据；`not_implemented` 表示产品本身尚未实现对应方法。缺少 Campaign 或 Outcome 不得导致整个报告失败、被标为 invalid，也不得通过虚构 Campaign、Claims 或业务结果补齐。

```text
导入 Telegram JSON 或选择 Synthetic Community Data
               ↓
运行分析
               ↓
查看 Community Intelligence Overview
               ↓
按可用数据查看 Campaign 跨语言执行
               ↓
查看行为与社区响应模式
               ↓
查看 Hygiene / Activation / Feedback
               ↓
查看 Candidate Metrics；有 Outcome 时查看统计关联验证
               ↓
点击 Evidence / 导出报告
```

## 9. 功能模块一：Behavior Discovery

Behavior Discovery 要从非结构化聊天中回答“人们到底在做什么”。Moderator 的种子行为可以包括 Campaign 宣传、产品解释、回答问题、主动引导讨论、CTA、新用户 onboarding、情绪安抚、翻译、纠正错误信息、普通闲聊、filler、重复宣传和 spam；用户种子行为可以包括项目讨论、Campaign 提问、产品问题、投诉、反馈、Feature Request、FUD、用户互助、CTA 响应、off-topic、分享外部信息和使用意向。

系统不能完全依赖预设 taxonomy。AI 需要能够从数据中提出新模式，例如把“机械翻译官方公告但没有进一步解释或激活讨论”识别为 `Translation-only Propagation`。Behavior Explorer 展示行为名称、说明、代表消息、出现频率、语言分布、Moderator/User 占比、AI confidence 和人工审核状态。审核状态至少包括 pending、accepted、renamed、merged 和 rejected。

## 10. 功能模块二：Campaign Intelligence

Campaign Intelligence 判断总部 Campaign 是否被各语言区正确、完整、一致地传播。第一步把长 Campaign Brief 拆成 atomic claims；第二步使用 multilingual semantic retrieval 在各语言区寻找与每个 claim 相关的消息，而不是只做关键词匹配；第三步把每个 claim 判断为 covered、partially covered、incorrect、contradicted、not covered 或 uncertain；第四步识别日期、奖励、资格、条件和含义在本地化中的 semantic drift。

每个判断保存 claim、community、status、confidence、evidence message、可选 translation 和 notes。界面按语言区展示 claims covered、缺失项、错误和 drift warning，所有 warning 均可点击查看 evidence。

## 11. 功能模块三：Community Response Pattern

产品必须进一步回答“信息发出去以后发生了什么”。分析单位从单条 message 提升为 conversation episode，即围绕 Campaign、Moderator 行为或用户问题，在时间、语义和回复图上相互连接的一组消息。

典型模式包括 `Announcement → Silence`，代表宣传完成但没有真实响应；`Announcement → User Question → Moderator Answer → New Users Join → User-to-user Discussion`，代表形成社区讨论；以及 `Announcement → Confusion → Repeated Questions → No Moderator Response → Negative Feedback`，代表传播或运营存在问题。

每个 episode 至少计算 unique participants、moderator/user messages、user-to-user replies、moderator responses、first response latency、conversation depth、branching、question count、resolved/unanswered questions 和 duration，并保留代表 episode 作为 evidence。

## 12. 功能模块四：Community Hygiene

Community Hygiene 回答活跃是真实互动还是人工制造。系统分析 duplicate、repetitive content、filler、burst posting、very short messages、spam 和 possible gaming，并给出 `duplicate_ratio`、`filler_ratio`、`repetitive_content_ratio`、`burst_events` 等定义清楚的信号。

这些结果只是 evidence，不自动处罚 Moderator。用户应能查看代表消息、规则或阈值以及潜在误报。系统不得为了让指标更好看而静默过滤不利样本。

## 13. 功能模块五：Community Activation

产品必须区分 Moderator Activity 与 Real User Activation。候选分析包括 unique engaged users、campaign discussion volume/share、meaningful interaction ratio、user-to-user interaction ratio、peer support ratio、conversation depth、conversation propagation depth、response latency 和 new user first engagement。

每项指标应定义分母、分析单位、时间窗和纳入规则。产品需要清楚区分“Moderator 发了 120 条消息但 coverage 低、filler 高、参与用户少”的社区，与“Moderator 只发 40 条消息但 coverage 高、用户问题得到及时回答且用户之间继续讨论”的社区，而不是把前者自动判断为更优秀。

## 14. 功能模块六：Community Feedback

Community Feedback 不能只输出 positive、neutral 和 negative，更重要的是解释为什么。系统提取 topic、sentiment、stance、concern、complaint、feature request、question、confusion 和 unanswered question，并以聚合方式展示主要原因及占比。运营人员可以从主题摘要下钻到形成该判断的原始 synthetic message。系统不得基于这些结果为个人建立敏感人格画像。

## 15. 功能模块七：Metric Discovery

Metric Discovery 是核心能力之一。产品不直接问 AI“社区运营应该考核什么 KPI”，而是使用以下流程：

```text
真实或 Synthetic 聊天
↓
发现行为与响应模式
↓
形成候选信号
↓
AI 提出 Candidate Metric
↓
转换成可计算公式
↓
历史或 Synthetic 数据计算
↓
统计验证
```

候选指标可以包括 Semantic Campaign Coverage、Meaningful Interaction Ratio、Conversation Propagation Depth、Peer Support Ratio、Unanswered Question Rate、Community Response Latency、User-to-User Interaction Ratio、Semantic Drift Rate、Campaign Discussion Share 和 Organic Project Mention Rate。每个候选指标必须包含名称、业务意义、精确公式、所需数据、分析单位、时间窗、可能价值、潜在偏差和局限。

## 16. Statistical Validation

AI 提出的候选指标不能直接成为正式 KPI。系统需要检查指标在不同语言区、Campaign、时间和社区中的稳定性，是否能区分高质量互动、刷量、沉默和高参与社区，是否与其他指标高度冗余，以及在存在 participation、conversion、retention、referral 或 user growth 时是否表现出 outcome association。

统计层必须执行真实计算并报告样本量、分布、缺失、效应大小或相关程度及适用的不确定性，不能只让 LLM 输出一段“这个指标很有价值”的文字。Metric Lab 中的状态为 Candidate、Promising、Validated 或 Rejected。Synthetic data 只能证明流程和已知情景是否可识别，不能证明指标在真实世界已经外部验证。

## 17. Moderator Evaluation

Moderator Evaluation 是 Community Intelligence 的下游应用。V1 不输出 `Moderator Score = 85`，也不设置 Coverage 30%、Activity 20%、Sentiment 20% 等未经证据支持的权重。

如需展示管理视角，应使用 evidence-based scorecard，把 Campaign Execution、Responsiveness、Community Activation、Content Quality、Anti-gaming 和 Unresolved Community Feedback 分开呈现。最终判断仍由人完成，系统不得自动处罚或做 HR 绩效决策。

## 18. Dashboard 信息架构

**Overview** 展示社区与语言区、消息和活跃用户概况、当前 Campaign、主要 alerts，并明确数据是 synthetic。**Campaign Intelligence** 展示 claims、各语言区 coverage、semantic drift、community response、主要 concerns、unanswered questions 和 evidence。**Community Intelligence** 展示行为组成、Moderator/User 活动、用户间互动、Campaign 讨论、Hygiene、Activation 和 Feedback themes。

**Behavior Explorer** 用于查看 AI 发现和人工审核的行为模式；**Response Pattern Explorer** 用于查看典型 conversation episode；**Metric Lab** 展示候选指标的定义、公式、分布、stability、redundancy、outcome association 和状态；**Evidence Review** 让所有重要判断回到对应 source message。Dashboard 的价值在于让分析可行动和可复核，而不是只展示漂亮图表。

## 19. 核心数据字段

Message 最少包含 `message_id`、`community_id`、`language`、`user_id_hash`、`user_role`、`timestamp`、`text`、`reply_to_message_id` 和 `campaign_id`。用户角色为 moderator、user 或 bot。

Campaign 包含 `campaign_id`、`campaign_name`、`start_time`、`end_time` 和 `campaign_brief`；抽取后的 claim 包含 `claim_id`、`campaign_id`、`claim_text` 和 `importance`。可选 Outcome 包含 `campaign_id`、`community_id`、`participants`、`conversion`、`new_users`、`retention` 和 `referrals`。Outcome 不自动归因给 Moderator，只用于上下文和指标验证。

## 20. MVP Demo 数据设计

V1 不使用真实历史公司或用户数据。系统生成至少四个 Community、四至五种语言、三个 Campaign 和 1,000 条以上消息，并提供生成规则、随机种子和 synthetic manifest。

Community A 的 Moderator 发言很多，但 filler 和 duplicate 高、Campaign Coverage 低、用户参与低，用于证明 Message Count 不等于社区质量。Community B 的 Moderator 消息较少，但 Coverage 高、问题得到及时回复、用户之间继续讨论。Community C 包含多语言本地化中的 Semantic Drift，例如奖励金额、截止日期或资格条件错误。Community D 有大量用户提问，但 Moderator 回应不足，unanswered questions 高且负面反馈增加。

Synthetic outcomes 只能用于测试 Metric Lab 是否能恢复预先记录的数据生成关系，不得被表述为真实社区研究结论。

## 21. 产品成功标准

V1 成功不是做出漂亮 Dashboard，而是同时证明以下能力：

1. **Behavior Discovery：** 能从非结构化、多语言聊天中发现有意义的行为类型，并保留代表 evidence 和审核状态。
2. **Community Response Pattern：** 能识别一个行为之后社区出现的典型对话链和关键 episode 指标。
3. **Multilingual Campaign Intelligence：** 能判断 Campaign 是否被正确、完整、一致地传播，并识别关键事实错误和 semantic drift。
4. **Metric Discovery：** 能从行为和响应模式中生成定义明确、可计算的 Candidate Metrics。
5. **Statistical Validation：** 能通过真实计算决定哪些候选指标值得保留、仍待观察或应被拒绝。
6. **Evidence：** 重要 AI 判断能回到 source message、claim、translation、confidence 和 review status。
7. **Reproducibility：** 新用户无需私人数据即可按 README 运行完整 demo、测试和 evaluation。

任何未实现能力必须标注 `Not implemented`，不能用 mock、placeholder、静态截图或文字描述冒充完成。

## 22. V1 非目标

V1 暂不解决实时 Telegram 监控、自动处罚 Moderator、自动 HR 绩效评估、复杂权限、SaaS 收费、Discord/Reddit 接入、大规模企业部署、因果分析和全自动业务决策。也不优先建设 Telegram Bot、Telethon realtime listener、Kafka、Kubernetes 或复杂云微服务。

## 23. V2 Roadmap

数据接入可以扩展到 Telegram API、Discord、Reddit、X Community 和 Customer Support；自动化可以扩展到 Weekly Community Intelligence Report、real-time alert、Campaign monitoring 和 automatic escalation；高级分析可以加入历史趋势、retention cohort、cross-community benchmark、Campaign A/B comparison 和 conversion attribution research；产品协作可以生成 Product Insight、Community Weekly Report、Campaign Review、User Concern Report 和 Product Team Escalation。

这些方向只有在 V1 的产品逻辑、评估和使用价值获得证据后才进入实施。

## 24. 产品长期价值

项目虽然起源于 Web3 Telegram Moderator 管理，但底层问题普遍存在于 AI 产品用户群、游戏社区、电商用户群、Developer Community、Discord、Reddit、客服、用户评论和社交媒体讨论：大量自然语言行为无法通过简单计数指标理解。

Community Intelligence AI 的长期价值是把社区中的非结构化自然语言行为转化为可解释的运营信号，并通过数据验证帮助团队判断哪些信号真正值得关注。

## 25. 最核心的产品故事

项目必须保留完整的问题演进：业务最初希望通过 Message Count 考核 Moderator；发现 KPI 被 gaming 后，尝试 Keyword Hit Rate；随后发现关键词无法处理多语言、语义变化、Campaign 完整性和用户响应；问题因此重新定义为“如何理解整个社区发生了什么”；AI 被用于从非结构化聊天中发现行为和响应模式；进一步又发现运营指标本身不能完全由经验决定，于是形成 `AI 发现候选行为和指标 + 统计分析验证 + 人做最终业务判断` 的方法。

最终项目从 Moderator KPI Script 演进为 Community Intelligence AI。这条问题发现与产品迭代路径，是项目最重要的产品价值之一，也应成为后续 README、Demo 和求职 Portfolio 的叙事主线。

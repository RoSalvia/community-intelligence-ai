# Product Owner 决策清单

状态：2026-09-10 已决策，M0 blocker 已关闭

规则：只把会改变产品承诺、隐私边界或真实验收方式的问题列为 blocker；普通技术选择已在 Technical Design 中收敛。

## A. 已关闭的 blocker

### B1. MVP 的真实 LLM 运行边界

**需要决定：** 最终 MVP/Demo 是允许用户显式配置 remote LLM，还是必须完全离线运行 Topic naming、Behavior adjudication、Brief、Agent 与 Mod Report extraction？

**决策：** 接受 Hybrid 模式。`local deterministic + local embedding` 默认可用；用户显式配置 remote LLM 后启用完整 Copilot。远程只发送完成任务所需的最小 Evidence/Knowledge snippets，不默认上传完整 community corpus。具体 provider 保持抽象，不在产品层绑定厂商。Portfolio Demo 不包含 key，也不以预生成答案冒充实时能力。

**为什么是真 blocker：** provider 选择会改变模型 contract、隐私文案、成本/延迟 gate、Topic/Behavior 质量方案和完整 Hero Demo 的可复现方式。Provider interface、deterministic pipeline 与 UI fallback 可以先开发，但 D3.4、D3.5、D4.5、D5、D7.2 的真实 provider 验收不能冻结。

**执行影响：** provider interface、capability probe、最小上下文策略和 remote opt-in 成为验收项；具体 provider 可在实现层配置。

### B2. 真实世界 evaluation / human productivity pilot 的数据与授权

**需要决定：** M9 是否只交付 synthetic + curated benchmark，还是在 MVP Definition of Done 中必须完成真实 Telegram 数据与真实 reviewer 的 Human Review Time、Issue Detection Lead Time、Human Agreement 测试？

**决策：** 采用 `benchmark-complete, real-world validation pending`。MVP 以 synthetic/curated benchmark、AI evaluation 和真实业务验证 protocol 为完成条件，不等待真实 Telegram 管理员数据。“saves time / detects earlier”等真实效果声明必须等合法数据和 reviewer 实测后才能使用。

**为什么是真 blocker：** 代码开发不受阻，但最终可宣称的产品完成度、Portfolio 文案和 release gate 不同。项目不能自行寻找或导入私有群聊，也不能把 synthetic 结果说成真实业务验证。

**执行影响：** D9.5 交付预注册 protocol，不填写 synthetic 推导的业务收益；Portfolio Demo 明确 validation pending。

## B. 已做出的非阻塞产品/技术选择

| PRD open question | 本设计选择 | 理由 |
|---|---|---|
| Ask Community 位置 | desktop persistent right Utility Dock；mobile full-screen | 符合 Copilot 主入口，保留当前页面 scope |
| Evidence 与 Ask 是否共区 | 共用 dock，Evidence 作为 detail stack，Back 恢复 chat | 避免双抽屉冲突且不丢会话 |
| Knowledge 格式 | P0 `.md`、`.txt`、文本型 `.pdf`；无 OCR | 覆盖 Web3 常见资料，边界可测试 |
| validity period | 允许手工设置并保存 revision | PRD 冲突/时效判断必须依赖它 |
| Brief 形态 | 短段落 + structured cards | 概览效率与可追溯性兼顾 |
| Risk severity | High/Medium/Low + evidence/confidence 独立 | 易读；不把 severity 当模型概率 |
| Topic correction | P0 rename；merge 在 identity 稳定后加入 | Hero 纠错可成立，降低 early data migration 风险 |
| 首批 correction | Signal reclassify/dismiss、Behavior relabel、Topic rename、Role assignment、Contributor confirm/remove | 覆盖 Hero 与主要人工复核；均可结构化 |
| Mod Report history | 保留本地历史与 raw immutable revision | Reported vs Observed 和审计需要 |
| authority policy | workspace 可配置、policy versioned；提供 PRD 默认序 | 项目规则不同，且需重现旧判断 |
| Translation | original-first，按需生成并明确 provider/version | 降低默认外发与误译风险 |
| Suggested Action | 小型 action taxonomy + optional note | 可评测、可过滤且不扩展到自动执行 |
| Agent history | 持久保存 Investigation、steps、citations、corrections；不做跨线程“个人记忆” | 审计需要，避免隐式 profiling |
| KB 更新后的旧 Finding | 标 stale + 用户触发/下一分析重算；P0 不全库自动重查 | 避免不可控成本与静默结论变化 |
| since-last-check | 用户成功查看 Home 后显式推进 watermark | 语义稳定，不因后台分析自动错过事件 |
| Signal thresholds | config/version + evaluation 冻结，不在 PRD 中拍脑袋写死 | 保持可迭代和可复现 |
| Topic clustering | noise-aware + stability gate；TF-IDF/KMeans 只作 baseline | 支持 Uncertain，不强制每条消息归类 |
| 数据库/部署 | local FastAPI + SQLite modular monolith | 满足规模与审计，不引入无收益基础设施 |

## C. 评审时建议只回答的三件事

1. B1 是否接受推荐的 hybrid provider 模式？
2. B2 的 MVP 声明边界选 benchmark-complete 还是必须包含真实 pilot？
3. 对 low-fi IA、Technical Design、Development Tasks 是否有会改变主路径的异议？若无，M0 视为批准并进入 D0.3/D0.4。

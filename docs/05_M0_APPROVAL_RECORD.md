# M0 Product Review Record

日期：2026-09-10

状态：Approved / Frozen

## 批准范围

- PRD v2.1 作为唯一产品依据。
- Existing / Reusable / Needs Refactor / New / Deprecated-but-keep 能力矩阵。
- 五入口 low-fi IA、全局 Ask Community、统一 Conversation/Evidence Drawer。
- Technical Design、API/data contract 方向与 Milestone 依赖。
- 首个 vertical slice 固定为 `CN Telegram data → Wallet Issue Signal → Home Need Attention → Investigate → Agent analysis → Project Knowledge（如需要）→ Original Conversation Evidence`。

## 已关闭决策

1. Hybrid AI：deterministic analysis 与 multilingual embedding 默认本地；remote LLM 仅在用户显式配置后启用，只发送完成任务所需的最小 Evidence/Knowledge snippets，provider 保持抽象。
2. Validation：MVP 以 benchmark-complete、real-world validation pending 交付；synthetic/curated benchmark 与真实验证 protocol 可进入 Portfolio Demo，真实业务效果声明必须等待后续合法实测。

## 执行门槛

- 后续只在当前 active workspace 开发，保留 v0.1 Git history 与 legacy assets。
- 优先完成首个 vertical slice，不横向铺开全部模块。
- 每个 Milestone 完成后暂停进入下一阶段，提交 user-visible actions、实际界面/flow、尚未实现能力与风险、测试/evaluation 结果供 Product Review。
- 普通实现细节不升级为 PO 问题；只有影响产品行为、隐私、AI 质量或 scope 时才提出。

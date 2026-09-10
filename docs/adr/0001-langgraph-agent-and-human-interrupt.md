# ADR-0001: LangGraph 仅作为 Agent 与 Human Interrupt 编排层

- 状态：Accepted
- 日期：2026-09-10
- 生效阶段：M5 / M6

## Context

Investigation Agent 需要最多 5 步的动态 tool calling、可恢复状态与失败降级；Human Correction 需要在 proposal 后暂停，等待用户确认，再继续执行。与此同时，Community Intelligence 的 Topic、Behavior、Signal、RAG、Evidence、Correction 与 evaluation 必须能脱离具体 Agent framework 测试和演进。

## Decision

M1–M4 不引入 LangGraph，也不改变既定顺序。M5 在 bounded agent loop 首次需要时引入 LangGraph，仅负责：

- workflow state 与 checkpoint；
- tool routing；
- `max_steps=5`、timeout 与失败状态；
- interrupt / resume。

M6 使用 LangGraph 编排：

```text
correction proposal
  → interrupt
  → explicit human confirmation
  → resume
  → domain correction service
```

真正的 target/version validation、correction apply、append-only audit、read-model stale 标记和 recompute 由 framework-agnostic domain service 与数据库事务完成。Topic、Behavior、Signal、RAG、Evidence、tool schemas、Mod/Contributor 和 evaluation 不导入 LangGraph 类型。

## Consequences

- LangGraph checkpoint 不是业务事实源，也不能代表用户批准。
- workflow runtime 可替换；替换后 domain contracts 与 evaluation fixtures 不变。
- M5 之前不增加 LangGraph dependency、adapter hierarchy 或占位实现。
- Agent/Copilot 不可用时，deterministic analysis、Home cards、Evidence 与 correction domain API 仍可独立运行。

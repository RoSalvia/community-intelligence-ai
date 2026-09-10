# M1 Data Foundation — Product Review

日期：2026-09-10

状态：Approved / Frozen after usability review

## Post-freeze Product Review Harness（不改变 M1 scope）

- 显式使用 `community-intelligence serve --m1-review` 后开放 `/internal/m1-review`；默认启动时该 route 为 404。
- 单页仅串联现有 `/api/v1/*`：Workspace → EN/CN/ES Community → Telegram JSON Upload → Actor `operator_label` → Mark Moderator → Freshness → Analysis Window → Run/Poll。
- 安全合成数据位于 `examples/m1-review-cn-telegram.json`。Harness 不增加业务逻辑，也不包含 Home、Topic、Signal、RAG 或 Agent。

## Freeze Review 已解决项

1. Actor identity：API/schema 返回 local-only `display_name`、`platform_handle`、稳定 pseudonym 与 `operator_label`；`user_id_hash` 继续作为内部 ID，Telegram 原始 sender ID 不持久化。
2. Privacy/export：ActorIdentity 不进入 AnalysisRun dataset、demo/benchmark export 或默认 remote-provider allowlist；本地 SQLite 默认位于仓库外，仓库同时忽略 SQLite artifacts。
3. Cross-batch reply：`reply_to_message_id` 不绑定 SyncBatch；稳定 `reply_to_source_key` 支持 parent 已存在或后补录，两个方向均有回归测试。
4. Agent framework：ADR-0001 只对 M5/M6 生效，不重新打开 M0，也不改变 M1–M4 顺序。

## 本阶段新增能力

- 可创建、读取、改名 Workspace，并配置 EN/CN/ES 三个 Telegram Community。
- 可把中文 Telegram Desktop JSON 作为 batch 导入；原始发送者不落库，workspace salt 参与匿名化；重复文件不会重复写入。
- 可通过 local-only `display_name` / `platform_handle` 或稳定 pseudonym 识别已导入用户并指定 Mod；内部仍使用 `user_id_hash`，保留生效时间与版本，不改写历史消息。
- Reply 使用稳定 message key，可解析跨 SyncBatch parent；父消息先到或后补录均已覆盖。
- 可读取每个 Community 的 freshness，使用 `since-last-check`、24h、7d、30d 或 custom `[start,end)` window，并得到等长 baseline window。
- 可创建并轮询持久 AnalysisRun；无新增消息返回 `no_new_activity`，相同成功输入复用结果，中断任务在重启后标为 failed。
- AnalysisRun 当前只调用保留的 v0.1 deterministic pipeline；未冒充 Topic、Signal、Brief 或 Copilot。

## 实际 Flow

当前可通过 internal M1 Review Harness 完成该 Flow；`/api/docs` 仍可用于接口检查：

```text
Create Workspace
  → Configure EN / CN / ES Communities
  → Upload CN Telegram result.json
  → Select actor by display name / handle / pseudonym as Mod
  → Inspect freshness + analysis window
  → Create AnalysisRun (202)
  → Poll run status / reuse successful run
```

现有网页仍是保留的 v0.1 dashboard。本阶段没有增加临时设置页，因为它会在 Hero Flow 的 Home IA 接入时被替换；因此 M1 数据能力已可集成，但尚不是最终用户界面。

## PRD Acceptance 对照

| PRD M1 | 结果 |
|---|---|
| Workspace | 已实现持久 create/read/update |
| Communities | 已实现 EN/CN/ES + Telegram + timezone contract |
| Mod config | 已实现 human-readable local identity + stable hash、effective dates、versioned manual assignment |
| SyncBatch | 已实现 content hash 幂等、事务写入、无 partial message state |
| freshness | 已实现 per-community latest message/import 与 current/stale/no-data |
| period comparison | 已实现 current window + 等长 baseline + explicit watermark |

## 验证

- 新增 focused/backend integration tests：13 passed。
- 全量 Python regression：345 passed，2 skipped。
- Frontend：3 tests passed；typecheck、lint、production build passed。
- `ruff`、dependency lock、Git whitespace checks passed。

## 尚未完成或降级

- 尚无正式 v2.1 产品 UI；当前单页只用于 internal Product Review，不进入产品导航。
- 尚未实现 Wallet Issue Topic/Signal、Home Need Attention、Investigate、Knowledge/RAG、Agent 与 Conversation Evidence；这些属于后续 Hero vertical slice。
- M1 AnalysisRun 输出仍是 legacy deterministic report，只作为迁移桥梁。
- schema 尚未发布，当前只维护 fresh-create + version mismatch refusal；首次真实 schema 变更时再引入 forward migration，不保留无使用者的 down-migration abstraction。

## Ponytail 收敛记录

- 未保留不需要的 Alembic，并删除 5 个未使用前端 runtime dependencies；保留 FastAPI 测试实际需要的 `httpx2`。
- 没有新增 repository hierarchy、provider framework、通用任务队列或 event bus。
- 新数据服务按 v1 endpoint 首次使用时才初始化，v0.1 分析路径及其文件布局保持不变。

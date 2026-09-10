# Blum Official Blog Historical Knowledge Acquisition — Review Gate

状态：**HISTORICAL BLOG ACQUISITION COMPLETE / FROZEN M2 IMPORT BLOCKED**

Pack：`blum-historical-blog-pack-v1`

基线：`3858dbf4236a8b148997dede40b609f057d3b23e`

## 决策摘要

当前官方 Blog catalog 共 77 篇：3 篇 current-live，74 篇由当前官方 catalog 直接链接到
Wayback。10 篇 CN Chat 时间窗口内的 controlled set 全部通过，随后 74 篇 archive raw
snapshot 全部获取并解析成功。normalized content 未发现 Wayback toolbar/chrome 污染，
provenance chain 74/74 完整。

这使 Blum Historical Blog corpus 从 3 篇增加到 77 篇 catalog sources，但尚不能进入 Frozen
M2：77 篇均只有 date-only publication metadata，且没有 confirmed `effective_from`。本轮没有
伪造时间、修改 M2 contract 或运行 RAG smoke。

## 1–4. Catalog 与 2024 范围

| 指标 | 结果 |
|---|---:|
| official Blog catalog articles | 77 |
| current-live | 3 |
| official-index-linked archive | 74 |
| publication date coverage | 77/77 |
| 2024 articles | 18 |
| 与 CN Chat `2024-03-19..2024-08-18` 重叠 | 10 |

Catalog raw hash：`380d82dd137b17c5527a76115dbff61d31249900280c1c082667ca9e08928892`。
publication date 均来自当前官方 Blog card，保持 date-only。

## 5–8. Controlled 与批量 acquisition

Controlled set 选择时间窗口内实际存在的 10 篇，覆盖 Trends、Company News、New Features、
Campaigns。结果为 `10/10 passed`，连续重跑时 catalog hash、最终 snapshot URL、raw hash 与
content hash 均为 `10/10 stable`。

Wayback 标准 replay 会动态注入 toolbar 元数据，导致 raw hash 变化。最终 acquisition 保留
catalog 原始 Read Article URL，同时使用同一 snapshot 的公开 `id_` raw-capture 表示保存原始
响应。该表示不含 toolbar，controlled 重跑 raw hash 稳定。

批量结果：

| 指标 | 结果 |
|---|---:|
| selected archive targets | 74 |
| successfully acquired | 74 |
| final failed snapshots | 0 |
| parser failures | 0 |
| provenance incomplete | 0 |
| chrome contamination | 0 |
| content-hash duplicates | 0 |
| raw-hash duplicates | 0 |
| normalized content length | 822–45,064 chars |

中间重跑曾有 1 次 `ReadTimeout`；最终 runner 使用受节流约束的单次瞬时重试后，该目标正常
获取。没有将超时误判为页面缺失，也没有无限重试。

## 9. Provenance chain

74/74 source 都保留：

`current official Blog article card`
→ `catalog Read Article URL`
→ `official-index-linked Wayback raw capture`
→ `original blum.io/post/<slug>`

acquisition/manifest 使用：

- `content_origin = historical_archive_snapshot`
- `official_identity_basis = current_official_blog_index_link`
- `source_type = official_blog`
- `source_channel = website`

普通自行搜索得到、但当前 catalog 没有链接关系的 archive 导入数为 0。

## 10. 时间字段

三个时间层完全分离：

- `official_catalog_publication_date`：当前官方 catalog 显示的 date-only 日期；
- `archive_snapshot_at`：最终 Wayback capture URL 中的精确 UTC 时间；
- `acquisition_observed_at`：本轮获取时间。

`snapshot_at` 被用作 `published_at` 的数量为 0；`observed_at` 被用作 `effective_from` 的数量
为 0。74 个实际 capture 分布于 2025-11-15 至 2026-06-06，不能据此声称网页正文从 2024
发布后从未更新。

## 11. Blum CN 2024 Knowledge Coverage

CN Chat 时间窗口内有 10 个官方 catalog 日期与事件：

| 日期 | 事件 |
|---|---|
| 2024-03-29 | Crypto with Blum / 产品定位 |
| 2024-04-09 | Blum app、愿景与核心功能介绍 |
| 2024-04-19 | Telegram Mini App 上线与 Blum Points |
| 2024-04-26 | Blum ecosystem FAQ |
| 2024-05-01 | Developer recruitment / 团队扩张 |
| 2024-05-03 | 2024 Roadmap、Tribes、Memepad 等规划 |
| 2024-05-18 | Drop Game 上线 |
| 2024-06-11 | Quests 上线与 $10,000 USDT campaign |
| 2024-07-05 | Pokras Lampas 活动与 Quest rules |
| 2024-07-22 | Tribes 社区功能与奖励机制 |

评估：**事件与主题覆盖显著改善，但仍不足以做严格、完整的 2024 `as_of_time` 裁决。**
原因包括：窗口内只有 10 个离散 publication dates；缺少 Help 历史版本和官方 Telegram
announcement；archive capture 来自 2025–2026；页面没有 revision/updated/effective validity
证据。

## 12. Help Center

维持：`unavailable / site-side access failure`。

- 候选：72；获取：0。
- 已观测 Cloudflare Error 1000：`DNS points to prohibited IP`。
- 暂停重试，不绕过 Cloudflare，不使用搜索摘要正文，不把 0 acquired 解释为 0 knowledge。

## 13–14. Frozen M2 compatibility

| corpus | sources | honest import | metadata blocked |
|---|---:|---:|---:|
| official-index-linked historical Blog | 74 | 0 | 74 |
| current-live Blog | 3 | 0 | 3 |
| combined | 77 | 0 | 77 |

每篇均存在两个独立 blocker：

1. official publication metadata 只有 date，而 Frozen M2 要求 precise datetime；
2. 没有 confirmed `effective_from` / validity provenance。

本轮没有进入可运行的 Frozen M2 corpus，因此没有发现或评估 genuine retrieval/answering
issue。当前问题仍属于 metadata contract compatibility，而不是已证实的 retrieval defect。

## Language、category 与解析异常

正文语言审计后为 `en=74`。原始 HTML 为 `en=66, ru=8`；8 篇 `html lang=ru` 页面正文实际为
英文，已保留 declared language 并记录 `language_mismatch=true`，实际 language 使用确定性的
script audit 标记为 `en`。

Category：Campaigns 19、Company News 22、Education 12、New Features 12、Product 5、
Partnerships 2、Trends 1、unknown 1。unknown 是 catalog 自身 category 为空的
“Blum Trading Bot - Terms of Use”，没有按标题猜分类。

## 15. 下一阶段建议

建议下一步进入独立的 `Blum Official Telegram Announcement Acquisition`，但本轮只提交实施
方案，不执行。其价值是为 2024-03～08 提供精确 message timestamp、连续事件时间线以及
Blog 未覆盖的公告/规则变更证据。EN/CN/ES official channel 必须先验证官方身份，并继续与
Community Chat 严格分离。

## Artifacts 与边界

- Aggregate manifest：`historical-blog-aggregate.json`
- Schema：`docs/schemas/blum-historical-blog-pack-v1.schema.json`
- Telegram Phase 2 plan：
  `docs/superpowers/plans/2026-09-11-blum-official-telegram-announcement-acquisition.md`
- Full catalog inventory、raw snapshots、normalized full text：ignored local
  `data/private/blum-knowledge-pack-v1-2026-09-11/historical-blog/`

Git 不含 Blum 正文、raw Wayback HTML、full catalog inventory、cache 或 validation DB。本 Track
不 merge、不 push，不修改 Frozen M2、M3 或 M4，完成后停在 review gate。

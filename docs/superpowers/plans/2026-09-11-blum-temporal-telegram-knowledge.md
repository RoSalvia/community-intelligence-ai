# Blum Temporal Precision + Official Telegram Knowledge

状态：**LOCALLY EXECUTED / REVIEW GATE**

## Goal

在不改变 Frozen M2 的 chunking、hybrid retrieval、reranker、authority ranking 与 answer
logic 参数的前提下，增加真实精度的 publication metadata，并把已完成的 Blum 官方 Telegram
announcement channel 作为一等 Project Knowledge 导入同一 Blum Knowledge Base。

## Decisions and boundaries

- Blog 仅保存 `published_on` 与 `temporal_precision=day`；`published_at` 保持 null，禁止补
  midnight。
- Telegram `date_unixtime` 保存为精确 UTC `published_at` 与
  `temporal_precision=second`。
- `effective_from` / `effective_until` 条件性可空；announcement time 不默认等于
  `effective_from`。
- 现有 schema 迁移必须向后兼容；旧 precise-datetime source 自动解释为 second precision。
- 一条 Telegram message 是一个独立 Knowledge source；继续复用 Frozen M2 structure-aware
  chunking，不拼接无关 messages。
- raw export、完整 snapshot、正文、media 与 private validation DB 仅进入 ignored
  `data/private/`；Git 只保留代码、schema、aggregate、hash、最小 fixture 与报告。
- Help Center 保持 site-side unavailable，不绕过 Cloudflare；不 merge main，不 push。

## Implementation sequence

1. 用 focused failing tests 固化 day/second precision、nullable validity、same-day ambiguity、
   citation trace 与 v2→v3 migration。
2. 实现最小 schema/application/API 兼容迁移，保持既有 Frozen M2 constants 不变。
3. 用 focused failing tests 固化 live-export complete-object fingerprint、stable freeze、官方
   announcement normalization、message-boundary ingestion 与 aggregate manifest。
4. 对 `Blum: All Crypto – One App` 做至少三次稳定检查；只有目标 byte range/hash 稳定且
   live file 同期继续增长时，才发布 immutable private snapshot。记录身份链、range/hash、
   snapshot hash 与 extraction method/time。
5. 将 3 current-live + 74 official-index-linked historical Blog 和所有合格 text-bearing
   ordinary announcements 导入一个 private Blum validation DB；保留独立 source/revision/chunk
   provenance。
6. 构建 2024-03～09 official timeline 与十个 Hero events 的 Blog/Telegram evidence matrix；
   只记录时间证据、冲突与不确定性，不推断社区行为因果。
7. 运行 Blum-specific retrieval/citation/as-of smoke；不据此调参。随后运行 focused tests、
   full regression、Ruff、schema validation、private-data/Git boundary 和 frozen constants 检查。
8. 更新 aggregate/report，提交当前 branch，停在 review gate；不 merge、不 push。

## Completion criteria

- 77/77 Blog 可用 day precision 诚实导入，且 DB/API/citation 中无虚构 midnight。
- Telegram 报告 ordinary/text-bearing/precise timestamp counts，并能从 Blog 与 Telegram 同时
  召回独立 citation。
- 同日精确 `as_of_time` 不把 Blog 宣称为已知精确发布时刻，trace 明示 ambiguity。
- Frozen M2 regression 全部通过，所有冻结版本常量保持不变。

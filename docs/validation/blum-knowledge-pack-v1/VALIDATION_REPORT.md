# Blum Knowledge Acquisition / Hero Workspace Knowledge Pack — Coverage Review

状态：**ACQUISITION COVERAGE BLOCKED / FINAL M2 SMOKE NOT STARTED**

采集版本：`blum-knowledge-pack-v1`

Frozen M2 baseline：`3858dbf4236a8b148997dede40b609f057d3b23e`

采集观测时间：`2026-09-10T17:43:10.040315Z`

## 决策

当前 3-source 结果不能视为 Blum Knowledge Pack coverage 完成，也不能据此进入最终
Frozen M2 smoke validation。Blog 的 77 个官方 `/post/` 候选只恢复 3 个；2024 年的 18 篇
全部未恢复。Help Center 发现了 72 个疑似知识页，但所有官方 URL 在当前 acquisition
环境中均返回 HTTP 403，普通可见浏览器也得到同一 Cloudflare 错误页。

Wayback 仅用于发现 underlying 官方 URL。采集器会提取
`https://blum.io/post/<slug>` 并优先重试官方 URL；74 个官方 URL 返回 404 后记录为
`official_source_unavailable_archive_fallback_candidate`。归档正文导入数为 0。

## 1–2. 官方页面发现与获取

| 来源 | 官方知识候选 | 官方源成功获取 | 暂时不可获取 | 结论 |
|---|---:|---:|---:|---|
| `help.blum.io` | 72 | 0 | 72（HTTP 403） | acquisition method blocker，不代表 Help 无知识 |
| `blum.io/blog` | 77 | 3 | 74（官方 `/post/` 为 HTTP 404） | coverage 严重不完整 |

Blog index 本身列出 77 张文章卡片和 77 个发布日期，其中 18 篇属于 2024 年。74 个
Wayback 包装链接全部恢复为 underlying 官方 `/post/` 后重新请求；只有原本就仍在同域的
3 篇 2025 文章成功，74 个 hint 对应的官方页面均未恢复。

Help 的 72 个候选来自历史 URL inventory，只作为 discovery hint。原始 91 条官方 URL中，
19 条 root、feed、`.well-known`、资源文件或截断 URL 被排除。剩余路径分布为 EN 32、RU 20、
TR 20；对 72 个 URL 的正文请求全部只发往 `help.blum.io`，均返回 403。公开搜索索引仍能
发现 Blum General FAQ、Trading Bot、Perps、Troubleshooting、Memepad 等官方页面，说明
“当前 crawler 取不到”不能解释为“Help Center 不存在”。搜索摘要没有进入 Knowledge Pack。

## 3. Source type、语言与时间元数据

成功获取的 3 篇来源分布如下：

| 字段 | 分布 |
|---|---|
| `source_type` | `product_docs=3` |
| `source_channel` | `website=3` |
| language | `en=3` |
| `published_at` | 3/3，均为 date-only：2025-06-13、2025-07-25、2025-07-28 |
| `updated_at` | 0/3 |
| `effective_from` | 0/3 |
| author | 0/3 |
| content-hash duplicate | 0 |
| 成功获取但无法分类 | 0 |

Help 候选尚未获得官方正文，因此不能把路径语言或搜索摘要推断成可导入 source metadata。
日期没有补成午夜，采集时间没有冒充 `published_at`，未知有效期保持为空。

## 4. Historical/time audit

结论：**当前 coverage 不足以支撑 2024 Blum community chat。**

- Blog 中有 18 篇明确标注为 2024 年；官方 URL 恢复 0/18，全部返回 404。
- 3 篇可获取正文均发表于 2025 年，没有 `updated_at`、revision、replacement 或
  supersession 证据。
- Help 当前正文获取 0 页，无法证明任何页面在 2024 年已经生效，也无法审计旧 FAQ。

因此当前来源不能用于对 2024 community chat 作无条件 `as_of_time` 判断。

## 5. 真正不需要与暂时拿不到

真正不进入 Knowledge Pack：8 个导航/营销页、2 个 Terms/Privacy 页面、7 个普通外域链接、
15 个 metadata/feed、1 个静态资源、2 个截断 URL。Terms/Privacy 不是当前 blocker。

暂时拿不到：74 个由 Wayback hint 恢复出的官方 Blog URL，以及 72 个 Help 知识候选。
这些不能按 `external_origin` 或“无知识”丢弃，应继续保留为 acquisition backlog。

## 6. Knowledge Pack manifest

- Version：`blum-knowledge-pack-v1`
- Schema：`docs/schemas/blum-knowledge-pack-manifest-v1.schema.json`
- Tracked aggregate：`docs/validation/blum-knowledge-pack-v1/manifest.json`
- Full inventory、raw snapshot、normalized content：ignored local
  `data/private/blum-knowledge-pack-v1-2026-09-11/`

Aggregate manifest 记录 259 个 canonical discovery records：3 included、147 failed、109
excluded；其中 74 条 archive hint 与对应 74 条官方重试分别保留，避免把线索和权威来源混为
一条。tracked 文件不含网页全文。

## 7. Frozen M2 import compatibility

当前只做了 provisional contract probe，不是覆盖完成后的正式导入。3 篇正文均缺少 Frozen
M2 所需的 precise source-provided `published_at`，且没有经证实的 `effective_from`/validity
provenance，因此结果为 `0 imported / 3 metadata-blocked`。没有修改 Frozen M2，也没有补造
时间。

Synthetic precise-time fixture 可以通过现有 `KnowledgeService.add_source`，说明 adapter 路径
可用；真实 pack 是否能不改 baseline 服务 Blum，必须等 coverage 与合法时间元数据解决后再
验证。

## 8. Blum RAG smoke validation

结果：**Not run / deliberately stopped before final smoke**。

`smoke-cases.json` 只是基于 3 篇已取得页面形成的 provisional case draft，不代表正式验证。
0-source 空库查询曾返回 `no_authoritative_source`、0 citations，但这不能证明 retrieval、回答
完整性或引用质量。coverage review 完成后仍存在 acquisition 与 metadata blocker，因此不进入
最终 Frozen M2 smoke。

## 9. Finding 分类

| 类别 | Finding | 当前状态 |
|---|---|---|
| acquisition | Help 72/72 官方 URL 返回 403；Blog 74 个官方重试返回 404 | blocker |
| metadata | 3 篇正文只有 date-only publication，无 confirmed effective validity | blocker |
| coverage | 2024 Blog 0/18；Help 0/72；无 FAQ/troubleshooting/rule corpus | blocker |
| Frozen M2 compatibility | 真实 3-source corpus 无法诚实通过时间门禁 | 未证明是 RAG 缺陷 |
| genuine M2 retrieval/answering | 未进入可运行 corpus | not evaluated |

当前没有证据支持重新打开 M2 Product Freeze。

## Help Center 合法 fallback

自动 acquisition 继续失败时，下一步应采用 **manual/public-browser snapshot ingestion**：

1. 操作者在可正常访问的普通公共浏览器中打开官方 `help.blum.io` 页面；不绕过登录、挑战或
   访问控制。
2. 保存官方页面 HTML/PDF snapshot，同时记录 canonical URL、observed time、浏览器可见标题、
   raw hash 与捕获方式。
3. 仅在人工确认 snapshot 确实来自官方 origin 后进入 normalizer；搜索缓存、Wayback 正文或
   第三方转载不得自动晋升为 authority source。
4. 页面未提供发布时间、更新时间或有效期时继续留空，由 Frozen M2 门禁决定是否可导入。

当前本机公共浏览器同样返回 403，所以 fallback 已提出但尚未执行。

## 10. 第二阶段建议

**暂不把 Telegram official announcement / status acquisition 作为替代方案来掩盖 Phase 1
缺口。** 先完成 Help 的合法 snapshot ingestion 或确认官方可用 endpoint，并为 74 个 Blog
archive fallback candidate 建立单独人工审批策略。若 Phase 1 仍不能补足 2024 时间线，再开
独立第二阶段接入 Telegram official announcement / status；它们更可能提供精确 message
timestamp，但仍必须与 community chat 分离，并保留 message/source ID 与官方身份依据。

本 Track 保持隔离，不 merge，不修改 M3/M4，不重新打开 Frozen M2。

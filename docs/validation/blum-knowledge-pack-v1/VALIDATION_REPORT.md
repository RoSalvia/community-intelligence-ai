# Blum Temporal Precision + Official Telegram Knowledge — Review Gate

状态：**LOCAL IMPLEMENTATION COMPLETE / REVIEW GATE**

Branch：`blum-knowledge-acquisition`
起始 checkpoint：`9335b3f29eba271653e65ea54e6ef910f35c5d9f`

## 决策结论

77 篇官方 Blog 与 1091 条 text-bearing 官方 Telegram announcement 已诚实进入同一个私有
Blum Knowledge Base，共 1168 个独立 source、8216 个 Frozen M2 chunks，导入 blocker 为 0。
Blog 保持 day precision，Telegram 保持 second precision；没有制造 midnight，也没有把
announcement timestamp 默认当作生效时间。

本轮未修改 Frozen M2 的 chunking、hybrid retrieval、reranker、authority ranking、answer
policy 或模型参数。全量回归结果为 `418 passed, 7 skipped`。

## 1. Temporal precision contract

数据库 schema 升级为 v3，revision 同时支持：

- `published_on: date | null`
- `published_at: datetime | null`
- `temporal_precision: day | second`
- `effective_from: datetime | null`
- `effective_until: datetime | null`

约束为：day source 必须有 `published_on` 且不得有 `published_at`；second source 必须有
`published_at`。v1/v2 既有 precise-datetime revision 在迁移时解释为 second precision，旧数据与
API 行为保持兼容。

`as_of_time` 对 day source 按 query date 过滤；精确查询与 Blog publication 落在同一天时，citation
与 answer trace 返回 `same_day_publication_time_unknown`。Telegram 则按真实 UTC timestamp 做
精确过滤。

## 2. Blog midnight fabrication

完全避免。77/77 Blog 均为：

`published_on=<official catalog date>, published_at=null, temporal_precision=day`

导入审计 `midnight_fabrication_count=0`。Wayback snapshot time 仅保留为 archive capture metadata，
没有被提升为 publication time；acquisition observed time 也没有被当作 validity time。

## 3. Blog import

| 指标 | 结果 |
|---|---:|
| official Blog catalog | 77 |
| current-live | 3 |
| official-index-linked archive | 74 |
| imported | 77 |
| blocked | 0 |
| day precision | 77 |

每篇保留 original Blum URL、title、full normalized body、language、publication date、archive 与
acquisition metadata、provenance chain、raw/content hash。正文与完整 inventory 仅在 ignored
private storage。没有独立 validity 证据的 77 篇均显式记录 `validity=not-provided`，而不是
`human-confirmed`。

## 4–5. Official Telegram announcement corpus

频道 `Blum: All Crypto – One App` 的 export identity 为 public channel ID `10629372799`；Blum
官方页面对 `@blumcrypto` 的链接与公开 channel metadata 构成一手身份链，因此记录为
`authority=official`、`source_type=telegram_announcement`、`source_channel=telegram`。

在 live export 继续增长的同时，对目标完整 object 做了三次检查：source size 从 86,960,846
增长至 86,989,032 bytes，但 byte range `[49052210, 52060211]` 与 range hash 连续稳定。随后才
发布 immutable private snapshot；live `result.json` 未修改、移动或截断。

| 指标 | 结果 |
|---|---:|
| ordinary messages | 1178 |
| text-bearing Knowledge messages | 1091 |
| textless ordinary excluded | 87 |
| service events excluded | 48 |
| ordinary precise timestamps | 1178/1178 (100%) |
| imported Telegram sources | 1091 |
| language | en 1082 / und 9 |

每条 text-bearing ordinary message 是一个独立 source，正文完整进入 private RAG；保留
message ID、entities、links、forward metadata、reactions、language、canonical message URL 与
hash。export 没有提供可保留的 media path/reference，因此本 snapshot 的 media-reference count
为 0；未做 OCR/ASR。1091 条来源的 validity provenance 同样是 `not-provided`。

## 6. 2024-03～09 official Knowledge coverage

| source type | count |
|---|---:|
| Official Blog | 13 |
| Official Telegram Announcement | 291 |
| combined independent sources/messages | 304 |

月度 Telegram 分布：Mar 23、Apr 42、May 46、Jun 45、Jul 44、Aug 49、Sep 42。

## 7. Hero events cross-source coverage

已有 10 个 Blog Hero events 全部找到独立 Telegram evidence：Crypto with Blum、app overview、
Mini App、FAQ、developer recruitment、Roadmap、Drop Game、Quests、Pokras Lampas、Tribes，结果
为 `10/10`。

其中 Mini App、developer recruitment、Roadmap、Quests、Pokras、Tribes 是同日双来源。Blog
没有日内时刻，因此只报告 same-day ambiguity，不用 Telegram timestamp 回填 Blog。未发现这
10 组证据存在 material cross-source contradiction，也没有做社区行为因果推断。

`Season 1` 在 2024-03～09 window 内没有明确官方引用；频道首次明确出现是 message 553，时间
为 `2024-12-23T20:16:04Z`，且属于回顾性表述，因此不把它硬塞入目标 window。

## 8. Telegram-only important events

发现 Blog timeline 未覆盖或粒度不足的重要 marker，包括：

- Blum Points farming prelaunch（message 41）；
- Drop Game ticket-expiry change announcement（message 211）；
- Roadmap update（message 249）；
- Frens o Mania campaign（message 258）；
- 40M 与 50M user milestones（messages 277、339）。

这些 marker 只作为官方时间证据。正文没有给出无歧义 effective instant 的条目保持
`effective_from/effective_until=null`；没有将 announcement time 当作生效时间。

## 9. Blum RAG smoke

完整 private import：1168/1168 sources、8216 chunks、0 blocked。按“小型 smoke、不调参”的范围，
另用 2 篇 Blog + 2 条 Telegram announcement 建立 controlled hybrid index，验证：

- 每个 query 同时使用 `fts5_bm25` 与 `multilingual_embedding`；
- Tribes Telegram message 257 在 `2024-07-22T10:27:50Z` 之前被排除，之后可召回；
- 同日 Blog 可作为 day-level candidate，但 citation/trace 明示日内时间未知；
- Mini App 与 Tribes query 均能同时召回 Blog 和 Telegram 两种独立 source；
- 所有 smoke citation 均可回到真实 source/revision/chunk；
- 两种来源没有 cross-source dedup，也没有融合为虚构 document；
- 未调 chunk size、embedding model、weights、TopK、reranker 或 authority weights。

在 target event publication 前，现有 broad retrieval 仍可能返回其他较早、词面相关的官方
source；answer model 未配置时会保持 `insufficient_evidence`。这不是 temporal leakage，但可作为
未来 relevance evaluation backlog，本轮不据此改 Frozen M2。

## 10. Frozen M2 regression

| check | result |
|---|---|
| focused temporal/Telegram/API/migration tests | 46 passed |
| full suite | 418 passed, 7 skipped |
| Ruff | passed |
| Telegram aggregate schema | passed |

冻结版本仍为：

- chunker `structure-v1`
- retrieval `sqlite-fts5-rrf-structure-v2`
- ranking `authority-validity-rrf-v4`
- conflict policy `majority-one-slot-v1`
- answer policy `material-facts-evidence-v2`
- multilingual policy `multilingual-listwise-v1`

## 11. Remaining blockers and limits

本轮 Blog + Telegram Knowledge import 与 temporal compatibility 没有真实 blocker，可以进入人工
review，但不代表整个 Blum Knowledge coverage 已完整：

- Help Center 仍为 `unavailable / site-side access failure`，候选 72、获取 0，观测到 Cloudflare
  Error 1000；未绕过、未用 search snippets，且它不阻塞本轮 Blog + Telegram。
- 本轮没有为任何 Telegram message 建立可审计的独立 effective instant；有效期字段均保持
  null。后续若做人工规则/campaign validity review，可只对有明确正文证据的 message 补充，
  不能从 publication timestamp 推断。
- 按产品要求只做 controlled hybrid smoke；完整 1168-source private corpus 已导入并分块，但未
  额外生成 production-scale semantic cache。这不是功能 blocker，也没有借 smoke 做参数优化。

## Artifacts and privacy boundary

- Telegram aggregate：`telegram-announcement-aggregate.json`
- Telegram schema：`docs/schemas/blum-telegram-announcement-pack-v1.schema.json`
- Timeline：`official-knowledge-timeline-2024-03-09.json`
- Smoke：`temporal-telegram-smoke.json`
- Full normalized Blog/Telegram corpus、raw snapshot、hash ledger、DB 与 detailed smoke results：
  ignored `data/private/blum-knowledge-pack-v1-2026-09-11/`

Git 中不含 raw Telegram export、full snapshot、公告正文、media、raw sender/user identifiers、
secret 或 private DB。本 Track 停在 review gate；不 merge main，不 push，不启动 M3/M4。

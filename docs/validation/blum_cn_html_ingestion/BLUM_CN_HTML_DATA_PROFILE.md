# Blum CN Telegram HTML Data Intake / Canonicalization

状态：`Verified for review`。本报告只包含结构与聚合统计，不包含聊天全文、用户名、用户映射或媒体内容。本轮未执行 Topic、Behavior、RAG、Signal、OCR、ASR 或远程 API。

## 数据边界与来源审计

- 发现 3 个 Telegram Desktop HTML export 目录、10 个 `messages*.html`。
- 三个目录是同一社区的累计快照，不是互斥分片。`ChatExport_Blum 官方中文社区🇨🇳_2` 是包含全部 33,562 个带 ID 事件的最大快照；其 7 个 HTML 页面作为 canonical selection source，较早两个快照作为重复 provenance 保留。
- 全部快照共包含 41,656 个 message/service block occurrences：普通消息 occurrence 41,028，service occurrence 628。
- HTML 时间字段精确到秒，但源文件没有时区元数据。当前运行以 `Asia/Shanghai` 作为显式 execution assumption，将 source-local 时间转换为 UTC；每条消息同时保留原始 `title`、local datetime、timezone assumption 与 provenance。该假设可通过重跑替换，不应解释为 Telegram 源文件已证明时区。
- `/Users/enm1cuarto/Downloads/` 全程只读。第一次与最终运行的全输入 fingerprint 相同，证明本轮未改变源 export。

## Canonical profile

| 项目 | 结果 |
|---|---:|
| Canonical ordinary messages | 33,380 |
| Canonical service events | 310（182 个带 source ID；128 个无 ID date divider） |
| Source-local 时间范围 | 2024-03-19 09:11:45 — 2024-08-18 21:09:15 |
| UTC 时间范围（按上述假设） | 2024-03-19T01:11:45Z — 2024-08-18T13:09:15Z |
| Text-only | 32,379 |
| Media-only | 608 |
| Mixed text + media | 393 |
| Empty（无 text 且无 media） | 0 |
| Unique display-name values | 1,246 |
| Conservative anonymized author identities | 5,063 |
| Deleted Account messages | 6,006（3,818 个显式锚点；2,188 个 joined 继承） |
| Missing author after structural recovery | 0 |
| Forwarded messages | 731 |
| Messages containing hyperlinks | 1,626 |
| Hyperlink records | 9,076 |

HTML 不提供稳定 Telegram user ID。普通 author identity 只能基于 display name 加 private salt；display-name 变化可能拆分同一用户，同名可能合并不同用户。`Deleted Account` 不被合并成一个人：每个显式 anchor 使用独立保守 identity，后续 joined 消息只继承该 anchor。

## Reply 与 joined 恢复

| 项目 | 结果 |
|---|---:|
| Reply records | 7,858 |
| Resolved replies | 4,603 |
| 其中跨 `messages*.html` 页面恢复 | 9 |
| Unresolved replies | 3,255 |
| Resolution rate | 58.577246% |
| Joined messages | 12,888 |
| Joined author inheritance success | 12,888 |
| Joined author inheritance failure | 0 |

所有 `#go_to_message<ID>` 均已解析并保留原始 target ID。3,255 个 unresolved reply 的目标 ID 不存在于任一输入快照；它们仍保留在 canonical message 中，只是 `reply_to_canonical_message_id=null`。这属于 source coverage limitation，不是 parser loss，也不进入 parse quarantine。

## Media reference profile

| Kind | Canonical refs |
|---|---:|
| Photo | 750 |
| Sticker | 196 |
| GIF | 10 |
| Video file | 2 |
| Embedded video（export 未提供本地文件） | 43 |
| Embedded photo（export 未提供本地文件） | 1 |
| Location link | 2 |
| **Total** | **1,004** |

- 960 个 local media refs 全部存在并完成 SHA-256；12 个 thumbnail refs 全部存在并完成 SHA-256。
- 2 个外部 location refs 只保留 URL；42 个无 path embedded refs 显式保留 unavailable 状态。
- 旧累计快照中 2 个可用 video file 与新快照的 `not included` 表现冲突；canonical media manifest 同时保留两个 variant，没有用新快照覆盖旧资源。
- 本轮不读取媒体语义，不做 OCR、视觉理解或 ASR。

## Duplicate、quarantine 与 parse loss

- 5,671 个 source message IDs 在累计快照间重复，共有 7,867 个 first occurrence 之外的重复 occurrence。
- Canonical ordinary `source_message_id` 与 `message_id` 均唯一；每条逻辑消息的 `source_occurrences` 保留所有重复位置与 raw fragment hash。
- 3 个重复 ID 的导出结构存在冲突：`2630`、`3358`、`17589`。最大快照 occurrence 被选为主记录，全部 occurrence 仍可回溯，冲突进入 `parse_quarantine.jsonl`。
- Parse quarantine：3；malformed message：0；parse loss：0。
- 每个 source block 都通过 `source_html_file + source_ordinal + start/end offset + raw_html_sha256` 回溯验证；41,656 / 41,656 occurrences 验证通过。

## M1 Message / Batch / Evidence compatibility

- 32,772 个 text-bearing messages 已生成标准 `CommunityDataset` projection，并通过现有 `read_dataset` 验证；JSON importer 的 message-ID digest contract 保持不变。
- 608 个 media-only messages 不能直接进入当前 `MessageRecord@1.1`，因为该 Frozen contract 要求非空 `text`。它们没有丢弃，仍完整保留在上层 canonical `messages.jsonl` 与 `media_manifest.jsonl`。
- Batch mapping 已写入 manifest：`source_type=telegram_desktop_html`、`content_hash=input_fingerprint`、窗口边界与 projection message count。
- Evidence mapping 使用稳定 canonical `message_id`；material claim 可从 M1 projection 的 `message_id` 回连上层 `messages.jsonl`，再定位全部 source occurrences。
- 当前状态是 `compatible_with_sidecar_retention`，不是“33,380 条全部原样符合 M1”。建议在 review 后正式保留 Telegram HTML adapter，并把 media-only envelope 作为通用 ingestion sidecar，而不是修改 Frozen JSON 行为或建立 Blum 专属下游模型。

## Private artifacts 与 fingerprints

当前 private canonical root（Git ignored）：

`data/private/blum-cn-html-ingestion/blum-cn-canonical-v1.0.0/`

其中：

- `messages.jsonl`：完整 33,380 条 canonical ordinary messages；
- `service_events.jsonl`：310 条 canonical service events；
- `media_manifest.jsonl`：1,004 条 media refs；
- `parse_quarantine.jsonl`：3 条结构冲突记录，不含聊天正文；
- `dataset_manifest.json`：schema、profile、input/output fingerprints、timezone 与 M1 mapping；
- `m1_dataset/`：现有 M1/M3/M4 reader 可直接读取的 32,772-message standard projection。

Fingerprints：

| Artifact | SHA-256 |
|---|---|
| Full input inventory | `5a6995dd8719462b0f8e7147a2df83e55d1021a94c1aede1d8e4216e82c9f7fa` |
| Canonical output generation | `9a4ae350ae8496984eb33373f0bcecb95bdf1e7e997cdc86f734c5052f075cb2` |
| Canonical `messages.jsonl` | `9dff7dc7cb0ffd57cc58be34f716098a584067e9c7dbd22d35fa5e06a7cdd25f` |
| Canonical `service_events.jsonl` | `5fb697ad0df99f3b356c0fb495ca1c0e7ef311c5adc244dbf47b0c2a2df39346` |
| Canonical `media_manifest.jsonl` | `d98c2e0f4f53ab9a767cec489c27b4c4c76c27b683b847d631f9cbb35c9d23bb` |
| Canonical `parse_quarantine.jsonl` | `d3c93647443222add3cfe7e4d9bb4e77f2db54611ba9ac8752b8cf67275c0d10` |
| M1 projection generation | `535d3581fddd1cf4e5964747d64058a0f2b2b176d1c47fce468919dffddfc8cc` |

真实输入使用同一 private identity salt 二次重跑，canonical 与 M1 projection 共 11 个文件逐字节一致。

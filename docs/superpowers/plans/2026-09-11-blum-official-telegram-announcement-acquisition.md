# Blum Official Telegram Announcement Acquisition — Phase 2 Plan

状态：**SUPERSEDED AND EXECUTED IN APPROVED SINGLE-CHANNEL SCOPE**

本计划原先要求新的执行批准。该批准已由后续
`2026-09-11-blum-temporal-telegram-knowledge.md` 明确给出；本轮仅执行已确认完整且有一手身份链的
`Blum: All Crypto – One App`，没有扩展到 CN/ES announcement discovery。

## Goal

为 `2024-03-19..2024-08-18` Blum CN Community Chat 建立精确时间的官方公告 Knowledge
timeline，补足 Blog 的离散日期与 Help Center 缺口。Telegram Official Announcement 属于
Project Knowledge；Community Chat 仍属于 Conversation Data，两者不得混入同一 ingestion
路径或 authority 身份。

## Scope gate

候选范围：EN official announcement channel、CN official news/announcement、ES official
news/announcement（若真实存在）。实施前必须由人工确认每个频道与 Blum 官方站、已验证官方
账号或其他一手身份来源之间的关系。仅凭频道名称、转发量、搜索结果或第三方列表不能获得
official authority。

不在本阶段自动获取私聊、用户群、Moderator 对话、回复线程或成员资料；不修改 Frozen M2、
M3/M4、chunking、reranker、authority policy 或 `as_of_time` logic。

## Acquisition contract

每条 official Knowledge message 至少保留：

- official channel identity 与人工确认依据；
- channel ID/username、source message ID 和 canonical message link；
- Telegram 原始 precise timestamp 与 timezone；
- text、entities、links 和 media references；
- edit timestamp、forward/reply metadata（存在时）；
- source language 与 metadata provenance；
- acquisition observed time、raw hash、normalized content hash；
- source deletion/unavailability 状态，不静默覆盖历史 snapshot。

原始用户标识、私有消息、API key、session 文件不得进入 Git。raw export、media、full message
text、cache 和 validation DB 只进入 ignored private storage。

## Implementation sequence

1. **Identity review**：列出 EN/CN/ES 候选频道与官方身份链，提交人工确认，不抓正文。
2. **Access/legal review**：确认可用公开导出/API/browser acquisition 方法、速率限制与保存范围；
   不绕过登录或平台访问控制。
3. **Controlled sample**：每个已批准频道选择 10–20 条覆盖 2024-03～08 的公告，验证 message
   ID、timestamp、edit、link/media、hash 与重跑确定性。
4. **Normalizer**：映射现有 Frozen enum，优先
   `telegram_announcement` / `official_announcement` / `maintenance_notice`；不新增
   Blum-specific taxonomy，不根据文本自动提升 authority。
5. **Timeline audit**：按 source timestamp 构建事件序列，识别 edit/replacement/conflict，和
   Historical Blog 的 10 个窗口内事件交叉核对，但不把两种来源合并为同一 revision。
6. **Batch gate**：controlled sample 全部或绝大多数通过且无身份/provenance 缺口后，才扩大到
   已批准频道的完整目标窗口。
7. **Frozen M2 probe**：只用真实 precise timestamp 与经确认的 validity metadata；若
   `effective_from` 仍未知则保持 blocked，不修改 M2 contract。

## Review outputs

- approved/rejected channel inventory；
- controlled acquisition report 与 failure taxonomy；
- versioned aggregate manifest、schema 与 hash ledger；
- 2024-03～08 official announcement timeline；
- Blog/Telegram coverage matrix；
- Frozen M2 honest-import count 与 metadata blockers；
- 不含正文的 Git artifacts。

未经新的执行批准，本计划不启动频道发现、认证、登录、消息抓取、导入或 smoke validation。

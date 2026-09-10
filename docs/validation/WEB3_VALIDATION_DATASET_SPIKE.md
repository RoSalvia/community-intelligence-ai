# Web3 Validation Dataset Spike — Sapienza XRP Telegram Archive

日期：2026-09-10

状态：Dataset Suitability Review complete；等待 Product Owner 确认；未进入 M2

## 一句话结论

**Conditional Go。** 该数据适合作为高噪声 Web3 事件社区的 Topic、Behavior 和 Hygiene 验证集，也能验证 Contributor Radar 的匿名用户级聚合与 Evidence 链；但它不适合单独验证 RAG、Moderator 识别、日常社区运营或 EN/CN/ES 多语言效果。

该 Telegram 群名为 “OFFICIAL BUY & HOLD XRP”，但没有证据表明它是 Ripple 或 XRPL 官方社区。本报告只称其为“XRP crowd-pump 群”。

## 来源与抽样

- 来源仓库：[SystemsLab-Sapienza/gme-pump-xrp-telegram](https://github.com/SystemsLab-Sapienza/gme-pump-xrp-telegram)，本次读取 commit da62fde43cac9e0cd7b00ed54da3aedfbff6d17b。
- 论文：[The Doge of Wall Street](https://arxiv.org/abs/2105.00733)。作者报告完整群有 45,548 条消息、约 200,000 名成员；它是 Telegram Group，不是只有管理员可发言的 Channel。
- 原始格式：120 个 Telegram Desktop HTML 文件；没有改动正式 JSON importer。
- 本轮仅解析 20 页：1–5、40–44、80–84、116–120。这是四个连续时间块，不是完整数据或随机总体样本。
- HTML、canonical JSONL 和完整 profiling 输出均在 Git 外临时目录处理，未提交仓库。

## 解析结果

| 项目 | 结果 | 产品含义 |
|---|---:|---|
| HTML message nodes | 6,394 | 包含少量无文本媒体消息 |
| 有效文本消息 | **6,370** | 全部通过现有 MessageRecord 校验 |
| 跳过的无文本消息 | 24 | 本轮不分析图片、视频、贴纸和文件 |
| 独立匿名用户 | **4,399** | 用户已由源仓库匿名化，adapter 再次哈希 |
| 消息时间跨度 | **2021-01-28 20:19:09 至 2021-02-03 12:35:35 UTC** | 抽样块之间有时间缺口，不能当作连续全量趋势 |
| 显式 reply 消息 | **897 / 6,370（14.1%）** | 每个 reply target 都能从 HTML href 解析 |
| 样本内立即恢复 reply | **752 / 897（83.8%）** | 其余 parent 多在未抽取页或为无文本消息 |
| 跨 HTML 页 reply | 176 | 证明 validation adapter 需要跨文件 source key |
| 文本重复组中的消息 | **2,600 / 6,370（40.8%）** | 适合测试去重与重复灌水 |

时间解释使用 Europe/Rome 本地时区转 UTC。首条 HTML 时间 21:19:09 转换后为 20:19:09 UTC，与论文报告的首条消息时间一致。

## 多人讨论还是管理员广播

结论：**真实多人群聊，且参与很广，但大量参与很浅。**

- 单一最活跃用户只占 2.68%，Top 10 用户合计占 6.47%，不符合少数账号主导广播的形态。
- 样本内恢复的 reply 中，98.5% 发生在不同用户之间。
- 4,399 个用户中，86.5% 只出现一次；这说明事件吸引了大量一次性参与者，不代表稳定社区关系。
- 源数据没有可靠管理员角色字段，不能据此识别 Mod 或比较 Mod 表现。
- 论文说明管理员曾关闭群聊，因此不同时间段的消息量也受到群开关影响，不能直接解释为社区需求变化。

## 行为可见性

以下只用于确认数据里“有没有足够候选”，不是标注真值。规则允许重叠，正式评测仍需人工 Golden Set。

| 候选行为 | 高召回候选数 | 占样本 | 人工 spot-check |
|---|---:|---:|---|
| Question / Help | 660 | 10.4% | 明确存在，集中在交易平台、地区可用性、时间和操作方式 |
| Peer Support | 60 | 0.9% | 明确存在，但不少回答极短，回答不等于正确或安全 |
| Project Discussion | 1,719 | 27.0% | 很丰富，涉及 XRP、Ripple、SEC、交易所、钱包、价格与活动协调 |
| Complaint / Concern | 95 | 1.5% | 存在诈骗质疑、平台限制、价格下跌和对管理员信息的抱怨 |
| Filler / short hype | 4,234 | 66.5% | 极丰富，短口号、单词、emoji 和情绪推动很多 |
| Repetitive | 2,600 | 40.8% | 极丰富，适合测试复制转发、口号和重复宣传 |

## 对各能力的适用性

| 能力 | 结论 | 可以验证 | 主要限制 |
|---|---|---|---|
| Topic | **适合** | 高速事件中的主题发现、主题合并、时间变化和 Evidence 回溯 | 单一 XRP 事件、主题很窄；不是日常社区；缺少 Topic ground truth |
| Behavior | **适合** | Question、Help、Peer Support、Complaint、hype、coordination 等重叠行为 | 无人工标签；讽刺、投机话术和错误建议很多，必须允许 Uncertain |
| Contributor Radar | **部分适合** | 稳定匿名用户、跨用户 reply、回答证据和反灌水规则 | 无可联系身份、无 Mod 角色、86.5% 用户只发一条；不能验证真实运营可行动性 |
| Hygiene | **非常适合** | filler、emoji-only、精确重复、复制宣传、机器人命令和异常爆发 | 只覆盖极端事件场景，不能据此设定正常社区阈值 |
| RAG | **不适合作为 Source of Truth** | 可作为不可信聊天、噪声检索和 prompt-injection 防线的负向测试 | 没有配套官方知识库，聊天里的金融与项目说法不能当作事实；需另配权威文档 |

因此，这个数据集不能成为唯一 validation dataset。后续仍需要：普通运营周期社区、EN/CN/ES 多语言样本、带角色/贡献人工标注的数据，以及与官方项目资料配对的 RAG benchmark。

## 许可与隐私边界

- 本次固定 commit 中没有找到 LICENSE 或 COPYING 文件。README 要求引用论文，但“请引用”不是明确的数据再利用许可证。
- 目前无法确认是否允许重新分发原始消息、发布衍生 benchmark、用于商业作品集演示或发送给第三方模型；公开 GitHub 可访问不等于拥有这些权利。
- README 表示用户已经匿名化，但正文仍可能包含链接、转发来源或其他可关联信息。adapter 会再次哈希 sender，并替换正文中的 64 位源匿名标识；这仍不能证明彻底去标识。
- 当前建议只做本地、内部、研究型 suitability/evaluation。进入 Portfolio Demo、公开 benchmark 或 remote LLM 处理前，需要获得维护者的明确许可或完成适用的法律/伦理审查。
- 图片、视频、贴纸和共享文件未纳入本轮；它们还可能有独立版权和隐私风险。

## 26 条去标识样例

以下均为**中文语义转述，不是逐字引文**；保留 source message ID 便于复核，不展示用户标识。

| ID | 候选行为 | 去标识语义转述 |
|---|---|---|
| xrp_tg_65 | Question / Help | 纽约用户询问还能在哪个平台购买 XRP，并表示 Uphold 不可用。 |
| xrp_tg_2555 | Question / Help | 询问 Crypto.com 是否适合购买。 |
| xrp_tg_2838 | Question / Help | 美国用户询问如何购买 XRP。 |
| xrp_tg_3045 | Question / Help | 多个平台暂停交易后，询问其他人通过什么渠道购买。 |
| xrp_tg_3218 | Question / Help | 询问群里是否约定了最低购买金额。 |
| xrp_tg_71 | Peer Support | 回复纽约购买问题，建议尝试 Kraken。 |
| xrp_tg_2563 | Peer Support | 回复平台可用性问题，称美国地区不可用并建议尝试 Uphold。 |
| xrp_tg_2848 | Peer Support | 回复美国购买问题，列出 Bitrue、KuCoin 和 Uphold。 |
| xrp_tg_3049 | Peer Support | 对交易平台暂停问题给出一个很短的平台建议。 |
| xrp_tg_3226 | Peer Support | 回复最低金额问题，表示只应投入个人能承受的金额。 |
| xrp_tg_3410 | Project Discussion | 建议使用个人钱包，不要长期把 XRP 留在交易所，也不要公开钱包地址。 |
| xrp_tg_3442 | Project Discussion | 讨论“美国用户暂停交易”和“交易所全面下架 XRP”的区别。 |
| xrp_tg_3541 | Project Discussion | 质疑只协调买入却无人协调卖出，并担忧并非所有人都会持有。 |
| xrp_tg_3812 | Project Discussion | 讨论价格上涨、外部 FOMO 与随后回落之间的可能关系。 |
| xrp_tg_2583 | Project Discussion | 询问这次活动究竟是拉高后卖出，还是买入后长期持有。 |
| xrp_tg_3601 | Complaint / Concern | 将另一个拉盘群称为骗局，并要求传播当前群链接。 |
| xrp_tg_4440 | Complaint / Concern | 抱怨 Robinhood 限制 Dogecoin 交易。 |
| xrp_tg_254583 | Complaint / Concern | 用一句很短的话直接质疑活动是骗局。 |
| xrp_tg_254885 | Complaint / Concern | 警告其他成员可能成为高位接盘者。 |
| xrp_tg_256855 | Complaint / Concern | 在事件高峰期直接宣称这是骗局。 |
| xrp_tg_3 | Filler | 简短打招呼，没有业务信息。 |
| xrp_tg_254587 | Filler | 只发送连续爆炸 emoji。 |
| xrp_tg_256984 | Filler | 只表达“开始/冲”的情绪。 |
| xrp_tg_257965 | Filler | 只有一个买入口号。 |
| xrp_tg_258965 | Filler | 重复拉盘口号并附带火焰、火箭 emoji。 |
| xrp_tg_178032 | Repetitive | 长篇复制宣传活动时间、号召转发，并附带风险免责说明。 |

这些样例也说明：结构上的“回答”可能是未经验证的金融建议；高活跃和高回复不能直接解释为高质量贡献。

## 数据许可与再利用风险

**当前为 High / unresolved。**

- 目标仓库没有 LICENSE 文件，也没有在 README 中授予明确的复制、修改、再分发或商业使用许可；“公开仓库”和“请引用论文”不能替代许可证。
- README 声明用户已匿名化，但消息正文仍可能含链接、转发内容、残余名称或可关联线索。adapter 已再次哈希发送者，并替换正文中的 64 位源匿名标识，但这不等于完成法律或伦理审查。
- 论文讨论了研究采集与公开发布，但未在本轮找到可覆盖下游产品 benchmark/portfolio 再利用的明确授权。

在获得作者许可或完成法律/伦理确认前：

1. 只允许本地、内部、非商业 suitability/evaluation；
2. 不提交原始 HTML、媒体、canonical JSONL 或长篇逐字聊天；
3. 不在 Portfolio Demo 分发数据集；
4. 不将该样本结果表述为真实业务收益；
5. 发布任何派生 benchmark 前，先确认许可范围与必要引用方式。

## 实现边界

- validation-only adapter：[xrp_telegram_html_spike.py](../../scripts/validation/xrp_telegram_html_spike.py)
- 使用 Python 标准库 HTML parser，没有新增依赖。
- 只输出当前 MessageRecord 所需字段；source sender 再哈希，正文中的 64 位源匿名标识被替换。
- 不修改、不调用或扩展正式 Telegram JSON importer。
- 没有新增 Topic、Behavior、Contributor、Hygiene、RAG 或 M2 产品逻辑；候选规则只属于本次 suitability profiling。

# TON Docs External Validation — casebook

34 个原始问题全部保留；未经优化的 baseline-run-1。Complete 是严格完整答案；partial 不等于全部错误。AI 人工式审读，尚未经 Product Owner 独立标注。

`source-key:ordinal` 对应固定 commit 的 source / section / chunk。下表 bm25 越小越好（SQLite 负值）；semantic 为余弦相似度，RRF rank 是后处理之前排名；空值表示未匹配或未进入 20+20 候选池，不是 0 分。完整 UUID/hash 只位于本机 ignored validation results。

## T01 — success

Which wallet.account.chain values identify mainnet and testnet in TON Connect?

Expected: `grounded`; returned: `grounded`; answer: **complete**.

验收事实：Map mainnet to -239 and testnet to -3, not just mention chain.

判定：链编号及主网/测试网映射完整，首位证据正确。

分类：success

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:1 / How do I tell if the user is on mainnet or testnet? | -39.004267 | 1 | 0.698081 | 1 | 0.032787 / 1 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:1 / How do I tell if the user is on mainnet or testnet? | -39.004267 | 1 | 0.698081 | 1 | 0.032787 / 1 |

原始 RRF Top-5: faq:1, faq:13, faq:11, connect:1, addresses:15

## T02 — retrieval_miss

Where does a TON Connect dApp read the maximum number of messages allowed in a transaction batch?

Expected: `grounded`; returned: `grounded`; answer: **wrong**.

验收事实：maxMessages of SendTransaction in wallet.device.features; split larger batches.

判定：FAQ maxMessages 段落词法第 63、语义第 59，未进入候选池；返回 Highload 的吞吐能力，混淆协议能力协商与钱包吞吐。FAQ 问题 heading 未进入正文索引，答案以 Bounded 开头。

分类：lexical_mismatch, false_grounded

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:16 / How big can a transaction batch be? | -6.335048 | 63 | 0.435694 | 59 | — / — |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | wallet_comparison:24 / Payment gateways | -15.707913 | 2 | 0.674930 | 1 | 0.032522 / 1 |

原始 RRF Top-5: wallet_comparison:24, highload3:156, faq:1, highload2:47, faq:12

## T03 — answer_selection

Which checksum algorithm protects a user-friendly TON address, and how many bytes does the checksum occupy?

Expected: `grounded`; returned: `grounded`; answer: **wrong**.

验收事实：CRC16-CCITT, 2 bytes over preceding 34 bytes.

判定：CRC16/2-byte 正确块已在 Top-K；答案只复制首块的 Luhn 类比，没有回答算法和长度，不能把类比当作算法。

分类：false_grounded, insufficient_answer_context

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | addresses:15 / Structure | -15.436617 | 6 | 0.636117 | 2 | 0.031281 / 4 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | addresses:16 / Structure | -23.440712 | 2 | 0.644684 | 1 | 0.032522 / 1 |
| 2 | addresses:15 / Structure | -15.436617 | 6 | 0.636117 | 2 | 0.031281 / 4 |
| 3 | addresses:14 / Structure | -25.210918 | 1 | 0.604488 | 3 | 0.032266 / 2 |
| 4 | addresses:12 / User-friendly format | -20.011472 | 3 | 0.588016 | 4 | 0.031498 / 3 |

原始 RRF Top-5: addresses:16, addresses:14, addresses:12, addresses:15, addresses:17

## T04 — post_rrf_policy

Why can a Highload v3 batch send only 254 outgoing messages rather than 255?

Expected: `grounded`; returned: `grounded`; answer: **wrong**.

验收事实：One action slot is used for set_code protection, leaving 254.

判定：正确解释在原始 RRF 第 4，但被 relevance 窄带筛选移除。答案只剩 two-transaction pattern 的引导句，没有 set_code 保留一个 action slot 的原因。

分类：false_grounded

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload3:124 / Single message per external | -27.786567 | 2 | 0.458444 | 27 | 0.016129 / 8 |
| 2 | highload3:156 / Protection against `set_code` | -23.750884 | 3 | 0.502085 | 13 | 0.029572 / 4 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload3:113 / Message sending flow | -15.146368 | 9 | 0.733952 | 1 | 0.030886 / 2 |
| 2 | highload3:112 / `message_to_send` (reference cell) | -32.196179 | 1 | 0.654838 | 2 | 0.032522 / 1 |

原始 RRF Top-5: highload3:112, highload3:113, highload2:47, highload3:156, highload3:73

## T05 — post_rrf_policy

Which TVM codepage is currently implemented?

Expected: `grounded`; returned: `grounded`; answer: **wrong**.

验收事实：Only codepage 0; not an unrelated codepage discussion.

判定：codepage 0 词法第 2、RRF 第 4；正文短且无 TVM heading，筛选后只返回 -1/-2 尚未实现。没有回答当前实现哪一页。

分类：false_grounded, heading_context_loss

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | whitepaper_comments:6 / 5.1. Codepages and interoperability of different TVM versions | -17.362844 | 2 | 0.405101 | 8 | 0.030835 / 4 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | whitepaper_comments:9 / B.2. Step function of TVM | -22.304030 | 1 | 0.709198 | 1 | 0.032787 / 1 |

原始 RRF Top-5: whitepaper_comments:9, whitepaper_comments:8, whitepaper_comments:3, whitepaper_comments:6, whitepaper_comments:7

## T06 — success

In the legacy Catchain BCP proof, what fraction of processes is assumed to be Byzantine?

Expected: `grounded`; returned: `grounded`; answer: **complete**.

验收事实：Strictly less than one third; contextualize as legacy proof rather than asserting current deployed consensus.

判定：正确提供 legacy proof 的 Byzantine 占比严格小于三分之一；问题本身限定 legacy。

分类：success

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | catchain:14 / 1   Overview | -4.534067 | 64 | 0.569910 | 5 | 0.015385 / 14 |
| 2 | catchain:161 / 3.5. Validity of BCP | -15.210463 | 2 | 0.710007 | 1 | 0.032522 / 2 |
| 3 | catchain:162 / 3.5.1. Fundamental assumption | -16.497858 | 1 | 0.640218 | 2 | 0.032522 / 1 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | catchain:161 / 3.5. Validity of BCP | -15.210463 | 2 | 0.710007 | 1 | 0.032522 / 2 |
| 2 | catchain:162 / 3.5.1. Fundamental assumption | -16.497858 | 1 | 0.640218 | 2 | 0.032522 / 1 |

原始 RRF Top-5: catchain:162, catchain:161, catchain:164, catchain:163, catchain:129

## T07 — answer_selection

I selected another account inside my wallet. How do I make my connected dApp use that account instead?

Expected: `grounded`; returned: `grounded`; answer: **partial**.

验收事实：Disconnect and reconnect in the dApp; switching in wallet alone does not switch dApp account.

判定：操作步骤原始 RRF 第 1，被筛掉但在 ±1 context 中；答案解释账户固定，却不告诉用户 disconnect/reconnect。

分类：post_rrf_policy, insufficient_answer_context

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:14 / Why is there no `accountChanged` event? | -15.849320 | 1 | 0.588768 | 2 | 0.032522 / 1 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:13 / Why is there no `accountChanged` event? | -15.140329 | 2 | 0.714091 | 1 | 0.032522 / 2 |

原始 RRF Top-5: faq:14, faq:13, connect:2, troubleshooting:23, catchain:113

## T08 — success

Must an ordinary app developer deploy their own TON Connect bridge server?

Expected: `grounded`; returned: `grounded`; answer: **complete**.

验收事实：Usually no; wallet provider operates bridge listed for the selected wallet.

判定：准确说明普通 dApp 开发者通常不需要自建 bridge，由钱包方提供。

分类：success

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:4 / How do I make my own bridge? | -19.094283 | 1 | 0.563867 | 1 | 0.032787 / 1 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:4 / How do I make my own bridge? | -19.094283 | 1 | 0.563867 | 1 | 0.032787 / 1 |
| 2 | connect:4 / Build a dApp | -7.267209 | 37 | 0.559882 | 2 | 0.016129 / 6 |
| 3 | faq:6 / How do I make my own bridge? | -15.406375 | 2 | 0.499203 | 3 | 0.032002 / 2 |
| 4 | whitepaper_comments:35 / 5. TON Payments | -3.166762 | 104 | 0.498052 | 4 | 0.015625 / 7 |

原始 RRF Top-5: faq:4, faq:6, connect:9, connect:16, connect:14

## T09 — answer_selection

Is Highload Wallet v2 recommended for a new deployment, or has it been replaced?

Expected: `grounded`; returned: `grounded`; answer: **partial**.

验收事实：v2 deprecated; use v3 for new deployments. Current statement about legacy artifact is answerable despite historical source status.

判定：首位输出只是 v3 recommended 的链接列表；v2 Deprecated 警告已在第二个 citation，却没有进入答案。严格 rubric 要求明确弃用与新部署建议；宽松人工评分可能接受链接提示，单独保留为 partial。

分类：insufficient_answer_context

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload2:1 / (no section) | -22.671365 | 1 | 0.654195 | 2 | 0.032522 / 1 |
| 2 | highload2:6 / What is Highload Wallet v2? | -15.418633 | 3 | 0.495378 | 14 | 0.029387 / 7 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload2:67 / See also | -19.576514 | 2 | 0.655296 | 1 | 0.032522 / 2 |
| 2 | highload2:1 / (no section) | -22.671365 | 1 | 0.654195 | 2 | 0.032522 / 1 |
| 3 | highload2:66 / Implementation | -11.050718 | 11 | 0.597185 | 3 | 0.029958 / 5 |
| 4 | highload2:4 / What is Highload Wallet v2? | -11.222149 | 10 | 0.596132 | 4 | 0.029911 / 6 |

原始 RRF Top-5: highload2:1, highload2:67, highload2:0, highload2:12, highload2:66

## T10 — correct_source_low_rank

hey my ton wallet says USER_REJECTS_ERROR lol... is our app broken or did the user just bail? what should we show them?

Expected: `grounded`; returned: `grounded`; answer: **wrong**.

验收事实：User cancelled/closed before signing; soft cancellation message and retry, not system error.

判定：USER_REJECTS_ERROR 位于 heading 而非可检索正文；取消/重试块词法第 1、语义第 29、RRF 第 11，最终返回 UNKNOWN_APP 会话撤销原因，不是用户取消。不能只归因于口语。

分类：lexical_mismatch, false_grounded, heading_context_loss

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | troubleshooting:13 / `USER_REJECTS_ERROR` — code 300 | -11.630741 | 8 | 0.418054 | 23 | 0.014706 / 15 |
| 2 | troubleshooting:14 / `USER_REJECTS_ERROR` — code 300 | -17.207665 | 1 | 0.404253 | 29 | 0.016393 / 11 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | troubleshooting:23 / `UNKNOWN_APP_ERROR` — code 100 | -9.353595 | 15 | 0.611853 | 1 | 0.029727 / 4 |

原始 RRF Top-5: connect:2, troubleshooting:44, wallet_comparison:13, troubleshooting:23, troubleshooting:38

## T11 — false_no_answer

highload v3 keeps yelling 35 at me even tho i just made the tx!! my laptop clock is right, what time should i put?

Expected: `grounded`; returned: `insufficient_evidence`; answer: **abstain**.

验收事实：On-chain now is last processed block time; set created_at 30-60 seconds before current time.

判定：时间落后解释和提前 30–60 秒建议在检索及 ±1 扩展中；首位语义 0.520 未跨 grounded 0.55 阈值，拒答并非没有答案。

分类：answer_status_threshold

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload3:57 / Timestamp validation | -10.356804 | 7 | 0.519541 | 1 | 0.031319 / 1 |
| 2 | highload3:58 / Timestamp validation | -3.973279 | 105 | 0.423734 | 6 | 0.015152 / 14 |
| 3 | highload3:60 / Timestamp validation | -9.703366 | 12 | 0.357831 | 19 | 0.026547 / 3 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload3:57 / Timestamp validation | -10.356804 | 7 | 0.519541 | 1 | 0.031319 / 1 |
| 2 | highload3:37 / `timeout` (22 bits) | — | — | 0.467726 | 2 | 0.016129 / 6 |
| 3 | highload3:101 / `timeout` (22 bits) | — | — | 0.464353 | 3 | 0.015873 / 8 |
| 4 | highload2:39 / `query_id` (64 bits) | — | — | 0.460432 | 4 | 0.015625 / 10 |
| 5 | catchain:184 / 3.5.8. Assumptions for proving the convergence of the protocol | -5.899671 | 66 | 0.449895 | 5 | 0.015385 / 12 |

原始 RRF Top-5: highload3:57, highload3:68, highload3:60, whitepaper_comments:17, whitepaper_comments:19

## T12 — correct_source_low_rank

manifest loads fine on my own site but wallet still can't grab it... cors thing??

Expected: `grounded`; returned: `grounded`; answer: **partial**.

验收事实：Cross-origin wallet access; permit unauthenticated origins and permissive CORS, not only dApp origin.

判定：CORS 解释语义第 5、RRF 第 6，筛选后只剩故障症状块；用户读到自己描述的症状，没有 CORS 原因及处理方式。

分类：post_rrf_policy, insufficient_answer_context

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | troubleshooting:44 / CORS blocks the wallet | -12.914624 | 9 | 0.588186 | 5 | 0.029877 / 6 |
| 2 | troubleshooting:45 / CORS blocks the wallet | -13.312188 | 7 | 0.172411 | 283 | 0.014925 / 11 |
| 3 | troubleshooting:46 / CORS blocks the wallet | — | — | 0.271858 | 107 | — / — |
| 4 | troubleshooting:47 / CORS blocks the wallet | -12.250607 | 12 | 0.334965 | 57 | 0.013889 / 15 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | troubleshooting:48 / Cloudflare or WAF challenge | -18.815363 | 3 | 0.680773 | 1 | 0.032266 / 2 |
| 2 | troubleshooting:53 / Auth proxy or `iconUrl` 404 | -25.847025 | 1 | 0.620173 | 2 | 0.032522 / 1 |

原始 RRF Top-5: troubleshooting:53, troubleshooting:48, troubleshooting:43, troubleshooting:28, troubleshooting:58

## T13 — false_no_answer

TON Connect 返回的哪个链编号是主网，哪个是测试网？

Expected: `grounded`; returned: `insufficient_evidence`; answer: **abstain**.

验收事实：Mainnet -239, testnet -3.

判定：中译英所需 faq:1 已进入结果第 3，语义 0.540；首位却是 Catchain 协议图引导句。正确证据存在但状态仍 insufficient。

分类：cross_language, answer_status_threshold, post_rrf_policy

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:1 / How do I tell if the user is on mainnet or testnet? | -4.324363 | 41 | 0.540207 | 3 | 0.015873 / 6 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | catchain:5 / 1   Overview | -2.766082 | 62 | 0.543963 | 1 | 0.016393 / 4 |
| 2 | connect:1 / What TON Connect is | -7.974738 | 8 | 0.542144 | 2 | 0.030835 / 1 |
| 3 | faq:1 / How do I tell if the user is on mainnet or testnet? | -4.324363 | 41 | 0.540207 | 3 | 0.015873 / 6 |
| 4 | catchain:11 / 1   Overview | -2.654143 | 70 | 0.522665 | 4 | 0.015625 / 8 |
| 5 | catchain:4 / 1   Overview | -2.449910 | 76 | 0.516044 | 5 | 0.015385 / 10 |

原始 RRF Top-5: connect:1, troubleshooting:59, faq:12, catchain:5, connect:6

## T14 — answer_selection

我在钱包里换了账户，为什么连接的网站还是旧账户？要怎么切换？

Expected: `grounded`; returned: `grounded`; answer: **partial**.

验收事实：dApp keeps account chosen at connect; disconnect/reconnect in dApp.

判定：中文召回账户固定原因，邻块有 disconnect/reconnect；answer 不使用扩展内容，未给出切换步骤。

分类：cross_language, insufficient_answer_context

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:13 / Why is there no `accountChanged` event? | — | — | 0.602011 | 1 | 0.016393 / 1 |
| 2 | faq:14 / Why is there no `accountChanged` event? | — | — | 0.446822 | 8 | 0.014706 / 8 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:13 / Why is there no `accountChanged` event? | — | — | 0.602011 | 1 | 0.016393 / 1 |

原始 RRF Top-5: faq:13, troubleshooting:11, faq:11, highload3:2, troubleshooting:18

## T15 — retrieval_miss

TON 虚拟机目前实现了哪些代码页？

Expected: `grounded`; returned: `insufficient_evidence`; answer: **abstain**.

验收事实：Only codepage 0.

判定：英文正文 Only codepage 0 is implemented 缺失 TVM 上级 heading；中文语义排名 143，词法无命中，候选池没有正确块。

分类：cross_language, heading_context_loss

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | whitepaper_comments:6 / 5.1. Codepages and interoperability of different TVM versions | — | — | 0.294300 | 143 | — / — |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | addresses:17 / Flag definitions | -2.678228 | 55 | 0.549543 | 1 | 0.016393 / 4 |
| 2 | highload2:3 / (no section) | — | — | 0.504880 | 2 | 0.016129 / 5 |
| 3 | highload3:1 / (no section) | — | — | 0.498190 | 3 | 0.015873 / 7 |

原始 RRF Top-5: highload2:63, highload3:157, faq:12, addresses:17, highload2:3

## T16 — retrieval_miss

Highload v3 的查询编号里，位索引最大能取多少？能用 1023 吗？

Expected: `grounded`; returned: `grounded`; answer: **wrong**.

验收事实：bit_number range 0-1022; 1023 excluded.

判定：正确 bit_number 限制语义第 49/63、词法第 40/38，未进候选池；返回 query ID 总容量而非位索引上限，数字相关不等于回答具体问题。

分类：cross_language, false_grounded

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload3:47 / How `query_id` is checked | -5.291508 | 40 | 0.373300 | 49 | — / — |
| 2 | highload3:87 / `query_id` (composite structure) | -7.146424 | 38 | 0.355858 | 63 | — / — |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload3:126 / Query ID space limitations | -8.383277 | 22 | 0.721864 | 1 | 0.016393 / 9 |

原始 RRF Top-5: highload3:68, highload3:73, highload2:66, highload2:67, highload3:69

## T17 — post_rrf_policy

能直接从 TON 地址算出用户公钥吗？合约还没部署时能在链上查到吗？

Expected: `grounded`; returned: `grounded`; answer: **wrong**.

验收事实：Cannot extract public key from address; before deployment not available on-chain.

判定：公钥提取限制语义第 8、RRF 第 18，后处理未保留；首位 ton_proof 后端认证虽涉及公钥，却不能证明从地址可提取公钥或未部署查询可行。

分类：cross_language, correct_source_low_rank, false_grounded

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | addresses:27 / Drawbacks | — | — | 0.564385 | 8 | 0.014706 / 18 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:11 / How do I implement backend authentication with TON Connect? | -2.338666 | 70 | 0.654462 | 1 | 0.016393 / 5 |
| 2 | connect:2 / What TON Connect is | — | — | 0.614869 | 2 | 0.016129 / 7 |
| 3 | highload2:21 / `public_key` (256 bits) | — | — | 0.594302 | 3 | 0.015873 / 8 |
| 4 | highload3:17 / `public_key` (256 bits) | — | — | 0.587138 | 4 | 0.015625 / 10 |

原始 RRF Top-5: connect:1, connect:16, connect:4, faq:12, faq:11

## T18 — post_rrf_policy

¿Qué identificadores de cadena devuelve TON Connect para la red principal y la red de pruebas?

Expected: `grounded`; returned: `grounded`; answer: **wrong**.

验收事实：Mainnet -239, testnet -3.

判定：西语链编号问题正确 FAQ 语义第 13、RRF 第 24；词法噪声和 relevance 策略把 legacy Catchain 网络协议排在前面。不是官方身份错，而是选错问题对应的来源。

分类：cross_language, correct_source_low_rank, wrong_source, false_grounded

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:1 / How do I tell if the user is on mainnet or testnet? | -4.324363 | 44 | 0.491250 | 13 | 0.013699 / 24 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | catchain:4 / 1   Overview | -2.449910 | 79 | 0.561147 | 1 | 0.016393 / 4 |
| 2 | faq:15 / Why is there no `networkChanged` event? | — | — | 0.550529 | 2 | 0.016129 / 6 |
| 3 | catchain:5 / 1   Overview | -2.766082 | 65 | 0.549755 | 3 | 0.015873 / 7 |
| 4 | catchain:11 / 1   Overview | -2.654143 | 73 | 0.547173 | 4 | 0.015625 / 9 |
| 5 | catchain:75 / 3   Block Consensus Protocol | -3.035821 | 56 | 0.541025 | 5 | 0.015385 / 11 |

原始 RRF Top-5: troubleshooting:59, connect:1, faq:12, catchain:4, connect:6

## T19 — answer_selection

Cambié de cuenta en mi monedero, pero la aplicación sigue usando la anterior. ¿Cómo cambio la cuenta conectada?

Expected: `grounded`; returned: `grounded`; answer: **wrong**.

验收事实：Account fixed at connect; disconnect and reconnect inside app.

判定：断开重连步骤 RRF 第 2且在最终第 2；answer 复制首位的 UNKNOWN_APP 会话撤销原因。证据已到手，不是需要更多召回。

分类：cross_language, post_rrf_policy, false_grounded

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:13 / Why is there no `accountChanged` event? | — | — | 0.519965 | 4 | 0.015625 / 4 |
| 2 | faq:14 / Why is there no `accountChanged` event? | — | — | 0.552629 | 2 | 0.016129 / 2 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | troubleshooting:23 / `UNKNOWN_APP_ERROR` — code 100 | — | — | 0.585202 | 1 | 0.016393 / 1 |
| 2 | faq:14 / Why is there no `accountChanged` event? | — | — | 0.552629 | 2 | 0.016129 / 2 |
| 3 | troubleshooting:21 / `UNKNOWN_APP_ERROR` — code 100 | — | — | 0.541980 | 3 | 0.015873 / 3 |
| 4 | faq:13 / Why is there no `accountChanged` event? | — | — | 0.519965 | 4 | 0.015625 / 4 |
| 5 | troubleshooting:18 / `METHOD_NOT_SUPPORTED` — code 400 | — | — | 0.515206 | 5 | 0.015385 / 5 |

原始 RRF Top-5: troubleshooting:23, faq:14, troubleshooting:21, faq:13, troubleshooting:18

## T20 — answer_selection

¿Qué algoritmo de suma de comprobación usa una dirección amigable de TON y cuántos bytes ocupa?

Expected: `grounded`; returned: `grounded`; answer: **wrong**.

验收事实：CRC16-CCITT, 2 bytes.

判定：正确 CRC16 段原始 RRF 第 1、最终第 3；答案只给 Luhn 类比，缺少算法及 2 bytes。

分类：cross_language, post_rrf_policy, false_grounded

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | addresses:15 / Structure | -7.832803 | 2 | 0.538683 | 3 | 0.032002 / 1 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | addresses:16 / Structure | — | — | 0.566966 | 1 | 0.016393 / 3 |
| 2 | catchain:94 / 3.1.6. The state update algorithm | — | — | 0.563167 | 2 | 0.016129 / 4 |
| 3 | addresses:15 / Structure | -7.832803 | 2 | 0.538683 | 3 | 0.032002 / 1 |
| 4 | catchain:95 / 3.1.6. The state update algorithm | — | — | 0.505481 | 4 | 0.015625 / 7 |
| 5 | addresses:14 / Structure | -8.047593 | 1 | 0.503277 | 5 | 0.031778 / 2 |

原始 RRF Top-5: addresses:15, addresses:14, addresses:16, catchain:94, whitepaper_comments:27

## T21 — success

Si falla el puente de TON Connect, ¿cada cuánto reintenta el SDK la conexión SSE y el envío de mensajes?

Expected: `grounded`; returned: `grounded`; answer: **complete**.

验收事实：SSE reconnect 2 seconds; POST /message 5 seconds.

判定：西语正确召回英文操作说明，包含 SSE 2 秒、POST 5 秒。输出仍为英文摘录，本指标不测回答语言本地化。

分类：cross_language

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | troubleshooting:12 / Bridge unreachable or timeout | -15.082703 | 1 | 0.716582 | 1 | 0.032787 / 1 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | troubleshooting:12 / Bridge unreachable or timeout | -15.082703 | 1 | 0.716582 | 1 | 0.032787 / 1 |

原始 RRF Top-5: troubleshooting:12, connect:13, troubleshooting:11, connect:9, faq:6

## T22 — answer_selection

¿El formato raw y el formato amigable de TON representan cuentas diferentes o la misma dirección?

Expected: `grounded`; returned: `grounded`; answer: **partial**.

验收事实：Equivalent representations of exactly one address, not different accounts.

判定：等价地址说明在最终第 2及 context；答案仅定义 raw 格式，没有回答是否同一个地址。

分类：cross_language, insufficient_answer_context

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | addresses:3 / (no section) | — | — | 0.539593 | 2 | 0.016129 / 8 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | addresses:4 / Raw format | -7.741224 | 1 | 0.593753 | 1 | 0.032787 / 1 |
| 2 | addresses:3 / (no section) | — | — | 0.539593 | 2 | 0.016129 / 8 |

原始 RRF Top-5: addresses:4, addresses:5, addresses:2, troubleshooting:16, addresses:28

## T23 — answer_selection

What can cause a TON Connect bridge timeout, and how often does the SDK retry SSE and POST /message?

Expected: `grounded`; returned: `grounded`; answer: **partial**.

验收事实：At least one listed cause (down/rate limit/blocked network/background SSE) plus 2-second SSE and 5-second POST retries.

判定：答案包含 2/5 秒重试，但未列出预期的具体超时原因；相邻 cause list 已在 context。严格完整性失败，不代表重试数值错误。

分类：insufficient_answer_context

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | troubleshooting:11 / Bridge unreachable or timeout | -14.490593 | 6 | 0.579502 | 3 | 0.031025 / 2 |
| 2 | troubleshooting:12 / Bridge unreachable or timeout | -26.942344 | 1 | 0.739732 | 1 | 0.032787 / 1 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | troubleshooting:12 / Bridge unreachable or timeout | -26.942344 | 1 | 0.739732 | 1 | 0.032787 / 1 |

原始 RRF Top-5: troubleshooting:12, troubleshooting:11, faq:6, highload3:127, connect:16

## T24 — answer_selection

How many bytes is a user-friendly TON address in total, and how are those bytes divided between flags, workchain, account and checksum?

Expected: `grounded`; returned: `grounded`; answer: **partial**.

验收事实：36 total; 1 flags, 1 workchain, 32 account, 2 checksum.

判定：36 bytes 引导句与 1/1/32/2 列表被分开，两块均命中且在扩展内；answer 只输出引导句，列表全部漏掉。扩大 chunk 不是唯一或优先答案。

分类：chunk_boundary, insufficient_answer_context

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | addresses:14 / Structure | -25.210918 | 2 | 0.693791 | 1 | 0.032522 / 2 |
| 2 | addresses:15 / Structure | -26.460982 | 1 | 0.673992 | 2 | 0.032522 / 1 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | addresses:14 / Structure | -25.210918 | 2 | 0.693791 | 1 | 0.032522 / 2 |
| 2 | addresses:15 / Structure | -26.460982 | 1 | 0.673992 | 2 | 0.032522 / 1 |

原始 RRF Top-5: addresses:15, addresses:14, addresses:17, addresses:12, shards:6

## T25 — false_no_answer

If a shard with prefix p splits, what are its children's prefixes, and what prefix do they have after merging back?

Expected: `grounded`; returned: `insufficient_evidence`; answer: **abstain**.

验收事实：Split p into p0 and p1; merge both back to p.

判定：拆分/合并两块原始及最终排名 1/2，完整上下文已返回；仅因相似度/词覆盖阈值，仍判 insufficient。

分类：answer_status_threshold

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | shards:10 / Sharding process | -25.227507 | 1 | 0.491813 | 1 | 0.032787 / 1 |
| 2 | shards:11 / Sharding process | -19.022241 | 4 | 0.481506 | 2 | 0.031754 / 2 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | shards:10 / Sharding process | -25.227507 | 1 | 0.491813 | 1 | 0.032787 / 1 |
| 2 | shards:11 / Sharding process | -19.022241 | 4 | 0.481506 | 2 | 0.031754 / 2 |

原始 RRF Top-5: shards:10, shards:11, shards:8, shards:9, shards:7

## T26 — success

In the legacy Catchain protocol, how is the catchain identifier derived from the genesis message?

Expected: `grounded`; returned: `grounded`; answer: **complete**.

验收事实：SHA-256 hash of genesis data structure; not ID of one participant.

判定：legacy Catchain genesis 数据结构的 SHA-256 标识说明完整召回且直接回答。

分类：success

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | catchain:23 / 2.3. The genesis block and the identifier of a catchain | -13.684818 | 3 | 0.783719 | 1 | 0.032266 / 1 |
| 2 | catchain:25 / 2.3.2. List of nodes participating in a catchain | -9.839931 | 10 | 0.570519 | 25 | 0.014286 / 19 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | catchain:23 / 2.3. The genesis block and the identifier of a catchain | -13.684818 | 3 | 0.783719 | 1 | 0.032266 / 1 |

原始 RRF Top-5: catchain:23, catchain:24, catchain:59, catchain:80, catchain:78

## T27 — false_grounded

Exactly how much gas in total does Highload v3 consume for a batch of 254 messages?

Expected: `insufficient_evidence`; returned: `grounded`; answer: **wrong**.

验收事实：Gas table says TBD; cannot supply a precise total from these sources.

判定：gas 精确值的表格是 TBD；系统把 Gas costs vary 的引导句判 grounded。没有捏造数值，但把不能证明精确值的资料误标为可回答。

分类：answer_status_threshold

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload3:135 / Gas consumption | -15.366594 | 7 | 0.272751 | 174 | 0.014925 / 15 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload3:134 / Gas consumption | -7.640026 | 46 | 0.633758 | 1 | 0.016393 / 8 |
| 2 | highload3:113 / Message sending flow | -10.209578 | 13 | 0.599894 | 2 | 0.029828 / 3 |
| 3 | highload2:54 / Gas limit for cleanup | -7.194606 | 48 | 0.571247 | 3 | 0.015873 / 10 |

原始 RRF Top-5: highload3:112, highload3:6, highload3:113, highload2:20, highload3:69

## T28 — success

What compensation does the TON Connect bridge SLA guarantee after one hour of downtime?

Expected: `insufficient_evidence`; returned: `insufficient_evidence`; answer: **complete**.

验收事实：Bridge troubleshooting exists; no SLA or compensation evidence in corpus.

判定：有 bridge 技术说明但无赔偿承诺，正确 insufficient。

分类：abstention

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | troubleshooting:9 / Bridge unreachable or timeout | — | — | 0.202486 | 101 | — / — |
| 2 | troubleshooting:11 / Bridge unreachable or timeout | -10.300366 | 6 | 0.364695 | 5 | 0.030536 / 2 |
| 3 | troubleshooting:12 / Bridge unreachable or timeout | -11.518995 | 5 | 0.392060 | 2 | 0.031514 / 1 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | troubleshooting:12 / Bridge unreachable or timeout | -11.518995 | 5 | 0.392060 | 2 | 0.031514 / 1 |
| 2 | connect:6 / Build a dApp | -12.681856 | 4 | 0.014789 | 539 | 0.015625 / 8 |
| 3 | catchain:130 / 3.4.4. Protocol parameters | -2.817820 | 130 | 0.385971 | 4 | 0.015625 / 9 |
| 4 | troubleshooting:11 / Bridge unreachable or timeout | -10.300366 | 6 | 0.364695 | 5 | 0.030536 / 2 |

原始 RRF Top-5: troubleshooting:12, troubleshooting:11, faq:6, highload3:49, connect:16

## T29 — success

My TON Connect transfer is stuck. Can these docs prove that my particular transaction failed because of a wrong network?

Expected: `insufficient_evidence`; returned: `insufficient_evidence`; answer: **complete**.

验收事实：Generic causes do not diagnose this transaction; missing transaction/network evidence.

判定：通用排错资料不能证明特定交易失败原因，正确 insufficient。

分类：abstention

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | troubleshooting:16 / `BAD_REQUEST_ERROR` — code 1 | -8.625845 | 19 | 0.419890 | 14 | 0.026172 / 2 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | faq:2 / How do I tell if the user is on mainnet or testnet? | -4.311003 | 157 | 0.528289 | 1 | 0.016393 / 4 |
| 2 | troubleshooting:38 / Manifest URL is unreachable | -4.058785 | 167 | 0.525595 | 2 | 0.016129 / 6 |
| 3 | troubleshooting:1 / (no section) | -6.276612 | 93 | 0.516080 | 3 | 0.015873 / 8 |
| 4 | troubleshooting:3 / `MANIFEST_NOT_FOUND_ERROR` — code 2 | -7.689495 | 46 | 0.508311 | 4 | 0.015625 / 9 |
| 5 | troubleshooting:11 / Bridge unreachable or timeout | -4.231681 | 160 | 0.498824 | 5 | 0.015385 / 11 |

原始 RRF Top-5: troubleshooting:5, troubleshooting:16, catchain:10, faq:2, catchain:182

## T30 — no_authoritative_status

Which cafe in Oslo sells the cheapest almond croissant on Sunday?

Expected: `no_authoritative_source`; returned: `insufficient_evidence`; answer: **status_wrong_safe_abstain**.

验收事实：No authoritative cafe information in this corpus.

判定：没有咖啡店依据，却因 sells/stablecoins 等泛词命中钱包用途；给出 insufficient 而非 no_authoritative_source。安全拒答但状态语义错误。

分类：lexical_noise

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| — | 无可证明答案的 chunk | — | — | — | — | — |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | wallet_comparison:11 / Retail users | -7.013545 | 1 | 0.060251 | 210 | 0.016393 / 1 |

原始 RRF Top-5: wallet_comparison:11, wallet_comparison:7, catchain:1, faq:0, wallet_comparison:2

## T31 — no_authoritative_status

Who won the 2022 Wimbledon women's singles final?

Expected: `no_authoritative_source`; returned: `insufficient_evidence`; answer: **status_wrong_safe_abstain**.

验收事实：Sports answer absent; do not use outside knowledge.

判定：网球问题误命中钱包代码的 final 等泛词；未提供体育答案，但错误声称有相关官方资料。

分类：lexical_noise

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| — | 无可证明答案的 chunk | — | — | — | — | — |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload3:155 / Protection against `set_code` | -8.252721 | 1 | -0.069782 | 644 | 0.016393 / 1 |
| 2 | highload3:118 / Message sending flow | -6.603694 | 2 | 0.022990 | 375 | 0.016129 / 3 |
| 3 | highload3:20 / `subwallet_id` (32 bits) | -6.278797 | 3 | 0.024941 | 365 | 0.015873 / 5 |
| 4 | highload2:13 / `subwallet_id` (32 bits) | -6.278797 | 4 | 0.024941 | 366 | 0.015625 / 7 |
| 5 | highload3:162 / See also | -5.761981 | 5 | -0.016581 | 544 | 0.015385 / 9 |

原始 RRF Top-5: highload3:155, catchain:1, highload3:118, whitepaper_comments:17, highload3:20

## T32 — temporal_classification

As of January 15, 2024, was setting Highload v3 created_at 30 seconds in the past the official recommendation?

Expected: `no_authoritative_source`; returned: `outdated_only`; answer: **status_wrong_safe_abstain**.

验收事实：No temporally proven source exists in snapshot for 2024. Abstain; future observed material is not evidence that 2024 advice is outdated. Excluded from historical truth accuracy.

判定：所有来源仅有后来的 snapshot availability 代理时间，无法验证 2024。baseline 把未来不可用和过去已过期都归 inactive，再统一输出 outdated_only。它没有拿今天答案肯定 2024，但状态无法区分未来与过期。非真实历史准确率。

分类：historical_validity_unavailable

as_of_time: `2024-01-15T12:00:00Z`

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload3:58 / Timestamp validation | -17.459874 | 1 | 0.442631 | 6 | 0.031545 / 1 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload3:57 / Timestamp validation | -2.382307 | 168 | 0.486397 | 1 | 0.016393 / 7 |
| 2 | highload3:60 / Timestamp validation | -5.366669 | 61 | 0.485819 | 2 | 0.016129 / 9 |
| 3 | highload3:68 / Why internal messages to self? | -9.785548 | 7 | 0.478578 | 3 | 0.030798 / 2 |
| 4 | highload2:58 / Query ID expiration | -3.556391 | 114 | 0.449212 | 4 | 0.015625 / 12 |
| 5 | highload3:93 / `created_at` (64 bits) | -9.253161 | 15 | 0.443090 | 5 | 0.028718 / 3 |

原始 RRF Top-5: highload3:58, highload3:68, highload3:93, highload2:67, highload3:59

## T33 — answer_selection

Does TON Connect give a dApp access to the user's private keys?

Expected: `grounded`; returned: `grounded`; answer: **wrong**.

验收事实：No; encrypted session without touching user keys.

判定：TON Connect 不触碰用户密钥的段落原始 RRF 第 1、最终第 3；answer 变成 Highload 签名验证原理，未回答 dApp 是否能访问私钥。

分类：post_rrf_policy, false_grounded, wrong_source

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | connect:2 / What TON Connect is | -15.720186 | 4 | 0.610895 | 3 | 0.031498 / 1 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | highload3:18 / `public_key` (256 bits) | -5.887499 | 56 | 0.617002 | 1 | 0.016393 / 9 |
| 2 | highload2:22 / `public_key` (256 bits) | -5.887499 | 57 | 0.617002 | 2 | 0.016129 / 10 |
| 3 | connect:2 / What TON Connect is | -15.720186 | 4 | 0.610895 | 3 | 0.031498 / 1 |
| 4 | highload3:22 / `subwallet_id` (32 bits) | -6.540305 | 47 | 0.574260 | 4 | 0.015625 / 11 |
| 5 | connect:1 / What TON Connect is | -7.974738 | 25 | 0.556669 | 5 | 0.015385 / 12 |

原始 RRF Top-5: connect:2, faq:13, faq:14, faq:12, faq:11

## T34 — success

Our treasury should not be movable by just one person. Which wallet type do the docs suggest for shared custody?

Expected: `grounded`; returned: `grounded`; answer: **complete**.

验收事实：Multisig/shared approvals, not single-owner Highload.

判定：正确推荐 Multisig 处理共享保管；答案指明钱包类型，证据直接匹配。

分类：success

### Expected source / section（无答案题为 related-only）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | wallet_comparison:16 / Shared custody | -26.155390 | 1 | 0.568027 | 1 | 0.032787 / 1 |
| 2 | wallet_comparison:18 / Shared custody | -13.763538 | 2 | 0.561992 | 2 | 0.032258 / 2 |

### Actual Top-K（后处理后）

| Rank | Chunk / section | BM25 | Lexical rank | Semantic | Semantic rank | RRF score / rank |
|---:|---|---:|---:|---:|---:|---|
| 1 | wallet_comparison:16 / Shared custody | -26.155390 | 1 | 0.568027 | 1 | 0.032787 / 1 |
| 2 | wallet_comparison:18 / Shared custody | -13.763538 | 2 | 0.561992 | 2 | 0.032258 / 2 |
| 3 | wallet_comparison:1 / (no section) | -2.062583 | 309 | 0.552590 | 3 | 0.015873 / 4 |
| 4 | highload3:22 / `subwallet_id` (32 bits) | -5.292526 | 65 | 0.531179 | 4 | 0.015625 / 6 |

原始 RRF Top-5: wallet_comparison:16, wallet_comparison:18, catchain:115, wallet_comparison:1, faq:4

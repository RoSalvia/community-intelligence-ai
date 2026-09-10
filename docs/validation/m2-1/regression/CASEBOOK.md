# Per-query failure and regression review

Retrieval scores refer to unchanged original query; no rewrite or reranker. Raw source/answer bodies remain in ignored local run artifacts.

## T01 — complete

Which wallet.account.chain values identify mainnet and testnet in TON Connect?

Expected: `faq:1` · grounded

Returned: grounded · Recall@5 1.0

主网/测试网编号映射完整，原成功保留。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| faq:1 | How do I tell if the user is on mainnet or testnet? | -36.33734128732716 | 1 | 0.7352 | 1 | 1 | 0.03278688524590164 |
| faq:2 | How do I tell if the user is on mainnet or testnet? | -17.426199360758027 | 3 | 0.7340 | 2 | 2 | 0.03200204813108039 |
| faq:3 | How do I tell if the user is on mainnet or testnet? | -18.916511883461446 | 2 | 0.6117 | 4 | 3 | 0.031754032258064516 |
| faq:15 | Why is there no `networkChanged` event? | -16.41812022059236 | 4 | 0.5483 | 7 | 4 | 0.03055037313432836 |
| faq:11 | How do I implement backend authentication with TON Connect? | -10.485289643301506 | 11 | 0.5743 | 5 | 5 | 0.02946912242686891 |

Expected evidence diagnostics:

- `faq:1` / How do I tell if the user is on mainnet or testnet?: lexical 1 (BM25 -36.33734128732716), semantic 1 (0.7352), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/faq.mdx).

## T02 — partial

Where does a TON Connect dApp read the maximum number of messages allowed in a transaction batch?

Expected: `faq:16` · grounded

Returned: grounded · Recall@5 1.0

maxMessages、SendTransaction、wallet.device.features 已完整回答；严格原 rubric 额外要求的大批次拆分建议未输出。不是虚构事实。

Taxonomy: strict_rubric_omission

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| faq:16 | How big can a transaction batch be? | -19.561372684264427 | 1 | 0.5350 | 5 | 1 | 0.03177805800756621 |
| wallet_comparison:24 | Payment gateways | -15.588896714676958 | 5 | 0.5966 | 1 | 2 | 0.03177805800756621 |
| highload3:156 | Protection against `set_code` | -16.330956903578336 | 3 | 0.4883 | 8 | 3 | 0.03057889822595705 |
| connect:2 | What TON Connect is | -18.402048959213065 | 2 | 0.3668 | 125 | 4 | 0.016129032258064516 |
| highload2:47 | `messages` (HashmapE 16) | -6.5048183987822386 | 46 | 0.5471 | 2 | 5 | 0.016129032258064516 |

Expected evidence diagnostics:

- `faq:16` / How big can a transaction batch be?: lexical 1 (BM25 -19.561372684264427), semantic 5 (0.5350), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/faq.mdx).

## T03 — partial

Which checksum algorithm protects a user-friendly TON address, and how many bytes does the checksum occupy?

Expected: `addresses:15` · grounded

Returned: grounded · Recall@5 1.0

CRC16-CCITT 与 2 bytes 正确；原 rubric 还要求校验前 34 bytes，回答未包含。保留严格评分，不改 rubric。

Taxonomy: strict_rubric_omission

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| addresses:16 | Structure | -25.440262421466905 | 1 | 0.5826 | 2 | 1 | 0.03252247488101534 |
| addresses:15 | Structure | -21.86444408559481 | 3 | 0.6356 | 1 | 2 | 0.032266458495966696 |
| addresses:14 | Structure | -22.422788990599155 | 2 | 0.4326 | 43 | 3 | 0.016129032258064516 |
| highload3:17 | `public_key` (256 bits) | None | None | 0.5718 | 3 | 4 | 0.015873015873015872 |
| addresses:28 | Summary | -20.203228503125526 | 4 | 0.3771 | 126 | 5 | 0.015625 |

Expected evidence diagnostics:

- `addresses:15` / Structure: lexical 3 (BM25 -21.86444408559481), semantic 1 (0.6356), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/addresses/formats.mdx).

## T04 — complete

Why can a Highload v3 batch send only 254 outgoing messages rather than 255?

Expected: `highload3:124, highload3:156` · grounded

Returned: grounded · Recall@5 1.0

set_code 保护占用一个 action slot，254/255 的原因已完整消费多条证据。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| highload3:112 | `message_to_send` (reference cell) | -26.56961024429963 | 2 | 0.5346 | 4 | 1 | 0.031754032258064516 |
| highload3:156 | Protection against `set_code` | -25.927461441292934 | 3 | 0.4929 | 7 | 2 | 0.030798389007344232 |
| highload2:47 | `messages` (HashmapE 16) | -14.425463150870582 | 10 | 0.5383 | 3 | 3 | 0.030158730158730156 |
| highload3:124 | Single message per external | -29.239012319911097 | 1 | 0.4455 | 20 | 4 | 0.02889344262295082 |
| highload3:141 | Gas consumption | -10.033015555427891 | 20 | 0.5279 | 5 | 5 | 0.027884615384615386 |

Expected evidence diagnostics:

- `highload3:124` / Single message per external: lexical 1 (BM25 -29.239012319911097), semantic 20 (0.4455), RRF 4; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/highload/v3/specification.mdx).
- `highload3:156` / Protection against `set_code`: lexical 3 (BM25 -25.927461441292934), semantic 7 (0.4929), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/highload/v3/specification.mdx).

## T05 — complete

Which TVM codepage is currently implemented?

Expected: `whitepaper_comments:6` · grounded

Returned: grounded · Recall@5 1.0

明确只有 codepage 0，不再拿未实现的 -1/-2 作答案。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| whitepaper_comments:6 | 5.1. Codepages and interoperability of different TVM versions | -23.283775500949716 | 1 | 0.7291 | 1 | 1 | 0.03278688524590164 |
| whitepaper_comments:9 | B.2. Step function of TVM | -21.20225343832065 | 2 | 0.7178 | 2 | 2 | 0.03225806451612903 |
| whitepaper_comments:8 | A. Instructions and opcodes | -8.09844425177504 | 4 | 0.6308 | 3 | 3 | 0.03149801587301587 |
| whitepaper_comments:3 | 1.3.2. List of control registers | -7.803275882793884 | 6 | 0.5288 | 4 | 4 | 0.030776515151515152 |
| whitepaper_comments:7 | A. Instructions and opcodes | -7.87077479512432 | 5 | 0.4539 | 5 | 5 | 0.03076923076923077 |

Expected evidence diagnostics:

- `whitepaper_comments:6` / 5.1. Codepages and interoperability of different TVM versions: lexical 1 (BM25 -23.283775500949716), semantic 1 (0.7291), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/whitepapers/comments.mdx).

## T06 — complete

In the legacy Catchain BCP proof, what fraction of processes is assumed to be Byzantine?

Expected: `catchain:162, catchain:161, catchain:14` · grounded

Returned: grounded · Recall@5 0.6666666666666666

Catchain BCP proof 范围下严格小于 1/3；未冒充当前部署共识。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| catchain:162 | 3.5.1. Fundamental assumption | -19.95486622094349 | 1 | 0.6913 | 1 | 1 | 0.03278688524590164 |
| catchain:161 | 3.5. Validity of BCP | -16.0173875109708 | 2 | 0.6113 | 3 | 2 | 0.03200204813108039 |
| catchain:164 | 3.5.3. Useful invariants | -9.485831172942252 | 8 | 0.6215 | 2 | 3 | 0.030834914611005692 |
| catchain:163 | 3.5.2. Weighted BCP | -10.440791207484907 | 6 | 0.5927 | 6 | 4 | 0.030303030303030304 |
| catchain:189 | 3.5.9. The protocol terminates under these assumptions | -9.70604681529105 | 7 | 0.5576 | 18 | 5 | 0.027745885954841176 |

Expected evidence diagnostics:

- `catchain:14` / 1   Overview: lexical 93 (BM25 -3.84103223354386), semantic 22 (0.5540), RRF None; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/whitepapers/catchain.mdx).
- `catchain:161` / 3.5. Validity of BCP: lexical 2 (BM25 -16.0173875109708), semantic 3 (0.6113), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/whitepapers/catchain.mdx).
- `catchain:162` / 3.5.1. Fundamental assumption: lexical 1 (BM25 -19.95486622094349), semantic 1 (0.6913), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/whitepapers/catchain.mdx).

## T07 — abstain

I selected another account inside my wallet. How do I make my connected dApp use that account instead?

Expected: `faq:14` · grounded

Returned: insufficient_evidence · Recall@5 1.0

步骤证据已排第一且完整进入 context；模型额外分解了原因要求，至少一条生成引用校验失败，答案被降级。拒答是安全保护，但用户任务仍未完成。失败引用原始内容本轮未保留，不能断言是错 ID 还是非逐字引文。

Taxonomy: citation_generation_failure, false_no_answer

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| faq:14 | Why is there no `accountChanged` event? | -13.283511660816037 | 2 | 0.5804 | 2 | 1 | 0.03225806451612903 |
| faq:13 | Why is there no `accountChanged` event? | -12.619185974035709 | 4 | 0.6130 | 1 | 2 | 0.032018442622950824 |
| faq:8 | How do I add my wallet to the list? | -12.16294454135319 | 6 | 0.4574 | 4 | 3 | 0.030776515151515152 |
| connect:2 | What TON Connect is | -11.908007602508969 | 7 | 0.4074 | 11 | 4 | 0.02900988017658188 |
| faq:7 | How do I make my own bridge? | -11.61107305790564 | 9 | 0.3936 | 17 | 5 | 0.027479766610201392 |

Expected evidence diagnostics:

- `faq:14` / Why is there no `accountChanged` event?: lexical 2 (BM25 -13.283511660816037), semantic 2 (0.5804), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/faq.mdx).

## T08 — complete

Must an ordinary app developer deploy their own TON Connect bridge server?

Expected: `faq:4` · grounded

Returned: grounded · Recall@5 1.0

普通 dApp 无需自建；钱包方 bridge 与 wallets-list 说明完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| faq:4 | How do I make my own bridge? | -23.22955827957168 | 1 | 0.5892 | 1 | 1 | 0.03278688524590164 |
| faq:7 | How do I make my own bridge? | -17.59514480475275 | 4 | 0.5812 | 2 | 2 | 0.031754032258064516 |
| faq:6 | How do I make my own bridge? | -18.26174860510354 | 3 | 0.5621 | 3 | 3 | 0.031746031746031744 |
| faq:5 | How do I make my own bridge? | -18.451008030517087 | 2 | 0.4738 | 8 | 4 | 0.030834914611005692 |
| connect:16 | See also | -12.021780204916714 | 9 | 0.4723 | 9 | 5 | 0.028985507246376812 |

Expected evidence diagnostics:

- `faq:4` / How do I make my own bridge?: lexical 1 (BM25 -23.22955827957168), semantic 1 (0.5892), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/faq.mdx).

## T09 — complete

Is Highload Wallet v2 recommended for a new deployment, or has it been replaced?

Expected: `highload2:1, highload2:6` · grounded

Returned: grounded · Recall@5 1.0

明确 v2 弃用，新部署用 v3。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| highload2:1 | — | -15.237081009338159 | 1 | 0.6833 | 1 | 1 | 0.03278688524590164 |
| highload2:67 | See also | -11.690883574398725 | 7 | 0.6574 | 2 | 2 | 0.031054405392392875 |
| highload2:6 | What is Highload Wallet v2? | -12.98094146670038 | 3 | 0.5381 | 13 | 3 | 0.029571646010002173 |
| highload2:56 | Gas limit for cleanup | -12.261945637194591 | 6 | 0.5576 | 10 | 4 | 0.029437229437229435 |
| highload2:66 | Implementation | -8.601884667472417 | 15 | 0.6222 | 4 | 5 | 0.028958333333333336 |

Expected evidence diagnostics:

- `highload2:1` / None: lexical 1 (BM25 -15.237081009338159), semantic 1 (0.6833), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/highload/v2/specification.mdx).
- `highload2:6` / What is Highload Wallet v2?: lexical 3 (BM25 -12.98094146670038), semantic 13 (0.5381), RRF 3; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/highload/v2/specification.mdx).

## T10 — complete

hey my ton wallet says USER_REJECTS_ERROR lol... is our app broken or did the user just bail? what should we show them?

Expected: `troubleshooting:13, troubleshooting:14` · grounded

Returned: grounded · Recall@5 0.5

取消/关闭钱包、软提示与重试、不作为系统错误均已覆盖。低位命中与邻块一起被消费。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| troubleshooting:23 | `UNKNOWN_APP_ERROR` — code 100 | -9.139778819876932 | 15 | 0.5843 | 1 | 1 | 0.029726775956284153 |
| troubleshooting:44 | CORS blocks the wallet | -10.994317953960671 | 11 | 0.4828 | 4 | 2 | 0.029709507042253523 |
| troubleshooting:21 | `UNKNOWN_APP_ERROR` — code 100 | -9.074644505670646 | 17 | 0.5012 | 2 | 3 | 0.029116045245077504 |
| addresses:15 | Structure | -8.942926274092958 | 20 | 0.4598 | 10 | 4 | 0.026785714285714288 |
| troubleshooting:14 | `USER_REJECTS_ERROR` — code 300 | -26.411280872100583 | 1 | 0.3678 | 132 | 5 | 0.01639344262295082 |

Expected evidence diagnostics:

- `troubleshooting:13` / `USER_REJECTS_ERROR` — code 300: lexical 3 (BM25 -15.262356599951644), semantic 78 (0.3991), RRF 7; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).
- `troubleshooting:14` / `USER_REJECTS_ERROR` — code 300: lexical 1 (BM25 -26.411280872100583), semantic 132 (0.3678), RRF 5; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).

## T11 — complete

highload v3 keeps yelling 35 at me even tho i just made the tx!! my laptop clock is right, what time should i put?

Expected: `highload3:57, highload3:58, highload3:60` · grounded

Returned: grounded · Recall@5 0.6666666666666666

链上 now 与电脑时间不同，created_at 提前 30–60 秒，原因与做法完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| highload3:57 | Timestamp validation | -12.566197351529883 | 1 | 0.5848 | 1 | 1 | 0.03278688524590164 |
| highload3:55 | Timestamp validation | -10.512501101840952 | 6 | 0.4725 | 5 | 2 | 0.030536130536130537 |
| highload3:60 | Timestamp validation | -11.81183284694827 | 4 | 0.4246 | 10 | 3 | 0.029910714285714284 |
| highload3:97 | `created_at` (64 bits) | -10.196065085768872 | 10 | 0.4436 | 8 | 4 | 0.028991596638655463 |
| highload3:130 | Timeout constraints | -9.114907279885465 | 14 | 0.4549 | 7 | 5 | 0.028438886647841874 |

Expected evidence diagnostics:

- `highload3:57` / Timestamp validation: lexical 1 (BM25 -12.566197351529883), semantic 1 (0.5848), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/highload/v3/specification.mdx).
- `highload3:58` / Timestamp validation: lexical 42 (BM25 -6.204624699340043), semantic 4 (0.4851), RRF 12; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/highload/v3/specification.mdx).
- `highload3:60` / Timestamp validation: lexical 4 (BM25 -11.81183284694827), semantic 10 (0.4246), RRF 3; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/highload/v3/specification.mdx).

## T12 — partial

manifest loads fine on my own site but wallet still can't grab it... cors thing??

Expected: `troubleshooting:44, troubleshooting:45, troubleshooting:46, troubleshooting:47` · grounded

Returned: grounded · Recall@5 0.0

跨来源请求与开放 CORS 已说明；未明确 manifest 本身须无需认证，仍缺原 rubric 一项。Top-K 未直接命中 gold，邻块仅覆盖一部分；附带其他可能原因，没有断言已诊断用户环境。

Taxonomy: correct_candidate_low_rank, strict_rubric_omission, incomplete_selected_context

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| troubleshooting:43 | CORS blocks the wallet | -20.97612223783754 | 2 | 0.6323 | 2 | 1 | 0.03225806451612903 |
| troubleshooting:48 | Cloudflare or WAF challenge | -19.46241951812218 | 3 | 0.6150 | 3 | 2 | 0.031746031746031744 |
| troubleshooting:53 | Auth proxy or `iconUrl` 404 | -25.94199161877296 | 1 | 0.5772 | 6 | 3 | 0.031544957774465976 |
| troubleshooting:28 | Manifest 404 and CORS | -15.332780005236673 | 6 | 0.6126 | 4 | 4 | 0.030776515151515152 |
| troubleshooting:58 | Caching pitfalls | -14.752120873108854 | 7 | 0.5998 | 5 | 5 | 0.030309988518943745 |

Expected evidence diagnostics:

- `troubleshooting:44` / CORS blocks the wallet: lexical 23 (BM25 -9.538763128706991), semantic 1 (0.6648), RRF 14; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).
- `troubleshooting:45` / CORS blocks the wallet: lexical 16 (BM25 -10.421604789006775), semantic 14 (0.5418), RRF 12; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).
- `troubleshooting:46` / CORS blocks the wallet: lexical 19 (BM25 -9.80833978074005), semantic 10 (0.5524), RRF 11; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).
- `troubleshooting:47` / CORS blocks the wallet: lexical 8 (BM25 -14.338732294520014), semantic 13 (0.5437), RRF 8; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).

## T13 — abstain

TON Connect 返回的哪个链编号是主网，哪个是测试网？

Expected: `faq:1` · grounded

Returned: no_authoritative_source · Recall@5 0.0

正确 FAQ 语义第 2、RRF 第 7，未进入 Top-5/context；不是整个候选集没找到，答案层没有猜链编号。

Taxonomy: correct_candidate_low_rank, cross_language_ranking, false_no_answer, incomplete_selected_context

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| connect:1 | What TON Connect is | -5.582845167018277 | 2 | 0.5805 | 3 | 1 | 0.03200204813108039 |
| faq:12 | How do I implement backend authentication with TON Connect? | -5.689752353629089 | 1 | 0.4842 | 12 | 2 | 0.03028233151183971 |
| troubleshooting:59 | See also | -5.462491045695388 | 7 | 0.5286 | 9 | 3 | 0.029418126757516764 |
| connect:13 | API reference | -5.388337034017059 | 8 | 0.4658 | 18 | 4 | 0.027526395173453996 |
| connect:14 | API reference | -5.1472349378287365 | 18 | 0.4989 | 11 | 5 | 0.02690501986276634 |

Expected evidence diagnostics:

- `faq:1` / How do I tell if the user is on mainnet or testnet?: lexical 38 (BM25 -4.863914905968345), semantic 2 (0.6066), RRF 7; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/faq.mdx).

## T14 — complete

我在钱包里换了账户，为什么连接的网站还是旧账户？要怎么切换？

Expected: `faq:13, faq:14` · grounded

Returned: grounded · Recall@5 1.0

为何账户固定及 dApp 内断开重连均完整，中文输出。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| faq:13 | Why is there no `accountChanged` event? | None | None | 0.6676 | 1 | 1 | 0.01639344262295082 |
| faq:14 | Why is there no `accountChanged` event? | None | None | 0.5848 | 2 | 2 | 0.016129032258064516 |
| highload3:115 | Message sending flow | None | None | 0.4668 | 3 | 3 | 0.015873015873015872 |
| highload2:12 | Storage structure | None | None | 0.4577 | 4 | 4 | 0.015625 |
| wallet_comparison:29 | Payment gateways | None | None | 0.4572 | 5 | 5 | 0.015384615384615385 |

Expected evidence diagnostics:

- `faq:13` / Why is there no `accountChanged` event?: lexical None (BM25 None), semantic 1 (0.6676), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/faq.mdx).
- `faq:14` / Why is there no `accountChanged` event?: lexical None (BM25 None), semantic 2 (0.5848), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/faq.mdx).

## T15 — abstain

TON 虚拟机目前实现了哪些代码页？

Expected: `whitepaper_comments:6` · grounded

Returned: no_authoritative_source · Recall@5 0.0

正确 codepage 块语义第 3、RRF 第 8；结构表示已修复旧候选 miss，但最终排名仍不足。

Taxonomy: correct_candidate_low_rank, cross_language_ranking, false_no_answer, incomplete_selected_context

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| highload2:63 | Implementation | -2.135858748821974 | 6 | 0.4747 | 9 | 1 | 0.02964426877470356 |
| whitepaper_comments:35 | 5. TON Payments | -2.08926670560054 | 12 | 0.4513 | 10 | 2 | 0.02817460317460317 |
| faq:12 | How do I implement backend authentication with TON Connect? | -2.23801222346775 | 1 | 0.2776 | 385 | 3 | 0.01639344262295082 |
| whitepaper_comments:27 | 2.1.20. TON Virtual Machine | -1.9878324124810836 | 26 | 0.5601 | 1 | 4 | 0.01639344262295082 |
| connect:1 | What TON Connect is | -2.215608736996085 | 2 | 0.3432 | 165 | 5 | 0.016129032258064516 |

Expected evidence diagnostics:

- `whitepaper_comments:6` / 5.1. Codepages and interoperability of different TVM versions: lexical 52 (BM25 -1.8471482828975738), semantic 3 (0.5545), RRF 8; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/whitepapers/comments.mdx).

## T16 — complete

Highload v3 的查询编号里，位索引最大能取多少？能用 1023 吗？

Expected: `highload3:87, highload3:47` · grounded

Returned: grounded · Recall@5 0.5

范围 0–1022 与排除 1023 均明确，中文问题检索英文资料成功。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| highload3:88 | `query_id` (composite structure) | -10.156670682802368 | 2 | 0.6075 | 2 | 1 | 0.03225806451612903 |
| highload3:87 | `query_id` (composite structure) | -9.348337900038977 | 3 | 0.4881 | 11 | 2 | 0.029957522915269395 |
| highload3:142 | Get methods | -3.004693958016256 | 18 | 0.4779 | 19 | 3 | 0.025478740668614087 |
| highload3:9 | Query ID structure | -10.272528829767468 | 1 | 0.4757 | 21 | 4 | 0.01639344262295082 |
| highload3:126 | Query ID space limitations | -2.833791895806794 | 40 | 0.6265 | 1 | 5 | 0.01639344262295082 |

Expected evidence diagnostics:

- `highload3:47` / How `query_id` is checked: lexical 5 (BM25 -7.50460783945246), semantic 53 (0.4383), RRF 9; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/highload/v3/specification.mdx).
- `highload3:87` / `query_id` (composite structure): lexical 3 (BM25 -9.348337900038977), semantic 11 (0.4881), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/highload/v3/specification.mdx).

## T17 — abstain

能直接从 TON 地址算出用户公钥吗？合约还没部署时能在链上查到吗？

Expected: `addresses:27` · grounded

Returned: insufficient_evidence · Recall@5 0.0

正确地址/公钥块语义第 5、RRF 第 10，未进入回答 context；安全拒答，不再用 ton_proof 相关资料冒充答案。

Taxonomy: correct_candidate_low_rank, cross_language_ranking, false_no_answer, incomplete_selected_context

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| faq:12 | How do I implement backend authentication with TON Connect? | -2.23801222346775 | 1 | 0.5221 | 8 | 1 | 0.031099324975891997 |
| faq:11 | How do I implement backend authentication with TON Connect? | -1.9214562900589724 | 41 | 0.6180 | 1 | 2 | 0.01639344262295082 |
| connect:1 | What TON Connect is | -2.215608736996085 | 2 | 0.4764 | 21 | 3 | 0.016129032258064516 |
| highload3:46 | How `query_id` is checked | None | None | 0.5715 | 2 | 4 | 0.016129032258064516 |
| connect:0 | — | -2.1629404638606693 | 3 | 0.2871 | 415 | 5 | 0.015873015873015872 |

Expected evidence diagnostics:

- `addresses:27` / Drawbacks: lexical None (BM25 None), semantic 5 (0.5575), RRF 10; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/addresses/formats.mdx).

## T18 — complete

¿Qué identificadores de cadena devuelve TON Connect para la red principal y la red de pruebas?

Expected: `faq:1` · grounded

Returned: grounded · Recall@5 0.0

正确块虽未直接进入 Top-5，但由邻块展开进入 evidence，主/测试链编号完整，西语输出。

Taxonomy: correct_candidate_low_rank, cross_language_ranking

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| connect:1 | What TON Connect is | -5.582845167018277 | 5 | 0.5354 | 6 | 1 | 0.030536130536130537 |
| troubleshooting:59 | See also | -5.462491045695388 | 10 | 0.5102 | 11 | 2 | 0.028370221327967807 |
| catchain:27 | 2.4. Messages in a catchain. Catchain as a process group | -6.455219234868518 | 1 | 0.3733 | 163 | 3 | 0.01639344262295082 |
| faq:2 | How do I tell if the user is on mainnet or testnet? | -4.081328071085879 | 84 | 0.5886 | 1 | 4 | 0.01639344262295082 |
| catchain:32 | 2.4.4. Cones, or ideals with respect to $\prec$ | -6.1306498133714875 | 2 | 0.3924 | 127 | 5 | 0.016129032258064516 |

Expected evidence diagnostics:

- `faq:1` / How do I tell if the user is on mainnet or testnet?: lexical 41 (BM25 -4.863914905968345), semantic 4 (0.5558), RRF 10; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/faq.mdx).

## T19 — complete

Cambié de cuenta en mi monedero, pero la aplicación sigue usando la anterior. ¿Cómo cambio la cuenta conectada?

Expected: `faq:13, faq:14` · grounded

Returned: grounded · Recall@5 1.0

账户固定及断开重连完整，不再只复制 UNKNOWN_APP 原因。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| faq:14 | Why is there no `accountChanged` event? | None | None | 0.5928 | 1 | 1 | 0.01639344262295082 |
| faq:13 | Why is there no `accountChanged` event? | None | None | 0.5767 | 2 | 2 | 0.016129032258064516 |
| troubleshooting:23 | `UNKNOWN_APP_ERROR` — code 100 | None | None | 0.5155 | 3 | 3 | 0.015873015873015872 |
| troubleshooting:21 | `UNKNOWN_APP_ERROR` — code 100 | None | None | 0.4499 | 4 | 4 | 0.015625 |
| highload3:71 | Why internal messages to self? | None | None | 0.4467 | 5 | 5 | 0.015384615384615385 |

Expected evidence diagnostics:

- `faq:13` / Why is there no `accountChanged` event?: lexical None (BM25 None), semantic 2 (0.5767), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/faq.mdx).
- `faq:14` / Why is there no `accountChanged` event?: lexical None (BM25 None), semantic 1 (0.5928), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/faq.mdx).

## T20 — complete

¿Qué algoritmo de suma de comprobación usa una dirección amigable de TON y cuántos bytes ocupa?

Expected: `addresses:15` · grounded

Returned: grounded · Recall@5 1.0

CRC16-CCITT 与 2 bytes 完整符合西语 rubric。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| addresses:15 | Structure | -7.523578901897049 | 3 | 0.5022 | 1 | 1 | 0.032266458495966696 |
| whitepaper_comments:27 | 2.1.20. TON Virtual Machine | -7.960283418701161 | 1 | 0.4084 | 29 | 2 | 0.01639344262295082 |
| addresses:14 | Structure | -7.890368152314807 | 2 | 0.3202 | 190 | 3 | 0.016129032258064516 |
| catchain:134 | 3.4.6. Attempt identification. Fast and slow attempts | None | None | 0.4952 | 2 | 4 | 0.016129032258064516 |
| catchain:133 | 3.4.5. Protocol overview | None | None | 0.4912 | 3 | 5 | 0.015873015873015872 |

Expected evidence diagnostics:

- `addresses:15` / Structure: lexical 3 (BM25 -7.523578901897049), semantic 1 (0.5022), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/addresses/formats.mdx).

## T21 — complete

Si falla el puente de TON Connect, ¿cada cuánto reintenta el SDK la conexión SSE y el envío de mensajes?

Expected: `troubleshooting:12` · grounded

Returned: grounded · Recall@5 1.0

SSE 2 秒与 POST 5 秒完整，原成功保留。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| troubleshooting:12 | Bridge unreachable or timeout | -15.244171772844481 | 1 | 0.7377 | 1 | 1 | 0.03278688524590164 |
| troubleshooting:11 | Bridge unreachable or timeout | -12.00208492090557 | 3 | 0.5620 | 2 | 2 | 0.03200204813108039 |
| connect:13 | API reference | -12.221924487113165 | 2 | 0.4095 | 12 | 3 | 0.030017921146953404 |
| troubleshooting:26 | `UNKNOWN_ERROR` — code 0 | -8.30131760513654 | 12 | 0.4804 | 3 | 4 | 0.02976190476190476 |
| troubleshooting:59 | See also | -5.462491045695388 | 20 | 0.4134 | 11 | 5 | 0.02658450704225352 |

Expected evidence diagnostics:

- `troubleshooting:12` / Bridge unreachable or timeout: lexical 1 (BM25 -15.244171772844481), semantic 1 (0.7377), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).

## T22 — complete

¿El formato raw y el formato amigable de TON representan cuentas diferentes o la misma dirección?

Expected: `addresses:3` · grounded

Returned: grounded · Recall@5 0.0

原文与友好格式为同一地址；邻块 evidence 被真正使用。

Taxonomy: correct_candidate_low_rank, cross_language_ranking

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| addresses:4 | Raw format | -7.399380323300241 | 2 | 0.6310 | 1 | 1 | 0.03252247488101534 |
| addresses:5 | Structure | -6.6781635167756965 | 5 | 0.5520 | 2 | 2 | 0.0315136476426799 |
| addresses:9 | Drawbacks | -6.659202717297913 | 6 | 0.5191 | 4 | 3 | 0.030776515151515152 |
| addresses:8 | Structure | -5.991018321012326 | 8 | 0.5163 | 5 | 4 | 0.030090497737556562 |
| addresses:2 | — | -6.710987172568617 | 4 | 0.4666 | 12 | 5 | 0.029513888888888888 |

Expected evidence diagnostics:

- `addresses:3` / None: lexical None (BM25 None), semantic 3 (0.5343), RRF 12; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/addresses/formats.mdx).

## T23 — complete

What can cause a TON Connect bridge timeout, and how often does the SDK retry SSE and POST /message?

Expected: `troubleshooting:11, troubleshooting:12` · grounded

Returned: grounded · Recall@5 1.0

具体超时原因与 2/5 秒重试完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| troubleshooting:12 | Bridge unreachable or timeout | -31.081378048967764 | 1 | 0.7411 | 1 | 1 | 0.03278688524590164 |
| troubleshooting:10 | Bridge unreachable or timeout | -23.212521031675067 | 2 | 0.5546 | 3 | 2 | 0.03200204813108039 |
| troubleshooting:11 | Bridge unreachable or timeout | -22.792822222584977 | 3 | 0.5789 | 2 | 3 | 0.03200204813108039 |
| troubleshooting:9 | Bridge unreachable or timeout | -14.730820219338911 | 6 | 0.4489 | 7 | 4 | 0.03007688828584351 |
| troubleshooting:26 | `UNKNOWN_ERROR` — code 0 | -14.65647615841179 | 7 | 0.4184 | 13 | 5 | 0.02862400327131466 |

Expected evidence diagnostics:

- `troubleshooting:11` / Bridge unreachable or timeout: lexical 3 (BM25 -22.792822222584977), semantic 2 (0.5789), RRF 3; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).
- `troubleshooting:12` / Bridge unreachable or timeout: lexical 1 (BM25 -31.081378048967764), semantic 1 (0.7411), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).

## T24 — complete

How many bytes is a user-friendly TON address in total, and how are those bytes divided between flags, workchain, account and checksum?

Expected: `addresses:14, addresses:15` · grounded

Returned: grounded · Recall@5 1.0

36 总字节与 1/1/32/2 分解均完整，跨块事实未丢失。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| addresses:15 | Structure | -33.68339460245771 | 1 | 0.6978 | 1 | 1 | 0.03278688524590164 |
| addresses:14 | Structure | -22.42278899059915 | 4 | 0.5622 | 2 | 2 | 0.031754032258064516 |
| addresses:17 | Flag definitions | -19.926861927783655 | 5 | 0.5539 | 3 | 3 | 0.03125763125763126 |
| addresses:6 | Structure | -14.375783420782275 | 17 | 0.5309 | 4 | 4 | 0.028612012987012988 |
| addresses:18 | Flag definitions | -18.604777256943596 | 8 | 0.4788 | 14 | 5 | 0.02821939586645469 |

Expected evidence diagnostics:

- `addresses:14` / Structure: lexical 4 (BM25 -22.42278899059915), semantic 2 (0.5622), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/addresses/formats.mdx).
- `addresses:15` / Structure: lexical 1 (BM25 -33.68339460245771), semantic 1 (0.6978), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/addresses/formats.mdx).

## T25 — complete

If a shard with prefix p splits, what are its children's prefixes, and what prefix do they have after merging back?

Expected: `shards:10, shards:11` · grounded

Returned: grounded · Recall@5 1.0

拆分 p0/p1 与合并回 p 都回答，不再因相似度阈值拒答。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| shards:10 | Sharding process | -25.43616819435249 | 1 | 0.3595 | 2 | 1 | 0.03252247488101534 |
| shards:11 | Sharding process | -19.467554754622185 | 4 | 0.3851 | 1 | 2 | 0.032018442622950824 |
| shards:18 | Hypercube routing | -15.678857053304064 | 5 | 0.2918 | 10 | 3 | 0.02967032967032967 |
| shards:8 | Sharding process | -12.081077453480127 | 9 | 0.3088 | 7 | 4 | 0.029418126757516764 |
| shards:9 | Sharding process | -22.636284258137326 | 2 | 0.2009 | 131 | 5 | 0.016129032258064516 |

Expected evidence diagnostics:

- `shards:10` / Sharding process: lexical 1 (BM25 -25.43616819435249), semantic 2 (0.3595), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/shards.mdx).
- `shards:11` / Sharding process: lexical 4 (BM25 -19.467554754622185), semantic 1 (0.3851), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/shards.mdx).

## T26 — complete

In the legacy Catchain protocol, how is the catchain identifier derived from the genesis message?

Expected: `catchain:23, catchain:25` · grounded

Returned: grounded · Recall@5 1.0

genesis 结构的 SHA-256 完整，原成功保留。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| catchain:23 | 2.3. The genesis block and the identifier of a catchain | -12.774236118755844 | 2 | 0.8019 | 1 | 1 | 0.03252247488101534 |
| catchain:24 | 2.3.1. Distribution of the genesis block | -12.693748857610613 | 3 | 0.7413 | 2 | 2 | 0.03200204813108039 |
| catchain:25 | 2.3.2. List of nodes participating in a catchain | -10.517612426547183 | 4 | 0.6566 | 8 | 3 | 0.030330882352941176 |
| catchain:49 | 2.5.3. Message headers | -9.974176177939926 | 5 | 0.6368 | 13 | 4 | 0.029083245521601686 |
| catchain:52 | 2.5.3. Message headers | -8.09686892443456 | 12 | 0.6428 | 12 | 5 | 0.027777777777777776 |

Expected evidence diagnostics:

- `catchain:23` / 2.3. The genesis block and the identifier of a catchain: lexical 2 (BM25 -12.774236118755844), semantic 1 (0.8019), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/whitepapers/catchain.mdx).
- `catchain:25` / 2.3.2. List of nodes participating in a catchain: lexical 4 (BM25 -10.517612426547183), semantic 8 (0.6566), RRF 3; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/whitepapers/catchain.mdx).

## T27 — correct_abstain

Exactly how much gas in total does Highload v3 consume for a batch of 254 messages?

Expected: `highload3:135` · insufficient_evidence

Returned: insufficient_evidence · Recall@5 None

TBD 未伪装为精确 gas 总数；明确 insufficient。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| highload2:20 | `last_cleaned` (64 bits) | -14.382440008670034 | 5 | 0.5374 | 4 | 1 | 0.031009615384615385 |
| highload3:134 | Gas consumption | -9.213304997512584 | 14 | 0.6504 | 1 | 2 | 0.029906956136464335 |
| highload3:135 | Gas consumption | -21.96899079194641 | 1 | 0.4093 | 19 | 3 | 0.029051670471052088 |
| highload3:141 | Gas consumption | -8.906752607620172 | 18 | 0.5943 | 2 | 4 | 0.028949545078577336 |
| highload3:136 | Gas consumption | -9.002958733322432 | 17 | 0.4946 | 8 | 5 | 0.027692895339954164 |

Expected evidence diagnostics:

- `highload3:135` / Gas consumption: lexical 1 (BM25 -21.96899079194641), semantic 19 (0.4093), RRF 3; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/highload/v3/specification.mdx).

## T28 — correct_abstain

What compensation does the TON Connect bridge SLA guarantee after one hour of downtime?

Expected: `troubleshooting:9, troubleshooting:11, troubleshooting:12` · insufficient_evidence

Returned: insufficient_evidence · Recall@5 None

没有 SLA/赔偿条款，明确 insufficient。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| troubleshooting:11 | Bridge unreachable or timeout | -14.574664136502935 | 1 | 0.3457 | 3 | 1 | 0.032266458495966696 |
| troubleshooting:12 | Bridge unreachable or timeout | -11.585856597589014 | 7 | 0.4044 | 1 | 2 | 0.03131881575727918 |
| faq:7 | How do I make my own bridge? | -11.234685057864317 | 8 | 0.3012 | 5 | 3 | 0.030090497737556562 |
| troubleshooting:10 | Bridge unreachable or timeout | -11.818758356148514 | 5 | 0.2666 | 11 | 4 | 0.02946912242686891 |
| troubleshooting:9 | Bridge unreachable or timeout | -10.44345527777713 | 9 | 0.2592 | 17 | 5 | 0.027479766610201392 |

Expected evidence diagnostics:

- `troubleshooting:9` / Bridge unreachable or timeout: lexical 9 (BM25 -10.44345527777713), semantic 17 (0.2592), RRF 5; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).
- `troubleshooting:11` / Bridge unreachable or timeout: lexical 1 (BM25 -14.574664136502935), semantic 3 (0.3457), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).
- `troubleshooting:12` / Bridge unreachable or timeout: lexical 7 (BM25 -11.585856597589014), semantic 1 (0.4044), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).

## T29 — correct_abstain

My TON Connect transfer is stuck. Can these docs prove that my particular transaction failed because of a wrong network?

Expected: `troubleshooting:16` · insufficient_evidence

Returned: insufficient_evidence · Recall@5 None

通用文档不能证明某一用户交易原因，明确 insufficient。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| troubleshooting:5 | `MANIFEST_NOT_FOUND_ERROR` — code 2 | -16.75030878237464 | 1 | 0.4870 | 6 | 1 | 0.031544957774465976 |
| faq:2 | How do I tell if the user is on mainnet or testnet? | -7.7478277536255185 | 35 | 0.5152 | 1 | 2 | 0.01639344262295082 |
| catchain:182 | 3.5.8. Assumptions for proving the convergence of the protocol | -14.079610008793836 | 2 | 0.3330 | 70 | 3 | 0.016129032258064516 |
| faq:11 | How do I implement backend authentication with TON Connect? | -6.210779795384082 | 79 | 0.5031 | 2 | 4 | 0.016129032258064516 |
| faq:7 | How do I make my own bridge? | -13.846411284080489 | 3 | 0.3130 | 93 | 5 | 0.015873015873015872 |

Expected evidence diagnostics:

- `troubleshooting:16` / `BAD_REQUEST_ERROR` — code 1: lexical 49 (BM25 -7.272516543577529), semantic 25 (0.4293), RRF None; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/troubleshooting.mdx).

## T30 — correct_abstain

Which cafe in Oslo sells the cheapest almond croissant on Sunday?

Expected: `none` · no_authoritative_source

Returned: no_authoritative_source · Recall@5 None

无咖啡店证据，no_authoritative_source；未用模型常识回答。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| wallet_comparison:11 | Retail users | -7.480998766282198 | 1 | 0.0901 | 166 | 1 | 0.01639344262295082 |
| catchain:1 | — | None | None | 0.2505 | 1 | 2 | 0.01639344262295082 |
| whitepaper_comments:34 | 4.1.9. Decentralized mixed services, or fog services | None | None | 0.2347 | 2 | 3 | 0.016129032258064516 |
| wallet_comparison:3 | Comparison table | None | None | 0.2280 | 3 | 4 | 0.015873015873015872 |
| wallet_comparison:7 | Retail users | None | None | 0.2173 | 4 | 5 | 0.015625 |

Expected evidence diagnostics:


## T31 — correct_abstain

Who won the 2022 Wimbledon women's singles final?

Expected: `none` · no_authoritative_source

Returned: no_authoritative_source · Recall@5 None

无体育证据，no_authoritative_source。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| highload3:155 | Protection against `set_code` | -8.419228022730433 | 1 | -0.0523 | 654 | 1 | 0.01639344262295082 |
| catchain:1 | — | None | None | 0.2578 | 1 | 2 | 0.01639344262295082 |
| highload3:118 | Message sending flow | -6.08309387323468 | 2 | -0.0164 | 598 | 3 | 0.016129032258064516 |
| catchain:189 | 3.5.9. The protocol terminates under these assumptions | None | None | 0.2236 | 2 | 4 | 0.016129032258064516 |
| highload3:122 | Single message per external | -5.689324278266548 | 3 | 0.0037 | 527 | 5 | 0.015873015873015872 |

Expected evidence diagnostics:


## T32 — correct_abstain

As of January 15, 2024, was setting Highload v3 created_at 30 seconds in the past the official recommendation?

Expected: `highload3:58` · no_authoritative_source

Returned: no_authoritative_source · Recall@5 None

未来可观测快照不是历史证据，no_authoritative_source；仅时间拒答诊断。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|

Expected evidence diagnostics:

- `highload3:58` / Timestamp validation: lexical 1 (BM25 -19.12630291883061), semantic 3 (0.5301), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/highload/v3/specification.mdx).

## T33 — complete

Does TON Connect give a dApp access to the user's private keys?

Expected: `connect:2` · grounded

Returned: grounded · Recall@5 1.0

无私钥访问与加密会话完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| connect:2 | What TON Connect is | -19.413404231848794 | 1 | 0.6305 | 1 | 1 | 0.03278688524590164 |
| faq:12 | How do I implement backend authentication with TON Connect? | -10.968332619020408 | 11 | 0.5646 | 3 | 2 | 0.029957522915269395 |
| faq:14 | Why is there no `accountChanged` event? | -13.08143530533822 | 6 | 0.4635 | 13 | 3 | 0.028850145288501453 |
| connect:13 | API reference | -10.55524583961661 | 12 | 0.4470 | 16 | 4 | 0.027046783625730993 |
| faq:2 | How do I tell if the user is on mainnet or testnet? | -12.273194966895918 | 9 | 0.4295 | 20 | 5 | 0.026992753623188405 |

Expected evidence diagnostics:

- `connect:2` / What TON Connect is: lexical 1 (BM25 -19.413404231848794), semantic 1 (0.6305), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/overview.mdx).

## T34 — complete

Our treasury should not be movable by just one person. Which wallet type do the docs suggest for shared custody?

Expected: `wallet_comparison:16, wallet_comparison:18` · grounded

Returned: grounded · Recall@5 1.0

Multisig/shared custody 建议完整，原成功保留。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| wallet_comparison:17 | Shared custody | -14.67871712296994 | 4 | 0.6893 | 1 | 1 | 0.032018442622950824 |
| wallet_comparison:19 | Shared custody | -15.603638524922399 | 3 | 0.6652 | 2 | 2 | 0.03200204813108039 |
| wallet_comparison:16 | Shared custody | -23.715872442411392 | 1 | 0.6304 | 5 | 3 | 0.03177805800756621 |
| wallet_comparison:18 | Shared custody | -20.72055915550371 | 2 | 0.6370 | 4 | 4 | 0.031754032258064516 |
| wallet_comparison:21 | Shared custody | -12.985885764930396 | 5 | 0.6587 | 3 | 5 | 0.03125763125763126 |

Expected evidence diagnostics:

- `wallet_comparison:16` / Shared custody: lexical 1 (BM25 -23.715872442411392), semantic 5 (0.6304), RRF 3; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/comparison.mdx).
- `wallet_comparison:18` / Shared custody: lexical 2 (BM25 -20.72055915550371), semantic 4 (0.6370), RRF 4; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/comparison.mdx).

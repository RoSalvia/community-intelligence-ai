# Per-query failure and regression review

Retrieval scores refer to unchanged original query; no rewrite or reranker. Raw source/answer bodies remain in ignored local run artifacts.

## H01 — complete

In the documented common TON mnemonic derivation, what intermediate value is produced before the key pair, and by which algorithm?

Expected: `mnemonics:4` · grounded

Returned: grounded · Recall@5 0.0

PBKDF2 → seed → keypair 的中间关系正确，gold 从邻块进入。

Taxonomy: correct_candidate_low_rank

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| mnemonics:2 | Key pair | -20.370697820658307 | 2 | 0.6215 | 1 | 1 | 0.03252247488101534 |
| mnemonics:5 | Key pair from a mnemonic | -20.821737186308294 | 1 | 0.5782 | 3 | 2 | 0.032266458495966696 |
| mnemonics:6 | Key pair from a mnemonic | -19.402664276819664 | 3 | 0.6022 | 2 | 3 | 0.03200204813108039 |
| mnemonics:10 | Generate a key pair | -14.7736600775895 | 6 | 0.5736 | 4 | 4 | 0.030776515151515152 |
| mnemonics:7 | Key pair from a mnemonic | -15.603744752289874 | 5 | 0.5670 | 5 | 5 | 0.03076923076923077 |

Expected evidence diagnostics:

- `mnemonics:4` / Key pair from a mnemonic: lexical 8 (BM25 -14.564782866705253), semantic 6 (0.5489), RRF 7; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/mnemonics.mdx).

## H02 — complete

For a TON mnemonic with no password, what iteration count, salt and first seed byte make it valid?

Expected: `mnemonics:14` · grounded

Returned: grounded · Recall@5 1.0

390 iterations、salt、first byte 三项完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| mnemonics:14 | Mnemonic validation | -39.054642002673475 | 1 | 0.7932 | 1 | 1 | 0.03278688524590164 |
| mnemonics:7 | Key pair from a mnemonic | -27.39842817534789 | 2 | 0.6831 | 3 | 2 | 0.03200204813108039 |
| mnemonics:15 | Mnemonic validation | -27.35354369999707 | 3 | 0.6941 | 2 | 3 | 0.03200204813108039 |
| mnemonics:5 | Key pair from a mnemonic | -17.894499103154864 | 4 | 0.5707 | 4 | 4 | 0.03125 |
| mnemonics:4 | Key pair from a mnemonic | -16.206757415790833 | 5 | 0.4819 | 7 | 5 | 0.030309988518943745 |

Expected evidence diagnostics:

- `mnemonics:14` / Mnemonic validation: lexical 1 (BM25 -39.054642002673475), semantic 1 (0.7932), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/mnemonics.mdx).

## H03 — abstain

I keep rerunning my little wallet dev script and get a fresh account every time lol. What should I save and reuse so the key pair stays the same?

Expected: `mnemonics:13` · grounded

Returned: insufficient_evidence · Recall@5 0.0

保存 mnemonic 的正确块词法第 1、语义第 81、RRF 第 7；未进 Top-5/context，拒答。并非候选生成 miss。

Taxonomy: correct_candidate_low_rank, false_no_answer, incomplete_selected_context

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| history:32 | Wallet V3 | -16.994731514307034 | 2 | 0.4799 | 7 | 1 | 0.031054405392392875 |
| v5:27 | Exit codes | -11.571422672853531 | 8 | 0.4627 | 10 | 2 | 0.028991596638655463 |
| history:29 | Wallet V2 | -11.812720662877505 | 7 | 0.4501 | 14 | 3 | 0.028438886647841874 |
| connect_core:30 | Multi-device behavior | -13.501337168457622 | 4 | 0.4409 | 19 | 4 | 0.028283227848101264 |
| history:24 | Get methods | -10.987115928084311 | 11 | 0.4576 | 12 | 5 | 0.02797339593114241 |

Expected evidence diagnostics:

- `mnemonics:13` / Generate a key pair: lexical 1 (BM25 -36.66763278513044), semantic 81 (0.3485), RRF 7; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/mnemonics.mdx).

## H04 — complete

推导一个已经部署的 TON 合约地址时，是对现在的数据状态做哈希吗？应该怎样得到地址？

Expected: `derive:1, derive:2` · grounded

Returned: grounded · Recall@5 0.5

初始 StateInit 而非当前状态及推导步骤均完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| connect_core:65 | Security model | -1.9706134400781357e-06 | 1 | 0.3637 | 69 | 1 | 0.01639344262295082 |
| derive:2 | — | None | None | 0.5476 | 1 | 2 | 0.01639344262295082 |
| connect_core:10 | Connect over the JS bridge | -1.9018970428390986e-06 | 2 | 0.3200 | 120 | 3 | 0.016129032258064516 |
| derive:25 | On-chain — prefixed | None | None | 0.5190 | 2 | 4 | 0.016129032258064516 |
| mnemonics:0 | — | -1.8969067019378347e-06 | 3 | 0.0708 | 459 | 5 | 0.015873015873015872 |

Expected evidence diagnostics:

- `derive:1` / None: lexical None (BM25 None), semantic 4 (0.4874), RRF 8; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/addresses/derive.mdx).
- `derive:2` / None: lexical None (BM25 None), semantic 1 (0.5476), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/addresses/derive.mdx).

## H05 — complete

In Wallet V5, how is wallet_id calculated, and does get_subwallet_id return a plain subwallet number?

Expected: `v5:8, v5:9, v5:12` · grounded

Returned: grounded · Recall@5 0.6666666666666666

XOR、32-bit signed 与 get_subwallet_id 语义完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| v5:12 | Wallet ID scheme | -36.42473446545181 | 1 | 0.7720 | 1 | 1 | 0.03278688524590164 |
| v5:28 | Get methods | -24.304935034022876 | 2 | 0.6873 | 4 | 2 | 0.031754032258064516 |
| v5:11 | Wallet ID scheme | -14.737101102323049 | 3 | 0.6300 | 6 | 3 | 0.031024531024531024 |
| v5:8 | Wallet ID scheme | -11.375385882655312 | 8 | 0.6950 | 3 | 4 | 0.03057889822595705 |
| history:36 | Wallet V3 | -10.260030484875836 | 10 | 0.7035 | 2 | 5 | 0.0304147465437788 |

Expected evidence diagnostics:

- `v5:8` / Wallet ID scheme: lexical 8 (BM25 -11.375385882655312), semantic 3 (0.6950), RRF 4; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/v5.mdx).
- `v5:9` / Wallet ID scheme: lexical 7 (BM25 -11.91603021833036), semantic 8 (0.6178), RRF 6; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/v5.mdx).
- `v5:12` / Wallet ID scheme: lexical 1 (BM25 -36.42473446545181), semantic 1 (0.7720), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/v5.mdx).

## H06 — complete

What happens to a Wallet V5 internal message that fails authentication?

Expected: `v5:19` · grounded

Returned: grounded · Recall@5 1.0

未认证 internal message 按 transfer 处理，未误说 revert。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| v5:19 | Authentication process | -22.68839164993546 | 1 | 0.7914 | 1 | 1 | 0.03278688524590164 |
| v5:15 | Authentication process | -17.508925820179133 | 2 | 0.7372 | 2 | 2 | 0.03225806451612903 |
| v5:20 | Actions | -17.34977271632114 | 3 | 0.7202 | 3 | 3 | 0.031746031746031744 |
| v5:16 | Authentication process | -17.193964150806146 | 4 | 0.6782 | 5 | 4 | 0.031009615384615385 |
| v5:17 | Authentication process | -15.16259386579671 | 6 | 0.7162 | 4 | 5 | 0.030776515151515152 |

Expected evidence diagnostics:

- `v5:19` / Authentication process: lexical 1 (BM25 -22.68839164993546), semantic 1 (0.7914), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/v5.mdx).

## H07 — complete

What are the two internal-message authentication methods in Wallet V5, and why does the added method enable gasless services?

Expected: `v5:17, v5:18` · grounded

Returned: grounded · Recall@5 1.0

两种认证与 gasless 原因完整，跨邻块。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| v5:17 | Authentication process | -22.386051624454097 | 1 | 0.7597 | 3 | 1 | 0.032266458495966696 |
| v5:18 | Authentication process | -21.26905527009827 | 3 | 0.8099 | 1 | 2 | 0.032266458495966696 |
| v5:29 | Gasless transactions | -21.993995675937896 | 2 | 0.7732 | 2 | 3 | 0.03225806451612903 |
| v5:19 | Authentication process | -20.72123617895188 | 4 | 0.6994 | 4 | 4 | 0.03125 |
| v5:34 | Flow details | -19.66559708378072 | 5 | 0.6671 | 7 | 5 | 0.030309988518943745 |

Expected evidence diagnostics:

- `v5:17` / Authentication process: lexical 1 (BM25 -22.386051624454097), semantic 3 (0.7597), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/v5.mdx).
- `v5:18` / Authentication process: lexical 3 (BM25 -21.26905527009827), semantic 1 (0.8099), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/v5.mdx).

## H08 — complete

En Wallet V5, ¿qué bit de send_mode es obligatorio para mensajes externos y qué códigos se usan si falta ese bit o se superan 255 acciones?

Expected: `v5:24, v5:25, v5:26` · grounded

Returned: grounded · Recall@5 0.6666666666666666

+2、137、255/147 全部正确，西语跨语言成功。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| v5:24 | Action list validation | -20.01939353842735 | 1 | 0.6245 | 1 | 1 | 0.03278688524590164 |
| v5:13 | External message body layout | -10.106481381394044 | 5 | 0.5904 | 2 | 2 | 0.0315136476426799 |
| v5:25 | Exit codes | -10.690667748438102 | 3 | 0.5671 | 4 | 3 | 0.03149801587301587 |
| v5:8 | Wallet ID scheme | -10.941172809564033 | 2 | 0.5634 | 7 | 4 | 0.031054405392392875 |
| v5:2 | — | -10.656928883063266 | 4 | 0.5487 | 9 | 5 | 0.030117753623188408 |

Expected evidence diagnostics:

- `v5:24` / Action list validation: lexical 1 (BM25 -20.01939353842735), semantic 1 (0.6245), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/v5.mdx).
- `v5:25` / Exit codes: lexical 3 (BM25 -10.690667748438102), semantic 4 (0.5671), RRF 3; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/v5.mdx).
- `v5:26` / Exit codes: lexical 42 (BM25 -4.0316698896241485), semantic 22 (0.4920), RRF None; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/v5.mdx).

## H09 — complete

How do TON Center API v2 version numbers distinguish the Python and C++ implementations, and why does the major stay at 2?

Expected: `api:7` · grounded

Returned: grounded · Recall@5 1.0

Python/C++ minor 映射与 major 固定 2 的原因完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| api:7 | Versioning | -36.03233613112188 | 1 | 0.6087 | 2 | 1 | 0.03252247488101534 |
| api:0 | — | -16.703480995652562 | 2 | 0.5362 | 3 | 2 | 0.03200204813108039 |
| api:6 | Versioning | -15.381163779511422 | 6 | 0.6231 | 1 | 3 | 0.031544957774465976 |
| api:2 | — | -15.898097739506486 | 4 | 0.5274 | 4 | 4 | 0.03125 |
| api:12 | How to access the API | -15.441577234587092 | 5 | 0.4921 | 6 | 5 | 0.030536130536130537 |

Expected evidence diagnostics:

- `api:7` / Versioning: lexical 1 (BM25 -36.03233613112188), semantic 2 (0.6087), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/api/v2/overview.mdx).

## H10 — complete

不带 API key 访问 TON Center API v2，默认每秒能请求几次？想提高限制该怎么办？

Expected: `api:14` · grounded

Returned: grounded · Recall@5 1.0

1 rps 与 API key/plan 提升路径完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| api:14 | Managed service | -17.859430526799343 | 1 | 0.7691 | 1 | 1 | 0.03278688524590164 |
| api:2 | — | -15.898097739506486 | 4 | 0.5832 | 2 | 2 | 0.031754032258064516 |
| api:15 | Self-hosted service | -15.211551927842542 | 7 | 0.5773 | 3 | 3 | 0.030798389007344232 |
| api:12 | How to access the API | -15.441577234587092 | 5 | 0.5292 | 7 | 4 | 0.030309988518943745 |
| api:1 | — | -13.935196289170207 | 11 | 0.5303 | 6 | 5 | 0.029236022193768675 |

Expected evidence diagnostics:

- `api:14` / Managed service: lexical 1 (BM25 -17.859430526799343), semantic 1 (0.7691), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/api/v2/overview.mdx).

## H11 — complete

Is TON Center API v2 an indexed data layer, and how does it bridge the node's binary protocol to web access?

Expected: `api:2, api:3` · grounded

Returned: grounded · Recall@5 1.0

非索引层、ADNL、tonlib/liteserver/REST 完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| api:3 | — | -46.95097590897416 | 1 | 0.7774 | 2 | 1 | 0.03252247488101534 |
| api:2 | — | -38.88055231386879 | 2 | 0.8095 | 1 | 2 | 0.03252247488101534 |
| api:13 | Managed service | -22.552973711065043 | 3 | 0.7016 | 5 | 3 | 0.03125763125763126 |
| api:1 | — | -20.47006951540506 | 5 | 0.7288 | 3 | 4 | 0.03125763125763126 |
| api:15 | Self-hosted service | -21.866363392364743 | 4 | 0.6616 | 6 | 5 | 0.030776515151515152 |

Expected evidence diagnostics:

- `api:2` / None: lexical 2 (BM25 -38.88055231386879), semantic 1 (0.8095), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/api/v2/overview.mdx).
- `api:3` / None: lexical 1 (BM25 -46.95097590897416), semantic 2 (0.7774), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/api/v2/overview.mdx).

## H12 — complete

Which two interface styles does the TON Center API v2 overview say applications can use?

Expected: `api:1` · grounded

Returned: grounded · Recall@5 0.0

REST/JSON-RPC 完整；由邻块获得 gold。

Taxonomy: correct_candidate_low_rank

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| api:0 | — | -21.386375639843806 | 4 | 0.7529 | 1 | 1 | 0.032018442622950824 |
| api:3 | — | -24.246027056458157 | 2 | 0.6871 | 4 | 2 | 0.031754032258064516 |
| api:12 | How to access the API | -22.52952841919054 | 3 | 0.7018 | 3 | 3 | 0.031746031746031744 |
| api:4 | — | -24.250784898967538 | 1 | 0.6071 | 9 | 4 | 0.030886196246139225 |
| api:2 | — | -19.960939195751696 | 8 | 0.7488 | 2 | 5 | 0.030834914611005692 |

Expected evidence diagnostics:

- `api:1` / None: lexical 6 (BM25 -21.20461636890819), semantic 5 (0.6806), RRF 6; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/api/v2/overview.mdx).

## H13 — complete

Compared with Wallet V1, what delayed-confirmation safeguard was added in V2 and which exit code indicates its failure?

Expected: `history:28, history:29` · grounded

Returned: grounded · Recall@5 1.0

valid_until 与 exit35 完整，正确区分旧版本。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| history:29 | Wallet V2 | -36.44511726420289 | 1 | 0.5906 | 3 | 1 | 0.032266458495966696 |
| history:40 | Exit codes | -17.900859612709784 | 2 | 0.5367 | 5 | 2 | 0.0315136476426799 |
| history:23 | Exit codes | -16.304969685055593 | 3 | 0.5535 | 4 | 3 | 0.03149801587301587 |
| history:41 | Exit codes | -9.951639584868547 | 10 | 0.6619 | 1 | 4 | 0.030679156908665108 |
| history:28 | Wallet V2 | -15.788466590740152 | 4 | 0.5149 | 9 | 5 | 0.030117753623188408 |

Expected evidence diagnostics:

- `history:28` / Wallet V2: lexical 4 (BM25 -15.788466590740152), semantic 9 (0.5149), RRF 5; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/history.mdx).
- `history:29` / Wallet V2: lexical 1 (BM25 -36.44511726420289), semantic 3 (0.5906), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/history.mdx).

## H14 — complete

Wallet V3 怎么让同一个公钥对应多个钱包？为什么改那个参数会改变地址？

Expected: `history:32, history:36` · grounded

Returned: grounded · Recall@5 1.0

subwallet_id 与部署状态导致不同地址均完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| history:32 | Wallet V3 | -5.6281032494144725 | 8 | 0.7207 | 1 | 1 | 0.031099324975891997 |
| history:36 | Wallet V3 | -5.036022068223672 | 11 | 0.6480 | 2 | 2 | 0.03021353930031804 |
| history:33 | Wallet V3 | -7.414689903166218 | 3 | 0.5964 | 11 | 3 | 0.029957522915269395 |
| history:34 | Wallet V3 | -6.529120940480752 | 6 | 0.6010 | 9 | 4 | 0.02964426877470356 |
| v5:8 | Wallet ID scheme | -1.2079228167040519 | 14 | 0.6168 | 4 | 5 | 0.029138513513513514 |

Expected evidence diagnostics:

- `history:32` / Wallet V3: lexical 8 (BM25 -5.6281032494144725), semantic 1 (0.7207), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/history.mdx).
- `history:36` / Wallet V3: lexical 11 (BM25 -5.036022068223672), semantic 2 (0.6480), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/history.mdx).

## H15 — complete

In the Simplex system model, is Byzantine tolerance defined by validator count or weight, and what are the exact f and quorum q bounds?

Expected: `simplex:12` · grounded

Returned: grounded · Recall@5 1.0

weight 而非 count，严格 f<W/3 与 floor quorum 公式正确。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| simplex:12 | 1.1 System Model | -28.25155734292509 | 1 | 0.6029 | 1 | 1 | 0.03278688524590164 |
| simplex:13 | 1.1 System Model | -19.389961925227727 | 3 | 0.4849 | 7 | 2 | 0.030798389007344232 |
| simplex:146 | 3.3 Almost-sure Liveness | -8.842949853503121 | 10 | 0.5122 | 3 | 3 | 0.030158730158730156 |
| simplex:77 | 3.2 Network Model | -9.281684102204322 | 8 | 0.5071 | 5 | 4 | 0.030090497737556562 |
| simplex:180 | 4.3 Network Model Discussion | -21.15823742130974 | 2 | 0.4168 | 74 | 5 | 0.016129032258064516 |

Expected evidence diagnostics:

- `simplex:12` / 1.1 System Model: lexical 1 (BM25 -28.25155734292509), semantic 1 (0.6029), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/whitepapers/simplex.mdx).

## H16 — complete

En Simplex, ¿un candidato vacío avanza el estado visible? ¿Cuándo lo genera el líder de shardchain y cuándo el de masterchain?

Expected: `simplex:182, simplex:184, simplex:185` · grounded

Returned: grounded · Recall@5 1.0

空候选不推进状态，以及 shard/master 两个生成条件完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| simplex:184 | 4.4 Empty Candidates | -15.0385225388623 | 1 | 0.7562 | 1 | 1 | 0.03278688524590164 |
| simplex:185 | 4.4 Empty Candidates | -7.695206803394751 | 2 | 0.7353 | 2 | 2 | 0.03225806451612903 |
| simplex:182 | 4.4 Empty Candidates | -7.015128057498135 | 3 | 0.7310 | 3 | 3 | 0.031746031746031744 |
| simplex:2 | — | -0.6483404735787104 | 8 | 0.6142 | 12 | 4 | 0.028594771241830064 |
| derive:25 | On-chain — prefixed | -6.837861580473406 | 4 | 0.2596 | 360 | 5 | 0.015625 |

Expected evidence diagnostics:

- `simplex:182` / 4.4 Empty Candidates: lexical 3 (BM25 -7.015128057498135), semantic 3 (0.7310), RRF 3; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/whitepapers/simplex.mdx).
- `simplex:184` / 4.4 Empty Candidates: lexical 1 (BM25 -15.0385225388623), semantic 1 (0.7562), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/whitepapers/simplex.mdx).
- `simplex:185` / 4.4 Empty Candidates: lexical 2 (BM25 -7.695206803394751), semantic 2 (0.7353), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/whitepapers/simplex.mdx).

## H17 — complete

For Simplex's two-step FEC encoding, how many symbols are needed to reconstruct a candidate, how many losses are tolerated, and is that a weight threshold?

Expected: `simplex:180` · grounded

Returned: grounded · Recall@5 1.0

FEC 符号数量、损失上限与 count/weight 区分完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| simplex:180 | 4.3 Network Model Discussion | -41.619052839372486 | 1 | 0.7015 | 1 | 1 | 0.03278688524590164 |
| simplex:174 | 4.1 Concept-to-Code Map | -24.65454103103673 | 2 | 0.5239 | 6 | 2 | 0.03128054740957967 |
| simplex:12 | 1.1 System Model | -11.650087397963947 | 3 | 0.5156 | 7 | 3 | 0.030798389007344232 |
| simplex:146 | 3.3 Almost-sure Liveness | -7.535177745582419 | 12 | 0.5516 | 2 | 4 | 0.030017921146953404 |
| simplex:80 | 3.2 Network Model | -9.918998636777506 | 6 | 0.5079 | 9 | 5 | 0.02964426877470356 |

Expected evidence diagnostics:

- `simplex:180` / 4.3 Network Model Discussion: lexical 1 (BM25 -41.619052839372486), semantic 1 (0.7015), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/whitepapers/simplex.mdx).

## H18 — abstain

I want to see the MyTonCtrl install command and env it would use, but don't actually install anything yet. Which option is the dry run?

Expected: `mytonctrl:7` · grounded

Returned: insufficient_evidence · Recall@5 1.0

正确 --print-env 块排名第一，模型却把询问选项扩展成索要本机实际环境值，判缺证据；answerability 过度分解，不是检索或 chunk 不足。

Taxonomy: false_no_answer, answerability_overdecomposition

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| mytonctrl:7 | Install MyTonCtrl | -38.857214903344264 | 1 | 0.5985 | 1 | 1 | 0.03278688524590164 |
| mytonctrl:2 | Install MyTonCtrl | -23.93478997616423 | 2 | 0.5407 | 2 | 2 | 0.03225806451612903 |
| mytonctrl:4 | Install MyTonCtrl | -22.058889243200813 | 3 | 0.4244 | 6 | 3 | 0.031024531024531024 |
| mytonctrl:3 | Install MyTonCtrl | -12.884932884458527 | 7 | 0.4788 | 3 | 4 | 0.030798389007344232 |
| mytonctrl:6 | Install MyTonCtrl | -20.580117595854617 | 4 | 0.3642 | 8 | 5 | 0.030330882352941176 |

Expected evidence diagnostics:

- `mytonctrl:7` / Install MyTonCtrl: lexical 1 (BM25 -38.857214903344264), semantic 1 (0.5985), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/nodes/cpp/mytonctrl/overview.mdx).

## H19 — complete

MyTonCtrl 的 ARCHIVE_TTL 默认值在 liteserver 模式和其他模式分别是多少？要长期保留怎么设置？

Expected: `mytonctrl:10` · grounded

Returned: grounded · Recall@5 1.0

两个 TTL 默认值和 -1 完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| mytonctrl:10 | Environment variables | -15.118783075425576 | 1 | 0.6450 | 1 | 1 | 0.03278688524590164 |
| mytonctrl:1 | — | -12.098584231966878 | 3 | 0.5248 | 2 | 2 | 0.03200204813108039 |
| mytonctrl:6 | Install MyTonCtrl | -9.075168964391477 | 4 | 0.5057 | 3 | 3 | 0.03149801587301587 |
| mytonctrl:9 | Environment variables | -13.126615327782694 | 2 | 0.4601 | 7 | 4 | 0.031054405392392875 |
| mytonctrl:5 | Install MyTonCtrl | -7.239617176145453 | 5 | 0.4835 | 4 | 5 | 0.031009615384615385 |

Expected evidence diagnostics:

- `mytonctrl:10` / Environment variables: lexical 1 (BM25 -15.118783075425576), semantic 1 (0.6450), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/nodes/cpp/mytonctrl/overview.mdx).

## H20 — partial

Si tengo los datos actuales de un contrato vanity de TON, ¿puedo deducir su dirección o debo usar algo obtenido previamente?

Expected: `derive:20, derive:21, derive:50` · grounded

Returned: grounded · Recall@5 0.6666666666666666

不能从当前数据推出 vanity 地址及预先常量正确；严格 rubric 还列出随机 salt 搜索机制，回答未讲，原文已在 Top-5。

Taxonomy: strict_rubric_omission, incomplete_selected_context

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| derive:21 | On-chain — vanity | -4.896117639292728 | 10 | 0.5191 | 1 | 1 | 0.030679156908665108 |
| derive:20 | On-chain — vanity | -6.246601720816868 | 6 | 0.4839 | 5 | 2 | 0.030536130536130537 |
| derive:24 | On-chain — vanity | -7.303038795274991 | 1 | 0.3450 | 75 | 3 | 0.01639344262295082 |
| derive:22 | On-chain — vanity | -6.867174689065674 | 2 | 0.3837 | 49 | 4 | 0.016129032258064516 |
| v5:15 | Authentication process | None | None | 0.5171 | 2 | 5 | 0.016129032258064516 |

Expected evidence diagnostics:

- `derive:20` / On-chain — vanity: lexical 6 (BM25 -6.246601720816868), semantic 5 (0.4839), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/addresses/derive.mdx).
- `derive:21` / On-chain — vanity: lexical 10 (BM25 -4.896117639292728), semantic 1 (0.5191), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/addresses/derive.mdx).
- `derive:50` / Off-chain — vanity: lexical 7 (BM25 -6.208772318397935), semantic 114 (0.2931), RRF 12; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/foundations/addresses/derive.mdx).

## H21 — complete

Is a TON Connect client_id safe to treat as a completely public identifier? What can somebody who knows it do to queued bridge messages?

Expected: `connect_core:25` · grounded

Returned: grounded · Recall@5 1.0

半私密 client_id、读取密文/移除排队消息、不可解密边界完整。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| connect_core:25 | What is persisted | -37.653648015418874 | 1 | 0.6233 | 2 | 1 | 0.03252247488101534 |
| connect_core:60 | Security model | -17.838017803670347 | 3 | 0.6689 | 1 | 2 | 0.032266458495966696 |
| connect_core:7 | Connect, request, disconnect over the HTTP bridge | -17.95613996574689 | 2 | 0.5778 | 6 | 3 | 0.03128054740957967 |
| connect_core:21 | Sessions and keypairs | -14.548992804067383 | 5 | 0.6072 | 3 | 4 | 0.03125763125763126 |
| connect_core:39 | Parameters | -15.691174398040333 | 4 | 0.5411 | 12 | 5 | 0.029513888888888888 |

Expected evidence diagnostics:

- `connect_core:25` / What is persisted: lexical 1 (BM25 -37.653648015418874), semantic 2 (0.6233), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/core-concepts.mdx).

## H22 — partial

¿Puedo copiar el estado de una sesión TON Connect a otro dispositivo para continuar conectado? ¿Cuál es la forma indicada de conectar varios dispositivos?

Expected: `connect_core:29, connect_core:30, connect_core:31` · grounded

Returned: grounded · Recall@5 0.3333333333333333

不要复制、各设备重连、ton_proof/token 方案正确；未明确协议不自动同步 keypair，gold29 未进入 context。按锁定 rubric 严格记 partial。

Taxonomy: strict_rubric_omission, incomplete_selected_context

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| connect_core:32 | Multi-device behavior | -3.081504221193761 | 9 | 0.4790 | 8 | 1 | 0.02919863597612958 |
| connect_core:4 | Architecture | -3.023888456088793 | 13 | 0.4822 | 6 | 2 | 0.028850145288501453 |
| connect_core:10 | Connect over the JS bridge | -3.331191535016634 | 2 | 0.3944 | 19 | 3 | 0.02878726010616578 |
| connect_core:31 | Multi-device behavior | -2.929717825005614 | 20 | 0.5680 | 2 | 4 | 0.028629032258064516 |
| connect_core:20 | Sessions and keypairs | -2.9961924300946134 | 16 | 0.4805 | 7 | 5 | 0.028083267871170464 |

Expected evidence diagnostics:

- `connect_core:29` / Multi-device behavior: lexical 39 (BM25 -2.7106783569857518), semantic 3 (0.5504), RRF 9; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/core-concepts.mdx).
- `connect_core:30` / Multi-device behavior: lexical 56 (BM25 -2.4114072146322254), semantic 1 (0.5876), RRF 7; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/core-concepts.mdx).
- `connect_core:31` / Multi-device behavior: lexical 20 (BM25 -2.929717825005614), semantic 2 (0.5680), RRF 4; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/applications/ton-connect/core-concepts.mdx).

## H23 — correct_abstain

Exactly how many USDT does the Wallet V5 gasless service charge per transfer?

Expected: `v5:29, v5:34` · insufficient_evidence

Returned: insufficient_evidence · Recall@5 None

没有精确 USDT 数值，insufficient。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| v5:34 | Flow details | -27.561484538331534 | 1 | 0.6966 | 1 | 1 | 0.03278688524590164 |
| v5:29 | Gasless transactions | -18.48745967967084 | 2 | 0.6066 | 2 | 2 | 0.03225806451612903 |
| v5:2 | — | -16.764465311741088 | 3 | 0.5806 | 4 | 3 | 0.03149801587301587 |
| v5:33 | Gasless transactions | -10.838425258352974 | 7 | 0.5218 | 5 | 4 | 0.030309988518943745 |
| v5:31 | Gasless transactions | -9.862021643716275 | 10 | 0.5859 | 3 | 5 | 0.030158730158730156 |

Expected evidence diagnostics:

- `v5:29` / Gasless transactions: lexical 2 (BM25 -18.48745967967084), semantic 2 (0.6066), RRF 2; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/v5.mdx).
- `v5:34` / Flow details: lexical 1 (BM25 -27.561484538331534), semantic 1 (0.6966), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/v5.mdx).

## H24 — correct_abstain

What contractual uptime percentage and cash refund does TON Center API v2 guarantee?

Expected: `api:13, api:14` · insufficient_evidence

Returned: insufficient_evidence · Recall@5 None

没有 SLA/退款合同，insufficient。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| api:2 | — | -15.898097739506484 | 3 | 0.4746 | 3 | 1 | 0.031746031746031744 |
| api:0 | — | -16.70348099565256 | 1 | 0.4284 | 7 | 2 | 0.03131881575727918 |
| api:1 | — | -13.935196289170207 | 10 | 0.4777 | 2 | 3 | 0.0304147465437788 |
| api:8 | Typical use cases | -13.157378013902516 | 14 | 0.5032 | 1 | 4 | 0.029906956136464335 |
| api:14 | Managed service | -13.765097951881495 | 11 | 0.4359 | 5 | 5 | 0.02946912242686891 |

Expected evidence diagnostics:

- `api:13` / Managed service: lexical 9 (BM25 -14.086844032069138), semantic 20 (0.3756), RRF 8; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/api/v2/overview.mdx).
- `api:14` / Managed service: lexical 11 (BM25 -13.765097951881495), semantic 5 (0.4359), RRF 5; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/api/v2/overview.mdx).

## H25 — correct_abstain

我的 MyTonCtrl 节点昨天丢了归档数据。这些文档能证明就是 STATE_TTL 配置导致的吗？

Expected: `mytonctrl:10` · insufficient_evidence

Returned: insufficient_evidence · Recall@5 None

不能用通用 TTL 文档证明用户实际丢数据原因，insufficient。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| mytonctrl:10 | Environment variables | -10.290305240897988 | 1 | 0.5487 | 1 | 1 | 0.03278688524590164 |
| mytonctrl:1 | — | -6.114098575566318 | 5 | 0.4843 | 4 | 2 | 0.031009615384615385 |
| mytonctrl:12 | Command reference | -5.976912749683309 | 8 | 0.5374 | 2 | 3 | 0.030834914611005692 |
| mytonctrl:14 | Related resources | -6.535693566952229 | 2 | 0.4183 | 11 | 4 | 0.03021353930031804 |
| mytonctrl:11 | Command reference | -5.994383561332467 | 7 | 0.4332 | 6 | 5 | 0.03007688828584351 |

Expected evidence diagnostics:

- `mytonctrl:10` / Environment variables: lexical 1 (BM25 -10.290305240897988), semantic 1 (0.5487), RRF 1; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/nodes/cpp/mytonctrl/overview.mdx).

## H26 — correct_abstain

Which spacecraft first landed on Titan?

Expected: `none` · no_authoritative_source

Returned: no_authoritative_source · Recall@5 None

没有 Titan 登陆资料，no_authoritative_source。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| simplex:23 | 1.3 Protocol Objects | -4.172146167369034 | 5 | 0.1747 | 3 | 1 | 0.03125763125763126 |
| history:3 | Common concept | -4.187635124613559 | 4 | 0.1283 | 13 | 2 | 0.0293236301369863 |
| history:53 | Lockup wallet | -3.6699074561276492 | 14 | 0.1249 | 18 | 3 | 0.026334026334026334 |
| derive:59 | Off-chain — prefixed | -4.673434381830263 | 1 | -0.0285 | 410 | 4 | 0.01639344262295082 |
| history:44 | Wallet V5 | None | None | 0.2226 | 1 | 5 | 0.01639344262295082 |

Expected evidence diagnostics:


## H27 — correct_abstain

¿Quién compuso la ópera Turandot?

Expected: `none` · no_authoritative_source

Returned: no_authoritative_source · Recall@5 None

没有歌剧作曲资料，no_authoritative_source。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|
| history:0 | — | None | None | 0.1430 | 1 | 1 | 0.01639344262295082 |
| history:4 | Common concept | None | None | 0.1353 | 2 | 2 | 0.016129032258064516 |
| mnemonics:0 | — | None | None | 0.1214 | 3 | 3 | 0.015873015873015872 |
| history:2 | — | None | None | 0.1195 | 4 | 4 | 0.015625 |
| mnemonics:8 | Generate a key pair | None | None | 0.1068 | 5 | 5 | 0.015384615384615385 |

Expected evidence diagnostics:


## H28 — correct_abstain

As of June 1, 2023, did official TON documentation already promise 255 outgoing messages for Wallet V5?

Expected: `v5:2` · no_authoritative_source

Returned: no_authoritative_source · Recall@5 None

快照无法证明 2023 官方有效性；仅历史拒答诊断，不算历史事实准确率。

Taxonomy: none

| Actual Top-K | Section | BM25 | Lex rank | Cosine | Semantic rank | Raw RRF rank | RRF score |
|---|---|---:|---:|---:|---:|---:|---:|

Expected evidence diagnostics:

- `v5:2` / None: lexical 3 (BM25 -12.607572185437302), semantic 8 (0.5490), RRF 3; [pinned source](https://github.com/ton-blockchain/docs/blob/0e5a346d1e69a5345d333be669576acf21c6b93a/content/contracts/standard/wallets/v5.mdx).

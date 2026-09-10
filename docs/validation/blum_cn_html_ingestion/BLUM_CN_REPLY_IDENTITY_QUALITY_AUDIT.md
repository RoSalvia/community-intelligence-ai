# Blum CN Reply / Author Identity Quality Audit

Status: **review gate — validation complete; canonical identity policy unchanged**

This audit is limited to Telegram HTML ingestion and structural data quality. It
does not perform Topic, Behavior, Signal, moderator identification, Peer Support
classification, OCR, ASR, RAG, or any other semantic analysis.

## Scope and provenance

- Parser baseline: `131c801`, `telegram_desktop_html_v1.0.0`
- Canonical grain: one retained ordinary Telegram source message
- Canonical ordinary messages: 33,380
- Input fingerprint: `5a6995dd8719462b0f8e7147a2df83e55d1021a94c1aede1d8e4216e82c9f7fa`
- Current output fingerprint: `d91aad688e81196063e193afd7b13bf5384e4927e7493b57ad0a5d70747651e5`
- Private aggregate sidecar SHA-256: `820e79dc9a0fdef4868d479b149b7fbf9fdf3bb0971fad3926d560d45fce9487`
- Raw display names, avatar tokens, and message text were not persisted by the
  audit and do not appear in this report.

The source export stayed read-only. The current private canonical artifact was
regenerated with `Asia/Shanghai` and this provenance statement:

`human-confirmed by dataset owner: Telegram Desktop export environment used Beijing time`

The manifest still records `html_metadata_present = false`. Equivalently,
`timezone_not_declared_by_source_html = true`; the timezone is human-confirmed
operator provenance, not Telegram-provided HTML metadata.

## A. Reply relation quality

The three states remain disjoint:

| State | Count | Share of ordinary messages | Interpretation |
|---|---:|---:|---|
| `resolved_reply` | 4,603 | 13.789% | Child and parent are both retained canonical messages |
| `unresolved_reply` | 3,255 | 9.751% | Reply fact and raw parent ID are retained, but parent is absent from all snapshots |
| `non_reply` | 25,522 | 76.460% | No reply reference exists in source HTML |

Among the 7,858 reply messages, 58.577% resolve. All 4,603 resolved edges have a
parseable child author and parent author; 4,594 stay within one HTML page and 9
cross a `messages*.html` page boundary. All 4,603 timestamp pairs are available,
with zero child-before-parent timestamp violations and zero reply cycles.

Reply-chain depth over resolved parent links has median 1, p95 4, and maximum
18. The exact distribution is:

| Depth | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Replies | 3,197 | 746 | 334 | 149 | 84 | 41 | 20 | 8 | 2 | 2 | 2 | 3 | 2 | 4 | 4 | 2 | 2 | 1 |

Therefore, the canonical dataset supplies **4,603 reliable directed
message-level edges**. Of these, 1,944 (42.233%) have an export-local avatar
token on both author endpoints and form the high-confidence token-supported
identity subset. The remaining resolved edges are structurally valid but use a
lower-confidence display-name or conservative anchor identity.

The 3,255 unresolved messages still deterministically assert “this is a reply”
and retain `reply_to_message_id`. Their child author is parseable in all 3,255
cases; the parent author and parent timestamp cannot be recovered because the
parent message is absent from every supplied snapshot.

Implications:

- Response latency requires a resolved parent timestamp and is valid only for
  the 4,603 resolved edges.
- User-to-user, user-to-mod, mod-to-user, Peer Support, and Mod Response
  classification require a resolved parent identity. Role/class labels are not
  produced by this audit.
- Response Coverage may count observed resolved responses, but unresolved
  replies must be surfaced separately. They cannot be treated as non-replies or
  proof that no response occurred.

Severity: **High** for any metric that silently treats the 41.423% unresolved
reply share as non-reply; confidence: **High**. This is source-window
incompleteness, not parser loss.

## B. Export-local author token audit

`photos/author_<token>.jpg` was treated only as an export-local structural
signal. The audit does **not** interpret `<token>` as a Telegram user ID.

### Coverage

| Check | Count | Rate |
|---|---:|---:|
| Direct token on ordinary message block | 13,683 | 40.992% of messages |
| Token after joined inheritance | 23,036 | 69.011% of messages |
| Messages without reliable token | 10,344 | 30.989% of messages |
| Explicit author anchors | 20,492 | — |
| Initials-only explicit anchors | 6,809 | 33.228% of anchors |
| Explicit anchors with neither token nor initials | 0 | 0% |
| Joined messages | 12,888 | — |
| Joined messages inheriting author context | 12,888 | 100% |
| Joined messages inheriting a token-bearing context | 9,353 | 72.571% |

Joined inheritance itself is reliable: every joined message found a valid
author context. The lower token coverage reflects initials-only anchors, not an
inheritance failure.

### Mapping shape and stability

On the canonical maximal snapshot:

- 857 unique tokens map one-to-one to a display name; 0 tokens map to multiple
  display names.
- 850 display names have token evidence: 845 map to one token and 5 map to
  multiple tokens.
- 280 tokens occur across multiple HTML pages; none maps to multiple names.

Across all three cumulative export snapshots:

- 216 tokens recur across snapshots; none maps to multiple names.
- Among 3,037 non-deleted source messages appearing in multiple snapshots,
  2,225 have token evidence. 2,222 have the same token in every occurrence;
  0 have conflicting token values.
- Three messages switch only between photo-token and initials-only availability
  while retaining the same display name. This is a 0.135% availability drift
  among multi-snapshot messages with any token evidence, not a token-value
  conflict.

No token-covered case shows the same token under different display names at
different times. This provides strong within-export and cumulative-snapshot
stability evidence, but it does not establish global Telegram account identity
or stability across unrelated exports.

### Deleted Account and residual ambiguity

All 6,006 Deleted Account messages lack an avatar token: 3,818 are explicit
anchors and 2,188 are joined inheritances. The 2,519 Deleted Account messages
that recur across snapshots remain tokenless. Token-assisted resolution cannot
improve this segment; the current conservative anchor-plus-joined rule should
remain.

The current display-name policy has two observable risks:

- **Over-merge risk indicator:** 5 display names map to multiple tokens,
  affecting 138 canonical messages (0.413%). These are review candidates, not
  proof of five definite identity collisions or a ground-truth person count.
- **Rename split evidence:** 0 token-covered messages show one token under
  multiple display names. However, 10,344 tokenless messages (30.989%),
  including every Deleted Account message, remain a blind spot; split risk in
  this segment cannot be quantified from the export.

Severity: **Medium** for display-name-only user and reply-graph cardinalities;
confidence: **High** for the observed structural conflicts and **Low/Unknown**
for real-person identity in the tokenless segment.

## C. Controlled identity strategy comparison

The candidate comparison is deliberately conservative:

- Current: globally merge available authors by display name; use a distinct
  explicit anchor for Deleted Account; joined messages inherit the anchor.
- Candidate `telegram-html-author-identity-v1.1`: prefer an export-local token;
  joined messages inherit token plus provenance; retain display name as
  human-readable metadata/fallback evidence; when no reliable token exists,
  keep the explicit anchor rather than forcing a global merge; preserve the
  conservative Deleted Account rule.

| Metric | Current display-name strategy | Candidate token-assisted conservative | Difference |
|---|---:|---:|---:|
| Canonical author identities | 5,063 | 7,666 | +2,603 (+51.412%) |
| Unique resolved-reply responders | 1,290 | 1,684 | +394 (+30.543%) |
| Unique resolved-reply recipients | 1,529 | 1,996 | +467 (+30.543%) |
| Unique directed author pairs | 2,984 | 3,362 | +378 (+12.668%) |
| Self-replies | 131 | 126 | -5 |
| Cross-author replies | 4,472 | 4,477 | +5 |

The candidate count is a conservative pseudonymous-entity count, not a claim
that 7,666 real people participated. Its increase mostly reflects refusing to
globally merge initials-only and Deleted Account anchors without a token.

Recommended candidate provenance/confidence fields for a future schema version:

- `identity_strategy_version = telegram-html-author-identity-v1.1`
- `identity_signal = avatar_token | joined_avatar_token | conservative_anchor`
- `identity_scope = export_local`
- `identity_confidence = high | medium | low`
- `display_name` retained as metadata
- token stored only as a salted private pseudonym, never as a claimed Telegram
  account ID

This candidate is recommended for a versioned schema review because token
stability is materially stronger than display name where token coverage exists.
It was **not** applied to `messages.jsonl`, the M1 projection, or production
identity policy.

## D. Artifact and determinism checks

- Input fingerprint stayed unchanged after provenance correction.
- The output fingerprint changed from
  `9a4ae350ae8496984eb33373f0bcecb95bdf1e7e997cdc86f734c5052f075cb2`
  to `d91aad688e81196063e193afd7b13bf5384e4927e7493b57ad0a5d70747651e5`
  because timezone provenance is embedded in canonical messages.
- Data profile and M1 projection generation ID stayed unchanged.
- A second full parse produced the same output fingerprint and all 11 generated
  canonical/M1 files were byte-identical.
- Current private artifact:
  `data/private/blum-cn-html-ingestion/blum-cn-canonical-v1.0.0`
- Private audit sidecar: `reply_identity_quality_audit.json`

## Review-gate recommendation

Do not modify or rewrite parser/canonical v1.0.0. The resolved reply structure is
fit for resolved-only downstream relationship calculations, provided unresolved
replies remain a separate state. Propose `telegram-html-author-identity-v1.1` as
an additive, versioned identity-resolution contract for review; do not activate
it until the dataset owner approves the strategy and its confidence semantics.

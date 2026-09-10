# Blum CN Telegram HTML Identity v1.1 Validation

Status: **implementation complete; stopped at review gate**

This checkpoint implements an additive private identity-resolution layer over
`telegram-html-canonical-v1.0.0`. It does not rewrite canonical messages and it
does not perform Topic, Behavior, Signal, moderator detection, Peer Support,
contributor classification, OCR, ASR, RAG, or other semantic analysis.

## Contract and artifacts

Strategy: `telegram-html-author-identity-v1.1`

Private output:

`data/private/blum-cn-html-ingestion/blum-cn-identity-v1.1.0/`

- `message_identities.jsonl`: one identity and reply-state sidecar row for each
  canonical ordinary message.
- `reply_edges.jsonl`: one row for each resolved message-level reply relation.
- `metric_identity_contract.json`: downstream identity-quality and dependency
  requirements.
- `identity_manifest.json`: fingerprints, artifact hashes, coverage, timezone,
  privacy declarations, and reply-graph profile.

Each message identity records `resolved_identity_id`,
`identity_strategy_version`, `identity_signal`, `identity_scope`,
`identity_confidence`, private display-name metadata, resolution status, and
`reply_state`. Raw avatar tokens are used only inside the salted digest input;
they are never persisted.

The sidecar uses these confidence rules:

- **High:** direct `author_<token>` or Telegram joined inheritance from a
  token-bearing author anchor.
- **Medium:** non-deleted tokenless author context retained as a conservative
  explicit anchor; display name remains metadata and is not a global merge key.
- **Low:** Deleted Account or missing-author conservative anchor. Joined
  messages may inherit the anchor, but it is not promoted into a real-user
  identity.

`resolved_identity_id` is always an export-local salted pseudonym. A medium or
low ID represents a conservative conversation anchor, not a resolved person.

## Identity coverage

| Confidence | Messages | Message coverage | Pseudonymous identity IDs |
|---|---:|---:|---:|
| High | 23,036 | 69.011% | 857 |
| Medium | 4,338 | 12.996% | 2,991 |
| Low | 6,006 | 17.993% | 3,818 |
| Total | 33,380 | 100% | 7,666 |

Signal distribution:

| Signal | Messages |
|---|---:|
| `avatar_token` | 13,683 |
| `joined_avatar_token` | 9,353 |
| `conservative_anchor` | 2,991 |
| `joined_conservative_anchor` | 1,347 |
| `deleted_account_anchor` | 3,818 |
| `joined_deleted_account_anchor` | 2,188 |

The 7,666 pseudonymous IDs are not a public unique-user count. In particular,
medium/low anchors deliberately avoid forced merge and may over-split one real
person.

## Reply graph confidence

The canonical reply-state partition is unchanged:

| Reply state | Messages |
|---|---:|
| `resolved_reply` | 4,603 |
| `unresolved_reply` | 3,255 |
| `non_reply` | 25,522 |

All 4,603 resolved replies remain valid message-level directed edges and all
4,603 have a non-negative calculable response latency.

| Identity edge confidence | Edges | Coverage of resolved edges |
|---|---:|---:|
| High | 1,944 | 42.233% |
| Medium | 825 | 17.923% |
| Low | 1,834 | 39.844% |
| Lower-confidence total | 2,659 | 57.767% |

Self/cross-author is classified only when both endpoints are high confidence:

| Classification | Edges |
|---|---:|
| `self` | 102 |
| `cross_author` | 1,842 |
| `uncertain` | 2,659 |

Lower-confidence edges retain their pseudonymous endpoints, but downstream
product metrics must use `author_relation=uncertain` unless a stronger reviewed
identity source is supplied.

### Responder and recipient coverage

| Endpoint | Broader pseudonymous identities | High-confidence pseudonymous identities | Edges with high-confidence endpoint | Endpoint edge coverage |
|---|---:|---:|---:|---:|
| Responders | 1,684 | 262 | 3,046 | 66.174% |
| Recipients | 1,996 | 472 | 2,897 | 62.937% |

The broader counts may be used only with strategy, confidence distribution,
eligible numerator/denominator, token coverage, and uncertainty displayed. They
must not be labeled as unique people.

## Downstream metric-quality contract

### Message-level metrics

No stable identity is required for:

- reply count and the explicit
  `resolved_reply / unresolved_reply / non_reply` partition;
- response latency on all 4,603 resolved edges;
- other message-level volume/time facts that do not group by author.

### High-confidence identity metrics

Token-supported metrics must restrict both reply endpoints to high confidence
and report the 1,944/4,603 edge coverage. This applies to definitive
self/cross-author, unique responder/recipient, and identity-network results.

### Broader identity-dependent metrics

Fallback anchors may be included for exploratory/private results only when the
output reports identity strategy, high/medium/low distribution, eligible
numerator and denominator, token-supported coverage, and uncertain count. A
single unqualified “unique users” number is prohibited.

### Additional dependencies

- User↔User, User↔Mod, Mod↔User, per-Mod, and contributor exclusion metrics
  require reviewed role labels that this projection does not create.
- Peer Support and behavior-segmented metrics require separately evaluated
  semantic labels that this projection does not create.
- Unresolved reply remains a reply fact; unresolved identity remains
  conservative and cannot silently become a new real user.

## Privacy and data-quality validation

- Sidecar-to-canonical message join: 33,380/33,380; all message IDs unique.
- Resolved reply-edge IDs: 4,603/4,603 unique; all child/parent references join.
- Response latency: 4,603 available; zero negative values.
- Raw author tokens discovered in source: 857 unique.
- Exact raw-token values persisted in v1.1 projection: 0.
- Raw author-avatar paths persisted in v1.1 projection: 0.
- Real raw-token values present in Git diff: 0.
- Private salt remains outside source exports and Git.
- Source timezone: `Asia/Shanghai`.
- Provenance: `human-confirmed by dataset owner: Telegram Desktop export environment used Beijing time`.
- `timezone_not_declared_by_source_html = true` and
  `html_metadata_present = false` remain explicit.

## Regression and determinism

- Canonical v1.0 output fingerprint remains
  `d91aad688e81196063e193afd7b13bf5384e4927e7493b57ad0a5d70747651e5`.
- Canonical `messages.jsonl` SHA-256 remains
  `287ecee01751e1eb2f0c17f2abd843ebc8304d5076ead158c93b27e265aa26eb`.
- M1 text projection `messages.jsonl` SHA-256 remains
  `c124557b6b6b8fb5ef6bce9005b3bba94affdabfb1d1859ddb671d6041a315f6`.
- Identity v1.1 output fingerprint is
  `fcc917a7c55744d6ba54a6188e7d19df78eef3bf1ddff0708de95b8d4deb5f30`.
- Independent full canonical rerun: all 11 canonical/M1 files byte-identical.
- Independent identity rerun: all four identity files byte-identical.
- Existing Telegram JSON import path is not called or modified by the identity
  projection.
- Full repository regression: 401 passed, 7 skipped; scoped Ruff passed.
- Reply relation counts remain 4,603 resolved, 3,255 unresolved, and 25,522
  non-reply.

## Milestone handoff decision

- **M3:** safe as structural input for reply context and evidence. Topic and
  Behavior remain not run.
- **M4:** safe for message-level facts. Unique-affected-user or identity-grouped
  facts must surface the v1.1 quality contract.
- **M7:** safe as relationship foundation, but per-Mod/User↔Mod results remain
  unavailable until reviewed role labels exist.
- **M8:** safe as relationship foundation, but Peer Support/contributor outputs
  remain unavailable until role, bot, behavior, and relevant semantic labels
  exist.

The ingestion/identity foundation is safe to hand off with these gates. It is
not authorization to start semantic analysis or to publish 7,666 as a real-user
count.

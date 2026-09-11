# Blum CN + ES Telegram JSON Intake & Structural Profiling

**Status:** Complete; stopped at review gate. No Topic, Behavior, RAG, Signal, LLM, M3, or M4 execution.

## Snapshot freeze

- Stability checks: 3 (stable=true, source growth observed=true)
- Combined snapshot SHA256: `3ee6038272502c772e1ad4f2a852705eafa58ff3eedb53065baa66f5b8d0c857`
- Real chat text, raw sender IDs, media, and per-message canonical data remain under ignored `data/private/`.

## Exact intake facts

| Community | First ordinary UTC | Last ordinary UTC | Ordinary | Service | Shared-period ordinary | from_id coverage | Resolved / reply |
|---|---:|---:|---:|---:|---:|---:|---:|
| CN | 2024-03-19T01:11:45+00:00 | 2024-09-22T03:41:23+00:00 | 69909 | 184 | 69285 | 100.00% | 7873 / 14304 (55.04%) |
| ES | 2024-05-15T18:26:38+00:00 | 2026-09-11T00:00:49+00:00 | 81952 | 90 | 38114 | 100.00% | 35770 / 39998 (89.43%) |

Shared period: **2024-05-15T18:26:38+00:00 → 2024-09-22T03:41:23+00:00** (inclusive), derived from observed ordinary-message timestamps.

## JSON versus HTML

- CN ordinary messages: JSON 69,909; HTML 33,380; difference +36,529.
- Exact 33,380-message cohort reply resolution: JSON 58.58%; HTML 58.58%; reply partitions match 100.00%.
- Full JSON snapshot reply resolution is 55.04%; its wider coverage and denominator are not directly comparable with the shorter HTML export.
- Stable sender coverage: JSON from_id 100.00%; HTML high-confidence identity 69.01%.
- Preferred canonical source: **yes — telegram_desktop_json**. HTML remains fallback.

## Validation-window handoff

- CN: Natural 8; Challenge/Reply 8; High Activity 8; Hero 4.
- ES: Natural 8; Challenge/Reply 8; High Activity 8; Hero 3.

Candidate selection is deterministic and lexicographic with visible trigger facts; no opaque score is used. Official event dates provide temporal alignment only, never causation. `unresolved question` means a rule-detected question without a resolved direct reply edge, not a semantic judgment.

## Limitations

- Salted actor entities are export-local pseudonyms, not verified unique humans.
- Telegram JSON does not reliably encode moderator roles; no role-dependent claims are made.
- Most textless records do not include downloadable media/file metadata in this export; they remain separately counted rather than inferred as media-only.
- Spam is `Not implemented` because no reusable deterministic spam contract exists.
- Content Creation / Advocacy, Peer Support, and Question / Confusion entries are sampling suitability only; no semantic gold label was assigned.

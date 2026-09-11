# Blum CN + ES Telegram JSON Intake & Structural Profiling

## Goal

Freeze the two already-closed CN and ES chat objects from the append-only Telegram Desktop global JSON export, canonicalize them through the existing M1 Telegram JSON contract, and publish only privacy-safe deterministic audits, timelines, comparisons, and validation-window recommendations. Stop at the review gate.

## Fixed scope and boundaries

- Base commit: `09fd2464dc536d33286d1d033db57d8aa7e8454f`.
- Branch: `codex/blum-multilingual-json-intake` in its own worktree.
- Read `/Users/enm1cuarto/Downloads/Telegram_Export_2026-09-11/result.json` only; never modify, move, truncate, or replace it.
- Process only `Blum 官方中文社区🇨🇳` and `Blum Español 🇪🇸🇨🇱🇦🇷🇺🇾🇲🇽🇵🇦`; do not wait for or process EN.
- Keep snapshots, message text, raw IDs, media references, and per-message canonical artifacts under ignored `data/private/`.
- Trackable outputs contain aggregate facts, timestamps, rules, hashes, limitations, and candidate windows only.
- No Topic, Behavior classifier, RAG, Signal, remote LLM, Frozen M2, M3, or M4 changes. No merge or push.

## Implementation tasks

1. Add a structure-aware live-export scanner under `src/community_intelligence/importers/`.
   - Locate `chats.list` through JSON structure, not fixed byte offsets.
   - Recognize only complete direct chat objects; tolerate an incomplete later object/top-level suffix.
   - Capture file size/mtime plus byte ranges and hashes.
   - Require at least two matching observations before publishing a no-replace private snapshot directory.
   - Emit a complete combined Telegram-style snapshot plus one parser-ready `result.json` per community.

2. Add a JSON structural projection and audit layer that reuses the M1 importer primitives and canonical `CommunityDataset`.
   - Use `date_unixtime` as authoritative UTC time.
   - Use salted `from_id` pseudonyms for stable actor metrics; explicitly audit missing/deleted identities.
   - Preserve unresolved reply state instead of converting it to non-reply.
   - Derive only structural content flags and existing deterministic question/hygiene/burst rules.
   - Mark deterministic spam as `Not implemented`.

3. Add an aggregate-only profiling command under `scripts/validation/`.
   - Publish CN full, ES full, and shared-period profiles.
   - Publish 5m/15m/1h/1d timelines for both full and overlap scopes.
   - Discover Natural, Challenge/Reply-heavy, High Activity, and Hero candidates without a composite score.
   - Use official date-only event metadata only for temporal alignment, never causal claims.
   - Compare JSON against the existing detached HTML aggregate artifacts without modifying them.
   - Produce the M3 sampling handoff without semantic labels.

4. Verify and stop at review gate.
   - Focused red/green tests for incomplete-live extraction, stability rejection, privacy, absolute timestamps, identity coverage, reply partitioning, and overlap calculation.
   - Full Python regression and Ruff.
   - Re-run the private pipeline deterministically and compare aggregate artifact hashes.
   - Scan tracked outputs for raw sender IDs, pseudonymous IDs, names, message text, and media paths.
   - Record exact limitations and `Not implemented` capabilities.

## Completion criteria

- Frozen CN/ES source-object hashes match across two or more observations; snapshot JSON parses and hashes are recorded.
- Exact CN/ES coverage, ordinary/service counts, overlap, identity coverage, reply resolution, content structure, and deterministic hygiene facts are present.
- All requested timeline grains and window classes are present for CN and ES with concrete trigger facts.
- HTML-vs-JSON differences are backed by both current JSON aggregates and preserved HTML aggregate evidence.
- No private/source data is tracked; the branch remains isolated, unmerged, and unpushed.

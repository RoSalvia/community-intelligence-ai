# Blum Knowledge Acquisition / Hero Workspace Knowledge Pack

## Goal

Build a reproducible, official-source-only Blum Knowledge Pack from
`https://help.blum.io` and `https://blum.io/blog`, then test whether the frozen M2
contract at baseline `3858dbf4236a8b148997dede40b609f057d3b23e` can ingest and
serve it without changing any M2 retrieval, chunking, authority, reranking, or
grounding behavior.

## Authorized scope and boundaries

- Work only on branch/worktree `blum-knowledge-acquisition` from the exact M2
  baseline above. Do not merge and do not modify M3/M4.
- Crawl only the two approved official origins. Use robots policy, sitemap,
  official navigation, same-origin links, a descriptive user agent, and a
  minimum one-second request interval.
- Store raw HTML, normalized full text, caches, validation databases, and model
  artifacts only below ignored local `data/private/` or `data/validation/`.
- Commit only acquisition/normalization code, schema, aggregate manifest,
  hashes, tests, small synthetic fixtures, and the validation report. Do not
  commit Blum page bodies.
- Preserve absent or date-only time metadata exactly in the acquisition layer.
  Do not invent publication times or effective validity. If frozen M2's
  required precise timestamps prevent import, record that as a contract
  compatibility finding rather than changing M2.
- Do not add a Blum taxonomy, hard-coded answers, GraphRAG, query rewriting,
  multi-query, new heuristics, new chunk settings, or model training.

## Implementation plan

1. Add acquisition contracts and focused tests for URL canonicalization,
   same-origin filtering, pagination/tracking removal, robots decisions,
   deterministic source-type mapping, date precision, content hashing,
   duplicate detection, and manifest aggregation.
2. Add a conservative HTML/sitemap parser and polite HTTP acquisition runner.
   Every discovered URL must receive a reviewable inventory outcome. Persist
   raw and normalized artifacts only in ignored local storage.
3. Run the live Phase 1–5 acquisition against the approved origins. Generate a
   versioned aggregate manifest and a content-free validation report from the
   observed results.
4. Add a frozen-M2 import adapter that rejects sources lacking the precise,
   source-provided timestamps required by `SourceInput`; create an isolated
   Blum workspace/database and import every compatible source without altering
   M2 constants.
5. Define smoke questions only after inspecting acquired source metadata and
   content. Run retrieval/citation/as-of checks for the supported slices and
   record unavailable slices explicitly when acquisition coverage or timestamp
   fidelity is insufficient.
6. Verify focused tests, full backend regression, Ruff, artifact schemas,
   ignored-data boundaries, frozen-version constants, and Git status. Commit
   the isolated branch but do not merge or push.

## Completion criteria

- The manifest reports discovered/fetched counts by origin, source type,
  language, timestamp availability, duplicate class, failures, unknowns,
  historical coverage, and provenance.
- No raw or normalized Blum page body is tracked by Git.
- Import and smoke results distinguish acquisition, metadata, coverage, and
  genuine M2 limitations.
- The final report answers all ten requested product-review questions and
  includes reproducible commands and observed test evidence.

## Coverage-review correction

- Treat Wayback Blog URLs only as discovery hints. Recover the underlying
  official `/post/<slug>`, retry that official URL first, and label unavailable
  official pages as archive-fallback candidates without importing archive text.
- Treat Help 403 responses as an acquisition-method failure, not evidence that
  the Help Center has no knowledge pages. Use public URL inventories only for
  discovery, retry content solely on the official origin, and propose a
  manual/public-browser snapshot path when the official crawler path remains
  unavailable.
- Stop before final Frozen M2 smoke unless the coverage review establishes a
  representative corpus. A three-source pack is not representative coverage.

## Historical Blog archive phase

1. Freeze the current official Blog catalog as a separate provenance artifact.
   Parse every card's title, category, date precision, Read Article URL,
   original Blum URL, target kind, catalog observation time, and catalog hash.
2. Select the actual 2024 cards overlapping the CN Chat window
   `2024-03-19..2024-08-18` as the controlled set, capped at ten. Fetch archive
   content only when the current official catalog links that exact snapshot.
3. Add a Wayback-aware parser and historical-source contract. Exclude replay
   chrome/error shells, validate title/original URL/body, separate publication,
   snapshot, and observation times, and store full bodies only under ignored
   private data.
4. Gate expansion on controlled validation. If the controlled set is clean or
   failures are acquisition-only rather than parser/provenance failures, acquire
   all official-index-linked archive cards and build aggregate coverage metrics.
5. Run a Frozen M2 compatibility probe without changing any contract. Record
   date-only metadata blocks separately from acquisition/parser failures.
6. Update the aggregate manifest, schema, validation report, and a future-only
   Telegram Official Announcement acquisition plan. Verify deterministic reruns,
   private-data boundaries, focused tests, full regression, and frozen constants;
   commit locally without merge or push, then stop at the review gate.

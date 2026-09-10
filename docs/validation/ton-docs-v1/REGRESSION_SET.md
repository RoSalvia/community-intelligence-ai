# TON Docs regression set

Accepted external validation is now an M2.1 regression set, not an unseen test.
All 34 original questions, gold references, required context and answer rubrics remain byte-for-byte unchanged in `queries.json` (SHA256 `e05e26672a7847de9a411902ff5ea1707a5de9f6e84e1f712562b4fe0593241b`).

The original results and adjudication are immutable baseline evidence. New runs and comparisons go under `m2-1`, not over the original experiment. Improvements on this set require a separately locked, document-disjoint holdout before any generalization claim.

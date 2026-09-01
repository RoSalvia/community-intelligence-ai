# Community Intelligence Web Product — Low-Fidelity Wireframe

## Purpose and fixed product rules

This wireframe translates the V0.1 product brief into a seven-view local web application. It deliberately describes information architecture before decorative styling. Message count is context, not quality. A page may show volume to explain the analysis scope, but it may not turn activity volume into an overall Moderator Score or imply that more messages mean healthier operations.

Every important judgment must expose evidence IDs, source messages, method, confidence semantics and review status. “Available”, “Not available for this dataset” and “Not implemented” are separate states. “Not available” means the method exists but the current input lacks the required data; “Not implemented” means the product does not claim the capability. Human review remains visible wherever candidate behavior names, campaign coverage or other interpretive outputs are shown.

Synthetic analysis and imported Telegram analysis use the same page structure. The source type, data status and limitations remain visible in the header and Overview. Outcome-aware statistics must say association, not causation. A chart never stands alone: users receive the underlying values, denominator or evidence route in the same view.

## Shared shell and interaction model

Desktop uses a persistent left navigation with Overview, Campaigns, Communities, Behaviors, Response Patterns, Metric Lab and Evidence. Mobile collapses the same navigation behind a labelled menu button. The top bar displays the loaded analysis source and provides access to Data & Methods. Running the synthetic demo or importing a Telegram Desktop JSON export creates one analysis session and updates all seven views from the same report.

An evidence trigger opens a right-side drawer without losing the current page context. The drawer presents evidence metadata first, then source messages in chronological order. Closing the drawer returns focus to the trigger that opened it. Filters are scoped to the loaded report and never change the underlying stored report.

## Capability states

| State | Meaning | Required presentation |
| --- | --- | --- |
| Available | The method ran and the report contains a result | Show result, method, scope and evidence route |
| Not available | The method exists but required fields or observations are absent | Explain exactly what data is missing and how to provide it |
| Not implemented | The product does not perform the claimed analysis | Use explicit “Not implemented” language; never substitute a proxy |
| Pending review | A candidate interpretation requires a person’s decision | Show evidence and confidence semantics; do not style as final truth |

## View 1 — Overview

The Overview answers four questions in order: what was analyzed, which capabilities are available, what signals deserve attention, and where can the user inspect evidence. The first row shows source type, message count, communities, languages and campaigns as scope facts. The second row presents capability cards for Community, Campaign and Outcome-aware analysis. The main body shows evidence-backed summaries for Activation, Hygiene, Feedback and Response Patterns, followed by limitations. The page never combines them into a single quality score.

Primary interactions are Run synthetic demo, Import Telegram JSON, open a community, open a campaign and inspect evidence. Loading, empty, import-error and partial-data states replace the same content region instead of opening unrelated screens.

## View 2 — Campaigns

Campaigns starts with a campaign selector and a summary of the intended claims. A community-by-claim matrix shows Covered, Partially covered, Not observed or Not available. Selecting a cell reveals its method, match strength, review status and evidence trigger. The lower section compares discussion share and selected activation indicators by community only when the report contains the required campaign window. General multilingual semantic judgment remains labelled Not implemented while the deterministic curated-alias baseline is used.

## View 3 — Communities

Communities compares community-level observations without ranking moderators or producing a composite score. The table exposes message scope, languages, meaningful interaction, peer support, response latency, duplicate content and filler content. Selecting a row opens a detailed panel with formulas, denominators, unavailable fields and evidence. Campaign-aware filters appear only when campaign data exists; otherwise the page remains useful in Community-only mode.

## View 4 — Behaviors

Behaviors presents deterministic seed labels separately from unsupervised candidate clusters. Each cluster card contains provisional terms, language and role distributions, message count, confidence semantics and Pending review status. The interface never invents a polished behavior name when `proposed_behavior_name` is null. Evidence opens representative messages so a reviewer can decide whether the cluster is coherent and useful.

## View 5 — Response Patterns

Response Patterns treats conversation episodes as reply-graph descriptions, not semantic resolution claims. The summary includes episode count, participants, question count, candidate answer count, unanswered question count, depth and first-response latency. Selecting an episode reveals the chronological thread, the transparent question rule and the limits of the candidate-answer rule. “Resolved” compatibility fields are never presented as proof that a user’s issue was actually solved.

## View 6 — Metric Lab

Metric Lab separates candidate metric definitions from observed validation results. Each definition includes business meaning, formula, numerator, denominator, unit of analysis, time window, required fields, evidence requirements, biases and limitations. Outcome-aware results show sample size, association estimate, uncertainty or test metadata and multiple-testing status when available. The page repeats that all results are descriptive association, not causation, and that synthetic validation does not establish external validity.

## View 7 — Evidence

Evidence is the audit surface for all analytical claims. Users can filter by evidence ID, message ID, community, campaign, method, rule and review status. Each row exposes the analytical claim and the linked source message identifiers. Opening a row displays original text, normalized metadata, timestamps, reply relationships, method version, threshold or raw metric where applicable, confidence semantics and review status. Real imported content is displayed locally and is not sent to a cloud service by the V1 product.

## Acceptance notes

The implementation matches this wireframe when all seven routes are reachable by keyboard, synthetic demo data fills every supported page, a Telegram JSON import reaches the same report views, evidence triggers open source-linked detail, mobile navigation works, empty/error/partial states are understandable, and unsupported capabilities remain explicit. Visual differences are acceptable when they improve usability without changing these information and evidence contracts.

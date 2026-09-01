# Metrics and Interpretation

Community Intelligence treats metrics as reviewable definitions, not universal truth. Every candidate metric records business meaning, formula, numerator/denominator, unit of analysis, time window, required fields, evidence requirements, biases, and limitations. The Metric Lab displays definitions separately from observed validation results.

Implemented candidate metrics include campaign discussion share, community response latency, conversation propagation depth, meaningful interaction ratio, organic project mention rate, peer support ratio, deterministic campaign coverage/drift, unanswered question rate, and user-to-user interaction ratio. Exact canonical definitions live in the generated report and `src/community_intelligence/metrics.py`.

Message count is a scope fact. It must not be used as a direct proxy for community quality, moderator usefulness, user understanding, or campaign success. The project does not calculate a composite Moderator Score and does not invent metric weights.

Response latency uses the first chronological direct moderator reply when role data exists. A fast reply can still be incorrect or unhelpful. Candidate answers in reply episodes are structural graph signals, not proof that a question was semantically resolved. Meaningful interaction uses transparent language-specific filler/minimum-length rules and does not make a general cross-language quality claim.

Statistical validation reports descriptive association, sample size, method, and limitations. Correlation is never causation. Synthetic outcomes are useful for pipeline verification but do not establish external validity; a metric should not be adopted operationally without suitable real-world data, robustness checks, and human business judgment.

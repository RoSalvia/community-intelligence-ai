# v0.1.0-alpha Release Notes

This first public alpha packages the existing Community Intelligence V0.1 as a local-first, reproducible open-source project. It is intended for product exploration and evidence-bounded analysis, not production monitoring or automated employee evaluation.

## What works

- One-command local web product with `community-intelligence serve`.
- Reproducible multilingual synthetic demo.
- Bounded Telegram Desktop JSON import followed by normalized analysis.
- Seven evidence-linked views: Overview, Campaigns, Communities, Behaviors, Response Patterns, Metric Lab, and Evidence.
- Deterministic community hygiene, activation, feedback, reply-episode, and campaign-coverage baselines.
- Behavior clustering plus candidate metric definitions and bounded statistical validation.
- Packaged frontend, installed CLI, CI configuration, and end-to-end release verification from a fresh wheel.

## Known limitations

- General multilingual semantic campaign judgment is not implemented.
- LLM-generated behavior naming is not implemented.
- Semantic retrieval is not integrated into the default report pipeline.
- Real-time Telegram integration is not implemented.
- Telegram Desktop exports do not reliably recover moderator roles, so imported roles default to `user`.
- V0.1 has no accounts, hosted multi-user service, billing, or cloud deployment.
- Synthetic results verify product behavior and reproducibility; they do not establish real-world metric validity.

No Git tag or hosted release is created during local public-release preparation. The release name is `v0.1.0-alpha`; the Python package uses the PEP 440 equivalent `0.1.0a0`.

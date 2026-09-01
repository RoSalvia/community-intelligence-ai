# Privacy and Data Handling

The default demo uses clearly labelled synthetic multilingual data. The Telegram importer accepts a local Telegram Desktop chat-history JSON file, hashes user and community identifiers deterministically, skips unsupported service/empty messages, and retains source message text for evidence review. Hashing identifiers is pseudonymization, not full anonymization: message text can still contain names, addresses, wallet identifiers, or other personal information.

`community-intelligence serve` binds to `127.0.0.1`. The V0.1 application has no telemetry, analytics beacon, account system, remote model call, or cloud upload path. Analysis data remains on the workstation under `~/.community-intelligence/analyses` unless `COMMUNITY_INTELLIGENCE_DATA_DIR` is set to another local location.

Users are responsible for lawful access, consent, retention, backups, and deletion of imported chat data. Do not commit real exports or generated real-data reports to Git. Before sharing a report, inspect both `report.json` and `evidence.jsonl`; the latter may contain original message text.

The optional semantic-model workflow is separate from ordinary analysis. Tests do not silently download models, and the default pipeline does not send message content to a model provider. Any future hosted or external-model integration requires a new privacy review and explicit user-visible data-flow disclosure.

# Contributing

Community Intelligence AI welcomes small, evidence-backed contributions that preserve the local-first product boundary. Before changing behavior, read `AGENTS.md`, `docs/ARCHITECTURE.md`, and the relevant tests. Open an issue before adding a new integration or analytical capability so product scope, data requirements, evaluation, and license implications can be agreed first.

Use test-driven development for production behavior. Add one focused failing test, confirm the expected failure, implement the smallest coherent change, then run the focused and full quality checks. Python changes must pass `uv run ruff check src tests` and `uv run pytest -q`. Web changes must pass the frontend unit test, typecheck, lint, production build, and relevant Playwright path.

Do not commit raw private chats, personal identifiers, credentials, downloaded model artifacts, generated analysis workspaces, `node_modules`, or local virtual environments. Synthetic fixtures must be clearly fictional. Do not describe a heuristic, cluster, or association as a verified semantic judgment or causal effect.

Pull requests should state the user problem, implemented scope, tests run, limitations, and any new dependency or data-contract decision. Update `docs/OSS_REUSE_AUDIT.md` and `THIRD_PARTY_NOTICES.md` whenever direct dependencies or copied OSS source change.

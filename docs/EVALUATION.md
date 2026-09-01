# Evaluation Status

V0.1 evaluates reproducibility, data-contract correctness, evidence joinability, bounded import behavior, deterministic analytical rules, API behavior, and user-facing product flows. The ordinary suite uses synthetic or fictional fixtures only.

The Python suite covers normalized models, atomic publication, synthetic generation, hygiene, activation, campaign judgments, behavior clustering, response episodes, metric validation, Telegram import, CLI behavior, local API boundaries, wireframe artifacts, and release-package requirements. The web suite covers loading/error states, seven report views, evidence drawers, Telegram import, campaign/evidence filtering, and mobile navigation. Browser tests run against the actual packaged frontend and local API.

Deterministic baselines are the reference point for future semantic or LLM work. A multilingual embedding provider has an optional, separately prefetched local integration test, but semantic retrieval is not called by the report pipeline and must not be described as evaluated product behavior.

Known evaluation limits are explicit: synthetic data cannot validate real community usefulness; the Telegram V0.1 importer does not recover moderator roles; curated aliases are not general semantic understanding; unsupervised clusters remain unnamed pending review; structural reply edges are not semantic resolution; and associations do not establish causal effects.

Before a release, run `./scripts/verify_release.sh`, inspect the generated wheel contents, and run Playwright in CI. A release is not complete when only engine tests pass: a stranger must be able to install, start, run the synthetic demo, import a bounded Telegram export, navigate all seven views, and understand the limitations.

## V0.1 release evidence

The complete release verification passed on 2026-09-01 on macOS 26.4.1 arm64 with Python 3.11.15, uv 0.11.6, Node.js 22.22.2, and npm 10.9.7. It recorded 332 passed and 2 skipped Python tests; the two skips are the opt-in semantic-model checks. The web checks recorded 3 passed unit tests, clean TypeScript and ESLint runs, a successful production build, and 4 passed Playwright flows. npm reported zero known vulnerabilities in the resolved 334-package development tree.

The built wheel contained the Python package, installed `community-intelligence` entry point, Apache-2.0 license, third-party notices, one frontend entry document, two JavaScript bundles, and one CSS bundle. A fresh Python 3.11 virtual environment installed that wheel and successfully exercised `--help`, the 120-message synthetic demo, Telegram JSON import followed by analysis, loopback service health/homepage, all seven product views, Evidence detail, campaign and evidence filtering, mobile navigation, and import error handling.

This evidence does not validate usefulness on real community operations. General multilingual semantic campaign judgment, LLM-generated behavior naming, and semantic retrieval inside the default report pipeline remain `not_implemented`. Real-time ingestion, reliable moderator-role recovery from Telegram exports, hosted multi-user operation, accounts, billing, and cloud deployment remain outside V0.1.

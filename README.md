# Community Intelligence AI

Community Intelligence AI is a local-first, evidence-linked product for understanding how multilingual communities respond—not merely how much they talk. It turns a Telegram Desktop export or a reproducible synthetic dataset into seven connected views: Overview, Campaigns, Communities, Behaviors, Response Patterns, Metric Lab, and Evidence.

This is an open-source vibe-coding project built from real experience managing more than ten multilingual Web3 Telegram communities. The original KPI evolved from message count to keyword hit rate, then into a broader question: can AI discover candidate behaviors and response patterns while statistics and humans validate which signals are actually useful? Moderator evaluation is a possible downstream use case, not the center of the product.

## Quick start

You need Python 3.11+ and [uv](https://docs.astral.sh/uv/). Clone the repository, then run:

```bash
uv sync
uv run community-intelligence serve
```

The command starts a loopback-only local server at `http://127.0.0.1:8765/` and opens the product in your browser. Use `--no-open` if you do not want the browser opened automatically, or `--port 8989` to select another local port.

Click **Run synthetic demo** for an immediate reproducible analysis. To analyze your own data, export one chat from Telegram Desktop as machine-readable JSON, then click **Import Telegram JSON** and select its `result.json` file. Uploaded content is processed locally; V0.1 does not send it to a cloud service.

## What is implemented

- A synthetic multilingual dataset generator covering English, Spanish, Chinese, and Arabic.
- A bounded Telegram Desktop JSON importer that normalizes rich text and reply relations while hashing user and community identifiers.
- Deterministic hygiene, activation, campaign-coverage, feedback, reply-episode, behavior-clustering, metric-definition, and bounded statistical-validation pipelines.
- Joinable evidence records with source message IDs/text, method, confidence semantics, and review status.
- Community-only, Campaign-aware, and Outcome-aware capability states with explicit `available`, `not_available`, and `not_implemented` distinctions.
- A responsive local web product, thin FastAPI adapter, installed CLI, unit tests, API tests, and browser acceptance tests.

Message count is always scope context, never an operational quality score. The product does not calculate an unvalidated composite Moderator Score. Statistical results are descriptive associations, not causal effects.

## Important boundaries

General multilingual semantic campaign judgment, LLM-generated behavior naming, and pipeline semantic-retrieval integration are **Not implemented**. The optional embedding provider has a separate local evaluation path, but the default report pipeline does not silently download or call a model. Real-time Telegram collection, Discord integration, accounts, billing, hosted multi-user operation, automated HR decisions, and cloud deployment are outside V0.1.

Telegram import currently supports a deliberate subset of Telegram Desktop chat-history JSON: ordinary text/rich-text messages, timestamps, authors, and reply relationships. Service messages and empty messages are skipped. Telegram exports do not reliably identify moderators, so imported roles default to `user`; the report exposes this limitation.

## CLI workflows

The web product is the easiest entry point. Reproducible CLI workflows remain available:

```bash
# Complete synthetic dataset + report workspace
uv run community-intelligence demo --workspace demo --messages 120

# Telegram JSON → normalized dataset → community-only report
uv run community-intelligence import telegram \
  --input result.json \
  --output data/my-community \
  --language en
uv run community-intelligence analyze \
  --input data/my-community \
  --output reports/my-community
```

Every output directory is create-only: existing paths are preserved rather than overwritten.

## Development and verification

```bash
uv sync
uv run ruff check src tests
uv run pytest -q

npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

Browser tests use Playwright. Run `npm --prefix frontend exec -- playwright install chromium`, start the local product with `community-intelligence serve --no-open`, then run `npm --prefix frontend run test:e2e`. Maintainers can run `./scripts/verify_release.sh` for the complete lint, test, build, fresh-wheel install, Telegram import, packaged-service, and browser release path.

## Documentation

- [Product architecture](docs/ARCHITECTURE.md)
- [Metrics and interpretation](docs/METRICS.md)
- [Evaluation status](docs/EVALUATION.md)
- [Privacy and local-data behavior](docs/PRIVACY.md)
- [OSS reuse audit](docs/OSS_REUSE_AUDIT.md)
- [Low-fidelity interaction contract](docs/wireframes/README.md)
- [Contributing](CONTRIBUTING.md) and [security policy](SECURITY.md)

## License

Community Intelligence AI is licensed under Apache-2.0. Direct dependency licenses and reuse decisions are summarized in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); lock files remain the authoritative resolved dependency inventory for a specific build.

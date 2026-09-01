# Third-Party Notices

Community Intelligence AI is Apache-2.0 licensed. It depends on third-party packages under their own licenses. This notice is a practical top-level inventory, not legal advice or a complete transitive software bill of materials. `uv.lock` and `frontend/package-lock.json` identify the exact resolved dependency graph for a build.

## Python runtime

| Package | Purpose | License |
| --- | --- | --- |
| FastAPI | Local HTTP API | MIT |
| Uvicorn | Local ASGI server | BSD-3-Clause |
| Pydantic | Data validation/contracts | MIT |
| python-multipart | Bounded browser file upload parsing | Apache-2.0 |
| pandas | Tabular loading and aggregation | BSD-3-Clause |
| NumPy | Numerical operations | BSD-3-Clause |
| SciPy | Statistical calculations | BSD-3-Clause |
| scikit-learn | TF-IDF/KMeans and evaluation utilities | BSD-3-Clause |
| NetworkX | Reply-graph calculations | BSD-3-Clause |

The optional `sentence-transformers` semantic extra is Apache-2.0. Any model artifact also has its own model-card license and must be reviewed before redistribution.

## Web runtime

| Package | Purpose | License |
| --- | --- | --- |
| React / React DOM | Web interface | MIT |
| Recharts | Quantitative charts | MIT |
| Radix Dialog, Tabs, Tooltip | Accessible interaction primitives | MIT |
| Lucide React | Interface icons | ISC |
| class-variance-authority | Component variants | Apache-2.0 |
| clsx / tailwind-merge | Class composition | MIT |

Vite, TypeScript, Tailwind CSS, Vitest, Testing Library, ESLint, and Playwright are development/build/test dependencies. Their licenses are recorded in package metadata and the OSS audit. No shadcn/ui, ReUI, Cult UI, Aceternity UI, or UI Tripled source code was copied into this repository; they were audited or used only as design references as documented in `docs/OSS_REUSE_AUDIT.md`.

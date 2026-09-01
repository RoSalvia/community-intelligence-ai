# Architecture

Community Intelligence AI is a local modular monolith. The Python engine owns every data contract, transformation, analytical rule, metric formula, evidence record, and report. A thin FastAPI adapter starts analyses and reads published reports. The React application presents those reports and never recomputes analytics in TypeScript.

```text
Telegram Desktop JSON ─┐
                       ├─> normalized dataset ─> deterministic pipeline ─> report.json
Synthetic generator ───┘                                               └─> evidence.jsonl
                                                                               │
browser <─ packaged React assets <─ loopback FastAPI adapter <─────────────────┘
```

The normalized dataset is the stable boundary. It contains messages plus optional campaigns, claims, outcomes, and annotations. Missing optional records produce capability status `not_available`; absent product methods produce `not_implemented`. Publication is create-only and uses private staging directories before an atomic no-replace rename.

Evidence is a first-class join contract. Important outputs retain evidence IDs linked to source messages or explicit analysis scopes, method, confidence semantics, and pending review status. The web evidence drawer reads these records directly.

The service binds to loopback. Analysis workspaces live under `~/.community-intelligence/analyses` by default or `COMMUNITY_INTELLIGENCE_DATA_DIR` when explicitly configured. The frontend production build is packaged inside the Python wheel so `community-intelligence serve` needs no Node.js at runtime.

V0.1 intentionally avoids a database, background queue, microservices, authentication, cloud object storage, and live Telegram sessions. These would add operational and privacy complexity without improving the current local research/product loop.

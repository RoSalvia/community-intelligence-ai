"""Offline controlled post-RRF ablation; immutable first-run candidate scores."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from knowledge_external_validation import ROOT, save, sha

from community_intelligence.evaluation import retrieval_metrics


def necessary_policy(items, when):
    """No relevance threshold; only verified, known, already-published sources."""
    eligible = []
    for item in items:
        if item["official_status"] != "verified_official" or item["status"] in {"draft", "unknown"}:
            continue
        if any(datetime.fromisoformat(item[k]) > when for k in ("published_at", "effective_from")):
            continue
        inactive = any(
            item[k] and datetime.fromisoformat(item[k]) <= when
            for k in ("effective_until", "superseded_at")
        )
        eligible.append({**item, "inactive": inactive})
    # Expired references remain inspectable; they are not current answer evidence.
    eligible.sort(key=lambda c: (c["inactive"], -c["rrf_score"]))
    return eligible[:5]


def main():
    base = ROOT / "data/generated/validation/ton-docs-v1/baseline-run-1"
    queries = ROOT / "docs/validation/ton-docs-v1/queries.json"
    assert (
        sha(queries.read_bytes())
        == "e05e26672a7847de9a411902ff5ea1707a5de9f6e84e1f712562b4fe0593241b"
    )
    rows = json.loads((base / "results.json").read_text())
    with sqlite3.connect(f"file:{base / 'eval.sqlite3'}?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        metadata = {
            r["chunk_id"]: dict(r)
            for r in con.execute(
                "SELECT c.chunk_id, s.official_status, r.status, r.published_at, r.effective_from, "
                "r.effective_until, r.superseded_at FROM knowledge_chunks c "
                "JOIN knowledge_revisions r USING(revision_id) "
                "JOIN knowledge_sources s ON c.source_id=s.source_id"
            )
        }
    cases = []
    for row in rows:
        q = row["question"]
        pool = [{**c, **metadata[c["chunk_id"]]} for c in row["candidate_pool"]]
        selected = necessary_policy(pool, datetime.fromisoformat(row["result"]["as_of_time"]))
        cases.append(
            {
                "id": q["id"],
                "query": q["query"],
                "language": q["language"],
                "gold": q["gold"],
                "current_pipeline": row["metrics"],
                "raw_rrf": row["prepolicy_metrics"],
                "necessary_policy": retrieval_metrics(q["gold"], [c["ref"] for c in selected]),
                "current_top5": row["actual_top_k"],
                "raw_top5": row["prepolicy_rrf_top5"],
                "necessary_top5": selected,
            }
        )
    positives = [c for c in cases if c["gold"]]
    metrics = {
        name: {
            m: sum(c[name][m] for c in positives) / len(positives)
            for m in ("recall_at_5", "mrr_at_5", "ndcg_at_5", "hit_at_5")
        }
        for name in ("current_pipeline", "raw_rrf", "necessary_policy")
    }
    output = ROOT / "docs/validation/m2-1/post_rrf_ablation_controlled.json"
    if output.exists():
        raise SystemExit("Refusing to overwrite ablation evidence")
    save(
        output,
        {
            "query_sha256": sha(queries.read_bytes()),
            "baseline_results_sha256": sha((base / "results.json").read_bytes()),
            "method": (
                "Same stored lexical/semantic candidates and scores, original body-only index. "
                "Only post-RRF selection differs. No answer-layer conclusions from this "
                "offline retrieval ablation."
            ),
            "N": len(cases),
            "answerable_N": len(positives),
            "metrics": metrics,
            "cases": cases,
        },
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

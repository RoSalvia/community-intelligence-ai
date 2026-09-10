#!/usr/bin/env python3
"""Compare current Top20 with one-slot, rank-preserving source diversity."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from m2_2_reranker_experiment import DATASETS, _percentile
from sqlalchemy import select

from community_intelligence.application.knowledge import KnowledgeService, _terms
from community_intelligence.application.knowledge_answer import JsonAnswerProvider
from community_intelligence.evaluation import retrieval_metrics
from community_intelligence.infrastructure.database import Database, workspaces
from community_intelligence.semantic import SentenceTransformerProvider

ROOT = Path(__file__).resolve().parents[2]


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _when(question: dict, fallback: str) -> datetime:
    return datetime.fromisoformat((question.get("as_of_time") or fallback).replace("Z", "+00:00"))


def _ordered(
    service: KnowledgeService,
    workspace_id: str,
    query: str,
    when: datetime,
    depth: int,
) -> list[dict]:
    terms = _terms(query)
    lexical = service._lexical(terms, depth, workspace_id)
    semantic = service._semantic(query, workspace_id, depth)
    fused = service._rrf(lexical, list(semantic))
    candidates = service._load_candidates(workspace_id, fused)
    for item in candidates:
        item["temporal_state"] = service._temporal_state(item, when)
        item["retrieval_channels"] = int(item["chunk_id"] in lexical) + int(
            item["chunk_id"] in semantic
        )
    return service._select_candidates(candidates, fused, len(candidates))


def source_diverse(base: list[dict], deeper: list[dict], limit: int = 20) -> list[dict]:
    """Reserve one slot for an unseen source only when one source owns a majority."""
    return KnowledgeService._source_diverse_candidates(base, deeper, limit)


def _payload(pool: list[dict]) -> list[dict]:
    return [
        {
            key: item.get(key)
            for key in (
                "chunk_id",
                "title",
                "source_type",
                "section",
                "parent_heading",
                "text",
                "temporal_state",
            )
        }
        for item in pool
    ]


def _rerank(provider: JsonAnswerProvider, query: str, pool: list[dict]) -> tuple[list[dict], dict]:
    started = time.perf_counter()
    try:
        ranking, receipt = provider.rerank(query, _payload(pool))
    except (RuntimeError, TypeError, ValueError):
        return pool[:5], {
            "status": "provider_error",
            "latency_ms": (time.perf_counter() - started) * 1000,
        }
    valid = KnowledgeService._validated_ranking(
        ranking, [item["chunk_id"] for item in pool]
    )
    if valid is None:
        return pool[:5], {**receipt, "status": "invalid_response"}
    by_id = {item["chunk_id"]: item for item in pool}
    return [by_id[chunk_id] for chunk_id in valid[:5]], {**receipt, "status": "applied"}


def _summary(rows: list[dict], arm: str) -> dict:
    positives = [row for row in rows if row["question"]["gold"]]

    def aggregate(subset: list[dict]) -> dict:
        return {
            "N": len(subset),
            **{
                metric: statistics.fmean(row[arm]["metrics"][metric] for row in subset)
                for metric in ("hit_at_5", "recall_at_5", "mrr", "ndcg_at_5")
            },
        }

    return {
        "overall": aggregate(positives),
        "multi_fact": aggregate(
            [
                row
                for row in positives
                if len(row["question"]["gold"]) > 1
                or len(row["question"].get("required_context", [])) > 1
            ]
        ),
        "long_document": aggregate([row for row in positives if row["long_document"]]),
        "cross_language": aggregate(
            [row for row in positives if "cross_language" in row["question"]["type"]]
        ),
        "pool": {
            "mean_unique_sources": statistics.fmean(row[arm]["unique_sources"] for row in rows),
            "mean_dominant_source_share": statistics.fmean(
                row[arm]["dominant_source_share"] for row in rows
            ),
        },
        "reranker": {
            "calls": sum(not row[arm].get("reused") for row in rows),
            "fallbacks": sum(row[arm]["receipt"]["status"] != "applied" for row in rows),
            "p50_latency_ms": statistics.median(
                row[arm]["receipt"].get("latency_ms", 0) for row in rows
            ),
            "p95_latency_ms": _percentile(
                [row[arm]["receipt"].get("latency_ms", 0) for row in rows], 0.95
            ),
        },
    }


def run(output: Path, model_dir: Path) -> None:
    if (output / "results.json").exists():
        raise SystemExit("Refusing to overwrite a completed experiment")
    provider = JsonAnswerProvider.configured()
    if provider is None:
        raise RuntimeError("Explicit answer provider configuration is required")
    embedder = SentenceTransformerProvider(model_dir)
    rows = []
    for dataset, (prior_run, query_path) in DATASETS.items():
        questions = json.loads(query_path.read_text())["queries"]
        prior_rows = {
            row["question"]["id"]: row
            for row in json.loads((prior_run / "results.json").read_text())
        }
        chunks = json.loads((prior_run / "chunks.json").read_text())
        source_sizes = Counter(item["source_id"] for item in chunks.values())
        database = Database(prior_run / "eval.sqlite3")
        service = KnowledgeService(
            database=database,
            artifact_root=prior_run / "knowledge",
            embedder=embedder,
            answerer=provider,
        )
        with database.engine.connect() as connection:
            workspace_id = connection.scalar(select(workspaces.c.workspace_id))
        if workspace_id is None:
            raise RuntimeError("Validation workspace missing")
        for question in questions:
            fallback = prior_rows[question["id"]]["result"]["as_of_time"]
            when = _when(question, fallback)
            current_pool = _ordered(service, workspace_id, question["query"], when, 20)[:20]
            deep_pool = _ordered(service, workspace_id, question["query"], when, 40)
            diverse_pool = source_diverse(current_pool, deep_pool)
            current_top5, current_receipt = _rerank(provider, question["query"], current_pool)
            if [item["chunk_id"] for item in diverse_pool] == [
                item["chunk_id"] for item in current_pool
            ]:
                diverse_top5, diverse_receipt = current_top5, current_receipt
                reused = True
            else:
                diverse_top5, diverse_receipt = _rerank(
                    provider, question["query"], diverse_pool
                )
                reused = False
            gold_sources = {
                chunk["source_id"] for chunk in chunks.values() if chunk["ref"] in question["gold"]
            }
            row = {
                "dataset": dataset,
                "question": question,
                "long_document": any(source_sizes[source] >= 50 for source in gold_sources),
            }
            for arm, pool, top5, receipt in (
                ("current", current_pool, current_top5, current_receipt),
                ("source_diverse", diverse_pool, diverse_top5, diverse_receipt),
            ):
                ranked = [chunks[item["chunk_id"]]["ref"] for item in top5]
                counts = Counter(item["source_id"] for item in pool)
                row[arm] = {
                    "pool": [chunks[item["chunk_id"]]["ref"] for item in pool],
                    "top5": ranked,
                    "metrics": retrieval_metrics(question["gold"], ranked),
                    "unique_sources": len(counts),
                    "dominant_source_share": max(counts.values()) / len(pool) if pool else 0,
                    "receipt": receipt,
                    "reused": arm == "source_diverse" and reused,
                }
            rows.append(row)
            save(output / "partial_results.json", rows)
            print(dataset, question["id"], "changed" if not reused else "unchanged", flush=True)
    save(output / "results.json", rows)
    save(
        output / "summary.json",
        {arm: _summary(rows, arm) for arm in ("current", "source_diverse")},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve(), args.model_dir.resolve())

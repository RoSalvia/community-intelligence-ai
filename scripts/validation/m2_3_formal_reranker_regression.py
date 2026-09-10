#!/usr/bin/env python3
"""Run the locked TON sets through the formal RRF and reranker product paths."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from datetime import datetime
from pathlib import Path

from knowledge_external_validation import baseline_hashes, save, sha
from m2_2_reranker_experiment import DATASETS, JUDGE_PROMPT, JsonCompletion, _percentile
from sqlalchemy import select

from community_intelligence.application.knowledge import KnowledgeService
from community_intelligence.application.knowledge_answer import JsonAnswerProvider
from community_intelligence.evaluation import retrieval_metrics
from community_intelligence.infrastructure.database import Database, workspaces
from community_intelligence.semantic import SentenceTransformerProvider

ROOT = Path(__file__).resolve().parents[2]
RETRIEVAL_METRICS = (
    "hit_at_1",
    "hit_at_3",
    "hit_at_5",
    "precision_at_1",
    "precision_at_3",
    "precision_at_5",
    "recall_at_1",
    "recall_at_3",
    "recall_at_5",
    "r_precision",
    "mrr",
    "ndcg_at_5",
)


class AnswerOnlyProvider:
    """Validation control: retain answer calls while intentionally omitting rerank."""

    def __init__(self) -> None:
        provider = JsonAnswerProvider.configured()
        if provider is None:
            raise RuntimeError("Explicit answer provider configuration is required")
        self.provider = provider

    @property
    def last_receipt(self) -> dict:
        return self.provider.last_receipt

    def assess(self, query: str, evidence: list[dict]) -> dict:
        return self.provider.assess(query, evidence)

    def repair(self, query: str, evidence: list[dict], issues: list[str]) -> dict:
        return self.provider.repair(query, evidence, issues)


def _configured_provider() -> JsonAnswerProvider:
    provider = JsonAnswerProvider.configured()
    if provider is None:
        raise RuntimeError("Explicit answer provider configuration is required")
    return provider


def _refs(result: dict, diagnostics: dict[str, dict]) -> list[str]:
    return [diagnostics[item["chunk_id"]]["ref"] for item in result["citations"]]


def _product_run(
    prior_run: Path,
    workspace_id: str,
    embedder,
    question: dict,
    diagnostics: dict[str, dict],
    *,
    reranker: bool,
) -> dict:
    answerer = _configured_provider() if reranker else AnswerOnlyProvider()
    service = KnowledgeService(
        database=Database(prior_run / "eval.sqlite3"),
        artifact_root=prior_run / "knowledge",
        embedder=embedder,
        answerer=answerer,
    )
    as_of = question.get("as_of_time")
    started = time.perf_counter()
    result = service.query(
        workspace_id,
        question["query"],
        as_of_time=datetime.fromisoformat(as_of.replace("Z", "+00:00")) if as_of else None,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    answer_receipt = answerer.last_receipt.copy()
    ranked = _refs(result, diagnostics)
    return {
        "retrieval": retrieval_metrics(question["gold"], ranked),
        "selected_refs": ranked,
        "answer": result,
        "answer_receipt": answer_receipt,
        "latency_ms": latency_ms,
    }


def _slice(question: dict, name: str) -> bool:
    if name in {"en", "zh", "es"}:
        return question["language"] == name
    if name == "cross_language":
        return "cross_language" in question["type"]
    if name == "noisy":
        return question["type"] == "colloquial_noisy"
    if name == "multi_fact":
        return len(question["gold"]) > 1 or len(question.get("required_context", [])) > 1
    raise KeyError(name)


def _retrieval_summary(rows: list[dict], arm: str) -> dict:
    positives = [row for row in rows if row["question"]["gold"]]

    def aggregate(subset: list[dict]) -> dict:
        result = {"N": len(subset)}
        for metric in RETRIEVAL_METRICS:
            label = metric.replace("hit_at", "hit_rate_at")
            result[label] = statistics.fmean(row[arm]["retrieval"][metric] for row in subset)
        result["mean_gold_cardinality"] = statistics.fmean(
            len(row["question"]["gold"]) for row in subset
        )
        result["precision_at_5_natural_ceiling"] = statistics.fmean(
            min(5, len(row["question"]["gold"])) / 5 for row in subset
        )
        return result

    return {
        "overall": aggregate(positives),
        "by_language": {
            name: aggregate([row for row in positives if _slice(row["question"], name)])
            for name in ("en", "zh", "es")
        },
        "slices": {
            name: aggregate([row for row in positives if _slice(row["question"], name)])
            for name in ("cross_language", "noisy", "multi_fact")
        },
    }


def _answer_summary(rows: list[dict], arm: str) -> dict:
    positives = [row for row in rows if row["question"]["gold"]]
    grounded = [
        row for row in positives if row[arm]["answer"]["answer_status"] == "grounded"
    ]
    cited = [row for row in rows if row[arm]["answer"]["claims"]]
    insufficient = [
        row for row in rows if row["question"]["expected_status"] == "insufficient_evidence"
    ]
    no_answer = [
        row
        for row in rows
        if row["question"]["expected_status"] == "no_authoritative_source"
    ]
    return {
        "complete_answer_rate": {
            "count": sum(row["judgment"][arm]["grade"] == "complete" for row in positives),
            "N": len(positives),
        },
        "false_grounded_rate": {
            "count": sum(row["judgment"][arm]["grade"] != "complete" for row in grounded),
            "N": len(grounded),
        },
        "insufficient_evidence_accuracy": {
            "count": sum(
                row[arm]["answer"]["answer_status"] == "insufficient_evidence"
                for row in insufficient
            ),
            "N": len(insufficient),
        },
        "no_answer_accuracy": {
            "count": sum(
                row[arm]["answer"]["answer_status"] == "no_authoritative_source"
                for row in no_answer
            ),
            "N": len(no_answer),
        },
        "citation_validity": {
            "count": sum(
                row[arm]["answer"]["grounding"]["citation_valid"] is True for row in cited
            ),
            "N": len(cited),
        },
        "citation_repair_rate": {
            "count": sum(
                bool(row[arm]["answer_receipt"].get("repair_attempted")) for row in rows
            ),
            "N": len(rows),
        },
        "answer_provider_error_rate": {
            "count": sum(
                row[arm]["answer"]["answerability"]["status"] == "provider_error"
                for row in rows
            ),
            "N": len(rows),
        },
        "reranker_fallback_rate": {
            "count": sum(
                row[arm]["answer"]["retrieval"]["reranker"]["fallback"] for row in rows
            ),
            "N": len(rows),
        },
    }


def _usage(row: dict, arm: str) -> dict[str, float]:
    answer = row[arm]["answer_receipt"]
    rerank = row[arm]["answer"]["retrieval"]["reranker"]
    receipts = [answer] + ([rerank] if rerank["status"] == "applied" else [])
    usage = {
        key: sum(float(receipt.get("usage", {}).get(key, 0)) for receipt in receipts)
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
        )
    }
    calls = float(answer.get("attempt_count", 0)) + (1 if rerank["status"] == "applied" else 0)
    evidence_chars = float(answer.get("evidence_chars", 0)) + (
        float(rerank.get("evidence_chars", 0)) if rerank["status"] == "applied" else 0
    )
    return {
        **usage,
        "remote_calls": calls,
        "remote_evidence_chars": evidence_chars,
        "estimated_remote_evidence_tokens": math.ceil(evidence_chars / 4),
        "remote_request_chars": float(answer.get("request_chars", 0))
        + (float(rerank.get("request_chars", 0)) if rerank["status"] == "applied" else 0),
    }


def _runtime_summary(rows: list[dict], arm: str) -> dict:
    usages = [_usage(row, arm) for row in rows]
    latencies = [row[arm]["latency_ms"] for row in rows]
    return {
        "N": len(rows),
        "per_query_mean": {
            key: statistics.fmean(item[key] for item in usages) for key in usages[0]
        },
        "latency_ms": {
            "p50": statistics.median(latencies),
            "p95": _percentile(latencies, 0.95),
        },
        "remote_evidence_chars": {
            "p50": statistics.median(item["remote_evidence_chars"] for item in usages),
            "p95": _percentile(
                [item["remote_evidence_chars"] for item in usages], 0.95
            ),
        },
        "remote_evidence_token_note": (
            "Evidence-only tokens are estimated as chars/4; model-reported prompt_tokens in "
            "per_query_mean are authoritative for total input."
        ),
    }


def run(output: Path, model_dir: Path) -> None:
    if (output / "results.json").exists():
        raise SystemExit("Refusing to overwrite completed regression")
    output.mkdir(parents=True, exist_ok=True)
    partial_path = output / "partial_results.json"
    rows = json.loads(partial_path.read_text()) if partial_path.exists() else []
    rows = [
        row
        for row in rows
        if all("reranker" in row[arm]["answer"].get("retrieval", {}) for arm in ("rrf", "reranker"))
    ]
    completed = {(row["dataset"], row["question"]["id"]) for row in rows}
    judge = JsonCompletion()
    receipt = {
        "started_at": datetime.now().astimezone().isoformat(),
        "resumed_rows": len(rows),
        "product_hashes": baseline_hashes(),
        "runner_sha256": sha(Path(__file__).read_bytes()),
        "model_dir_manifest": sha(
            (model_dir / "community_intelligence_manifest.json").read_bytes()
        ),
        "datasets": {},
        "contract": {
            "queries_gold": "locked unchanged TON regression + holdout",
            "candidate_generation": "FTS5 BM25 Top20 + multilingual embedding Top20 + RRF",
            "metadata_policy": "necessary authority/validity/time policy",
            "candidate_pool": "bounded policy Top20",
            "reranker": "formal validated multilingual listwise v1",
            "answer": "material-facts-evidence-v2",
            "chunk": "structure-v1 180/30",
            "neighbors": 1,
        },
    }
    embedder = SentenceTransformerProvider(model_dir)
    for dataset, (prior_run, queries_path) in DATASETS.items():
        questions = json.loads(queries_path.read_text())["queries"]
        diagnostics = {
            chunk_id: {"ref": item["ref"]}
            for chunk_id, item in json.loads((prior_run / "chunks.json").read_text()).items()
        }
        receipt["datasets"][dataset] = {
            "query_sha256": sha(queries_path.read_bytes()),
            "N": len(questions),
        }
        database = Database(prior_run / "eval.sqlite3")
        with database.engine.connect() as connection:
            workspace_id = connection.scalar(select(workspaces.c.workspace_id))
        if workspace_id is None:
            raise RuntimeError("Validation workspace missing")
        for question in questions:
            if (dataset, question["id"]) in completed:
                continue
            rrf = _product_run(
                prior_run,
                workspace_id,
                embedder,
                question,
                diagnostics,
                reranker=False,
            )
            reranker = _product_run(
                prior_run,
                workspace_id,
                embedder,
                question,
                diagnostics,
                reranker=True,
            )
            grading, grading_receipt = judge.call(
                JUDGE_PROMPT,
                {
                    "question": question["query"],
                    "rubric": question["rubric"],
                    "rrf": {
                        "status": rrf["answer"]["answer_status"],
                        "claims": rrf["answer"]["claims"],
                        "missing_facts": rrf["answer"]["answerability"]["missing_facts"],
                    },
                    "reranker": {
                        "status": reranker["answer"]["answer_status"],
                        "claims": reranker["answer"]["claims"],
                        "missing_facts": reranker["answer"]["answerability"]["missing_facts"],
                    },
                },
                max_tokens=1200,
            )
            normalized = {"rrf": grading["current"], "reranker": grading["reranker"]}
            rows.append(
                {
                    "dataset": dataset,
                    "question": question,
                    "rrf": rrf,
                    "reranker": reranker,
                    "judgment": normalized,
                    "judge_receipt": grading_receipt,
                }
            )
            save(partial_path, rows)
            print(
                dataset,
                question["id"],
                normalized["rrf"]["grade"],
                normalized["reranker"]["grade"],
                reranker["answer"]["retrieval"]["reranker"]["status"],
                flush=True,
            )
    receipt.update(completed_at=datetime.now().astimezone().isoformat(), row_count=len(rows))
    metrics = {
        arm: {
            "retrieval": _retrieval_summary(rows, arm),
            "answer": _answer_summary(rows, arm),
            "runtime": _runtime_summary(rows, arm),
        }
        for arm in ("rrf", "reranker")
    }
    metrics["judge_evaluation_only"] = {
        "calls": len(rows),
        "total_tokens": sum(
            row["judge_receipt"].get("usage", {}).get("total_tokens", 0) for row in rows
        ),
        "excluded_from_product_runtime": True,
    }
    save(output / "results.json", rows)
    save(output / "receipt.json", receipt)
    save(output / "metrics.json", metrics)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve(), args.model_dir.resolve())

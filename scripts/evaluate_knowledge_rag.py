#!/usr/bin/env python3
"""Run the reproducible generic M2 retrieval and answer-status benchmark."""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from community_intelligence.application.data_foundation import DataFoundationService
from community_intelligence.application.knowledge import (
    AUTHORITY_POLICY_VERSION,
    CHUNK_STRATEGY_VERSION,
    INDEX_VERSION,
    ChunkConfig,
    KnowledgeService,
    SourceInput,
)
from community_intelligence.semantic import MODEL_ID, MODEL_REVISION, SentenceTransformerProvider

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "knowledge"
DEFAULT_MODEL = (
    ROOT / "data" / "generated" / "models" / ("paraphrase-multilingual-MiniLM-L12-v2-e8f8c211")
)
PROVENANCE = {
    "source_type": "human-confirmed",
    "authority_level": "human-confirmed",
    "official_status": "human-confirmed",
    "published_at": "source-provided",
    "validity": "human-confirmed",
}


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate(config: ChunkConfig, neighbors: int, embedder: object | None) -> dict[str, object]:
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="ci-m2-eval-") as temporary:
        root = Path(temporary)
        now = datetime(2026, 9, 10, 12, tzinfo=UTC)
        foundation = DataFoundationService(
            database_path=root / "eval.sqlite3",
            artifact_root=root / "runs",
            clock=lambda: now,
        )
        workspace_id = foundation.create_workspace("Generic Fixture Project")["workspace_id"]
        service = KnowledgeService(
            database=foundation.database,
            artifact_root=root / "knowledge",
            clock=lambda: now,
            embedder=embedder,
            chunk_config=config,
        )
        source_ids: dict[str, str] = {}
        for item in manifest["sources"]:
            created = service.add_source(
                workspace_id,
                SourceInput(
                    title=item["title"],
                    source_type=item["source_type"],
                    source_channel=item["source_channel"],
                    content=(FIXTURES / item["file"]).read_text(encoding="utf-8"),
                    filename=item["file"],
                    canonical_url=f"https://fixtures.invalid/{item['key']}",
                    language=item["language"],
                    project_scope="generic-fixture-project",
                    authority_level="official",
                    official_status="verified_official",
                    verification_method="curated fixture metadata",
                    published_at=parse_time(item["published_at"]),
                    effective_from=parse_time(item["effective_from"]),
                    effective_until=(
                        parse_time(item["effective_until"]) if item.get("effective_until") else None
                    ),
                    source_timezone=str(parse_time(item["published_at"]).tzinfo),
                    status=item["status"],
                    metadata_provenance=PROVENANCE,
                    semantic_tags=item.get("semantic_tags", {}),
                ),
            )
            source_ids[item["key"]] = created["source_id"]

        rows = []
        for golden in manifest["golden_queries"]:
            result = service.query(
                workspace_id,
                golden["query"],
                as_of_time=parse_time(golden["as_of_time"]),
                top_k=5,
                neighbor_count=neighbors,
            )
            expected = {
                (source_ids[key], section)
                for key, section in zip(
                    golden["expected_sources"], golden["expected_sections"], strict=True
                )
            }
            returned_targets = list(
                dict.fromkeys(
                    (citation["source_id"], citation["section"]) for citation in result["citations"]
                )
            )
            returned = list(
                dict.fromkeys(citation["source_id"] for citation in result["citations"])
            )
            hits = expected & set(returned_targets)
            recall = len(hits) / len(expected) if expected else int(not returned)
            reciprocal_rank = 0.0
            for rank, target in enumerate(returned_targets, 1):
                if target in expected:
                    reciprocal_rank = 1 / rank
                    break
            ideal = sum(1 / math.log2(rank + 1) for rank in range(1, len(expected) + 1))
            dcg = sum(
                1 / math.log2(rank + 1)
                for rank, target in enumerate(returned_targets, 1)
                if target in expected
            )
            citation_valid = all(
                service.get_chunk(citation["chunk_id"])["revision_id"] == citation["revision_id"]
                for citation in result["citations"]
            )
            rows.append(
                {
                    "id": golden["id"],
                    "language": golden["language"],
                    "expected_status": golden["expected_status"],
                    "actual_status": result["answer_status"],
                    "recall_at_5": recall,
                    "mrr": reciprocal_rank,
                    "ndcg_at_5": dcg / ideal if ideal else float(not returned),
                    "citation_valid": citation_valid,
                    "retrieval_scores": [
                        citation["retrieval_scores"] for citation in result["citations"]
                    ],
                    "returned_source_keys": [
                        next(key for key, value in source_ids.items() if value == source_id)
                        for source_id in returned
                    ],
                }
            )

    count = len(rows)
    status_accuracy = sum(row["expected_status"] == row["actual_status"] for row in rows) / count
    expected_with_sources = [
        row for row in rows if row["expected_status"] != "no_authoritative_source"
    ]
    no_answer = [row for row in rows if row["expected_status"] == "no_authoritative_source"]
    insufficient = [row for row in rows if row["expected_status"] == "insufficient_evidence"]
    conflicts = [row for row in rows if row["expected_status"] == "conflict"]
    outdated = [row for row in rows if row["expected_status"] == "outdated_only"]
    cross = [row for row in rows if row["language"] == "cross"]

    def accuracy(items: list[dict[str, object]]) -> float:
        return (
            sum(item["expected_status"] == item["actual_status"] for item in items) / len(items)
            if items
            else 0.0
        )

    return {
        "configuration": {
            "chunk_strategy": CHUNK_STRATEGY_VERSION,
            "max_tokens": config.max_tokens,
            "overlap_tokens": config.overlap_tokens,
            "neighbor_count": neighbors,
        },
        "retrieval": {
            "recall_at_5": sum(row["recall_at_5"] for row in rows) / count,
            "mrr": sum(row["mrr"] for row in expected_with_sources) / len(expected_with_sources),
            "ndcg_at_5": sum(row["ndcg_at_5"] for row in rows) / count,
            "cross_language_recall_at_5": sum(row["recall_at_5"] for row in cross) / len(cross),
        },
        "answer": {
            "answer_status_accuracy": status_accuracy,
            "citation_validity": sum(row["citation_valid"] for row in rows) / count,
            "grounded_answer_accuracy": accuracy(
                [row for row in rows if row["expected_status"] == "grounded"]
            ),
            "no_answer_abstention_accuracy": accuracy(no_answer),
            "insufficient_evidence_accuracy": accuracy(insufficient),
            "conflict_detection_accuracy": accuracy(conflicts),
            "outdated_detection_accuracy": accuracy(outdated),
            "outdated_source_error_rate": 1 - accuracy(outdated),
        },
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()
    embedder = SentenceTransformerProvider(args.model_dir) if args.model_dir.is_dir() else None
    configurations = [
        (ChunkConfig(max_tokens=120, overlap_tokens=0), 0),
        (ChunkConfig(max_tokens=180, overlap_tokens=30), 1),
        (ChunkConfig(max_tokens=260, overlap_tokens=40), 1),
    ]
    results = [evaluate(config, neighbors, embedder) for config, neighbors in configurations]
    report = {
        "dataset_version": "generic-knowledge-fixtures-v1",
        "N": 12,
        "language_distribution": {"en": 8, "zh": 1, "es": 2, "cross": 1},
        "document_type_distribution": {
            "whitepaper": 1,
            "product_docs": 1,
            "faq": 2,
            "announcement_or_notice": 2,
            "official_blog": 1,
            "release_notes": 1,
            "manual_note": 1,
        },
        "embedding_model": MODEL_ID if embedder else None,
        "embedding_revision": MODEL_REVISION if embedder else None,
        "index_version": INDEX_VERSION,
        "authority_policy_version": AUTHORITY_POLICY_VERSION,
        "results": results,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

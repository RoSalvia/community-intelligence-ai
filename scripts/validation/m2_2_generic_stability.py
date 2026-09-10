#!/usr/bin/env python3
"""Repeat the fixed generic 180/30/±1 gate without changing its fixtures."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from evaluate_knowledge_rag import DEFAULT_MODEL, evaluate
from knowledge_external_validation import baseline_hashes, save

from community_intelligence.application.knowledge import ChunkConfig
from community_intelligence.semantic import SentenceTransformerProvider


def run(output: Path, repetitions: int) -> None:
    if output.exists():
        raise SystemExit("Refusing to overwrite generic stability result")
    model = SentenceTransformerProvider(DEFAULT_MODEL)
    runs = []
    for number in range(1, repetitions + 1):
        result = evaluate(ChunkConfig(180, 30), 1, model)
        runs.append(
            {
                "run": number,
                "retrieval": result["retrieval"],
                "answer": result["answer"],
                "cases": [
                    {
                        key: case[key]
                        for key in (
                            "id",
                            "expected_status",
                            "actual_status",
                            "recall_at_5",
                            "mrr",
                            "ndcg_at_5",
                        )
                    }
                    for case in result["cases"]
                ],
            }
        )
        print(number, result["answer"]["answer_status_accuracy"], flush=True)
    save(
        output,
        {
            "dataset": "generic-knowledge-fixtures-v1",
            "completed_at": datetime.now(UTC).isoformat(),
            "configuration": "structure-v1 180/30, neighbor=1",
            "product_hashes": baseline_hashes(),
            "runs": runs,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    run(args.output, args.repetitions)

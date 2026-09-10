"""Version-independent retrieval evaluation metrics."""

from __future__ import annotations

import math


def retrieval_metrics(gold: list[str], ranked: list[str]) -> dict[str, float | int | None]:
    if not gold:
        return {
            **{
                f"{metric}_at_{k}": None
                for metric in ("hit", "precision", "recall")
                for k in (1, 3, 5)
            },
            "r_precision": None,
            "mrr": None,
            "mrr_at_5": None,
            "ndcg_at_5": None,
        }
    expected = set(gold)
    ranked = list(dict.fromkeys(ranked))
    top_five = ranked[:5]
    ranks = [rank for rank, target in enumerate(top_five, 1) if target in expected]
    dcg = sum(1 / math.log2(rank + 1) for rank in ranks)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(5, len(expected)) + 1))
    result: dict[str, float | int | None] = {
        "r_precision": len(expected.intersection(ranked[: len(expected)])) / len(expected),
        "mrr": 1 / min(ranks) if ranks else 0,
        "mrr_at_5": 1 / min(ranks) if ranks else 0,
        "ndcg_at_5": dcg / ideal,
    }
    for k in (1, 3, 5):
        hits = len(expected.intersection(ranked[:k]))
        result.update(
            {
                f"hit_at_{k}": int(hits > 0),
                f"precision_at_{k}": hits / k,
                f"recall_at_{k}": hits / len(expected),
            }
        )
    return result

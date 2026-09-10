from community_intelligence.evaluation import retrieval_metrics


def test_retrieval_metrics_cover_fixed_k_and_gold_cardinality():
    metrics = retrieval_metrics(["a", "b"], ["x", "a", "b", "y", "z"])

    assert metrics["hit_at_1"] == 0
    assert metrics["hit_at_3"] == metrics["hit_at_5"] == 1
    assert metrics["precision_at_1"] == 0
    assert metrics["precision_at_3"] == 2 / 3
    assert metrics["precision_at_5"] == 2 / 5
    assert metrics["recall_at_1"] == 0
    assert metrics["recall_at_3"] == metrics["recall_at_5"] == 1
    assert metrics["r_precision"] == 0.5
    assert metrics["mrr"] == metrics["mrr_at_5"] == 0.5
    assert 0 < metrics["ndcg_at_5"] < 1


def test_retrieval_metrics_are_not_defined_for_abstention_gold():
    metrics = retrieval_metrics([], ["a"])

    assert all(value is None for value in metrics.values())

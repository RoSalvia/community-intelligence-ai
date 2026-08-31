from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pandas as pd
import pytest

from community_intelligence.metrics import metric_catalog, validate_metrics

CATALOG_NAMES = (
    "campaign_discussion_share",
    "community_response_latency",
    "conversation_propagation_depth",
    "meaningful_interaction_ratio",
    "organic_project_mention_rate",
    "peer_support_ratio",
    "semantic_campaign_coverage",
    "semantic_drift_rate",
    "unanswered_question_rate",
    "user_to_user_interaction_ratio",
)


def _metric_frame(**metrics: list[float]) -> pd.DataFrame:
    count = len(next(iter(metrics.values())))
    return pd.DataFrame(
        {
            "observation_id": [f"obs-{index:02d}" for index in range(count)],
            "community_id": [f"community-{index % 3}" for index in range(count)],
            "language": [("en", "es", "zh")[index % 3] for index in range(count)],
            **metrics,
        }
    )


def _outcome_frame(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "observation_id": [f"obs-{index:02d}" for index in range(len(values))],
            "retention": values,
        }
    )


def _result(results: tuple, metric_name: str):
    return next(result for result in results if result.metric_name == metric_name)


def test_catalog_has_required_metrics_and_complete_business_contracts() -> None:
    catalog = metric_catalog()

    assert tuple(catalog) == CATALOG_NAMES
    for name, definition in catalog.items():
        assert definition.metric_name == name
        assert definition.business_meaning.strip()
        assert definition.formula.strip()
        assert definition.denominator.strip()
        assert definition.required_fields
        assert definition.unit_of_analysis.strip()
        assert definition.time_window.strip()
        assert definition.why_it_may_matter.strip()
        assert definition.biases
        assert definition.limitations
        assert definition.evidence_requirements
        assert "caus" not in definition.why_it_may_matter.lower()

    assert (
        catalog["peer_support_ratio"].denominator
        == "all answered user questions in the analysis window"
    )
    assert (
        "source message"
        in " ".join(catalog["semantic_campaign_coverage"].evidence_requirements).lower()
    )


def test_catalog_and_definition_are_deeply_immutable() -> None:
    catalog = metric_catalog()
    definition = catalog["peer_support_ratio"]

    with pytest.raises(TypeError):
        catalog["changed"] = definition
    with pytest.raises(FrozenInstanceError):
        definition.formula = "changed"
    with pytest.raises(TypeError):
        definition.limitations[0] = "changed"


@pytest.mark.parametrize(
    ("values", "expected_reason"),
    [
        ([1.0] * 8, "zero_variance"),
        ([np.nan] * 8, "all_missing"),
        ([1.0, 2.0, np.inf, 4.0, 5.0, 6.0, 7.0, 8.0], "nonfinite_values"),
        ([1.0, 2.0, 3.0], "insufficient_sample"),
    ],
)
def test_invalid_metric_series_is_rejected(values: list[float], expected_reason: str) -> None:
    results = validate_metrics(
        _metric_frame(candidate_metric=values),
        _outcome_frame(list(range(len(values)))),
        metric_columns=("candidate_metric",),
        outcome_columns=("retention",),
        minimum_sample_size=5,
        synthetic=True,
    )

    result = results[0]
    assert result.status == "Rejected"
    assert expected_reason in result.reasons
    assert "association" in result.interpretation.lower()
    assert "causal" in result.interpretation.lower()


def test_partial_missingness_is_reported_and_finite_rows_are_analyzed() -> None:
    values = [0.0, 1.0, np.nan, 3.0, 4.0, 5.0, 6.0, 7.0]
    result = validate_metrics(
        _metric_frame(candidate_metric=values),
        _outcome_frame([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]),
        metric_columns=("candidate_metric",),
        outcome_columns=("retention",),
        minimum_sample_size=5,
        synthetic=True,
    )[0]

    assert result.sample_size == 8
    assert result.missing_count == 1
    assert result.missing_rate == pytest.approx(0.125)
    assert result.finite_sample_size == 7
    assert result.status == "Promising"


def test_perfect_synthetic_association_is_never_validated() -> None:
    values = [float(index) for index in range(10)]
    result = validate_metrics(
        _metric_frame(peer_support_ratio=values),
        _outcome_frame(values),
        metric_columns=("peer_support_ratio",),
        outcome_columns=("retention",),
        minimum_sample_size=5,
        synthetic=True,
    )[0]

    assert result.status == "Promising"
    assert result.status != "Validated"
    assert result.associations[0].spearman_rho == pytest.approx(1.0)
    assert result.associations[0].p_value <= 0.05
    assert result.associations[0].confidence_interval_95 == pytest.approx((1.0, 1.0))
    assert result.synthetic is True
    assert result.minimum_sample_size == 5
    assert result.promising_absolute_rho_threshold == pytest.approx(0.3)
    assert result.promising_p_value_threshold == pytest.approx(0.05)
    assert result.redundancy_absolute_rho_threshold == pytest.approx(0.9)
    assert "association" in result.interpretation.lower()
    assert "causality" in result.interpretation.lower()


def test_valid_metric_without_outcome_remains_candidate() -> None:
    result = validate_metrics(
        _metric_frame(candidate_metric=[0.0, 2.0, 1.0, 5.0, 3.0, 4.0]),
        None,
        metric_columns=("candidate_metric",),
        minimum_sample_size=5,
        synthetic=True,
    )[0]

    assert result.status == "Candidate"
    assert result.associations == ()
    assert "no_outcome_frame" in result.reasons


def test_redundant_metrics_are_reported_without_an_arbitrary_score() -> None:
    values = [float(index) for index in range(8)]
    results = validate_metrics(
        _metric_frame(metric_a=values, metric_b=[value * 10 for value in values]),
        _outcome_frame(list(reversed(values))),
        metric_columns=("metric_a", "metric_b"),
        outcome_columns=("retention",),
        minimum_sample_size=5,
        synthetic=True,
    )

    assert _result(results, "metric_a").redundant_with == ("metric_b",)
    assert _result(results, "metric_b").redundant_with == ("metric_a",)
    assert all(not hasattr(result, "score") for result in results)
    assert all(not hasattr(result, "weight") for result in results)


def test_cross_community_and_language_spread_is_calculated_when_available() -> None:
    frame = _metric_frame(candidate_metric=[0.0, 3.0, 6.0, 0.0, 3.0, 6.0])
    result = validate_metrics(
        frame,
        None,
        metric_columns=("candidate_metric",),
        minimum_sample_size=5,
        synthetic=True,
    )[0]

    assert result.community_spread is not None
    assert result.community_spread.group_count == 3
    assert result.community_spread.mean_range == pytest.approx(6.0)
    assert result.language_spread is not None
    assert result.language_spread.group_count == 3
    assert result.language_spread.mean_range == pytest.approx(6.0)


def test_results_are_deeply_immutable_and_deterministically_ordered() -> None:
    frame = _metric_frame(z_metric=[0, 1, 2, 3, 4, 5], a_metric=[5, 3, 4, 0, 2, 1])
    outcomes = _outcome_frame([0, 1, 2, 3, 4, 5])

    first = validate_metrics(
        frame,
        outcomes,
        metric_columns=("z_metric", "a_metric"),
        outcome_columns=("retention",),
        minimum_sample_size=5,
        synthetic=True,
    )
    second = validate_metrics(
        frame.sample(frac=1, random_state=7),
        outcomes.sample(frac=1, random_state=11),
        metric_columns=("a_metric", "z_metric"),
        outcome_columns=("retention",),
        minimum_sample_size=5,
        synthetic=True,
    )

    assert first == second
    assert tuple(result.metric_name for result in first) == ("a_metric", "z_metric")
    with pytest.raises(TypeError):
        first[0] = first[1]
    with pytest.raises(FrozenInstanceError):
        first[0].status = "Rejected"


def test_multiple_outcomes_are_sorted_and_invalid_outcome_is_diagnostic() -> None:
    values = [float(index) for index in range(8)]
    outcomes = _outcome_frame(values)
    outcomes["all_missing"] = np.nan
    outcomes["conversion"] = list(reversed(values))

    result = validate_metrics(
        _metric_frame(candidate_metric=values),
        outcomes,
        metric_columns=("candidate_metric",),
        outcome_columns=("retention", "all_missing", "conversion"),
        minimum_sample_size=5,
        synthetic=True,
    )[0]

    assert tuple(item.outcome_name for item in result.associations) == (
        "all_missing",
        "conversion",
        "retention",
    )
    assert result.associations[0].reason == "no_finite_pairs"
    assert result.associations[0].spearman_rho is None


def test_duplicate_observation_ids_are_rejected_instead_of_many_to_many_joined() -> None:
    metric_frame = _metric_frame(candidate_metric=[0, 1, 2, 3, 4, 5])
    metric_frame.loc[1, "observation_id"] = "obs-00"

    with pytest.raises(ValueError, match="unique observation_id"):
        validate_metrics(
            metric_frame,
            _outcome_frame([0, 1, 2, 3, 4, 5]),
            metric_columns=("candidate_metric",),
            outcome_columns=("retention",),
            minimum_sample_size=5,
            synthetic=True,
        )

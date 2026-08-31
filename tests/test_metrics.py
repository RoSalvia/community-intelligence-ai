from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pandas as pd
import pytest

from community_intelligence.campaign import SEMANTIC_COVERAGE_FORMULA
from community_intelligence.metrics import (
    adapt_metric_source,
    metric_catalog,
    validate_metrics,
)

OBSERVATION_KEYS = ("observation_id",)
ADAPTER_REASON_COLUMN = "adapter_diagnostic_reason"
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


def _metric_frame(**metrics: list[object]) -> pd.DataFrame:
    count = len(next(iter(metrics.values())))
    return pd.DataFrame(
        {
            "observation_id": [f"obs-{index:02d}" for index in range(count)],
            "community_id": [f"community-{index % 3}" for index in range(count)],
            "language": [("en", "es", "zh")[index % 3] for index in range(count)],
            **metrics,
        }
    )


def _outcome_frame(**outcomes: list[object]) -> pd.DataFrame:
    count = len(next(iter(outcomes.values())))
    return pd.DataFrame(
        {
            "observation_id": [f"obs-{index:02d}" for index in range(count)],
            **outcomes,
        }
    )


def _validate(
    metric_frame: pd.DataFrame,
    outcome_frame: pd.DataFrame | None,
    *,
    metric_columns: tuple[str, ...],
    outcome_columns: tuple[str, ...] | None = None,
    minimum_sample_size: int = 5,
    minimum_group_size: int = 2,
):
    return validate_metrics(
        metric_frame,
        outcome_frame,
        observation_key_columns=OBSERVATION_KEYS,
        metric_columns=metric_columns,
        outcome_columns=outcome_columns,
        minimum_sample_size=minimum_sample_size,
        minimum_group_size=minimum_group_size,
        synthetic=True,
    )


def _result(results: tuple, metric_name: str):
    return next(result for result in results if result.metric_name == metric_name)


def test_catalog_has_canonical_upstream_formula_contracts() -> None:
    catalog = metric_catalog()

    assert tuple(catalog) == CATALOG_NAMES
    assert catalog["semantic_campaign_coverage"].formula == SEMANTIC_COVERAGE_FORMULA
    assert "0.5" in " ".join(catalog["semantic_campaign_coverage"].limitations)
    assert "candidate design choice" in " ".join(catalog["semantic_campaign_coverage"].limitations)
    assert "moderator score" in " ".join(catalog["semantic_campaign_coverage"].limitations)
    assert catalog["conversation_propagation_depth"].formula == (
        "number of message nodes on the episode's longest reply path"
    )
    latency = catalog["community_response_latency"]
    assert latency.formula == (
        "sum of first direct moderator reply latency seconds / "
        "eligible real-user messages with a direct moderator reply"
    )
    assert latency.denominator == (
        "eligible real-user messages with a direct moderator reply in the analysis window"
    )
    assert catalog["peer_support_ratio"].denominator == (
        "all answered user questions in the analysis window"
    )
    assert catalog["peer_support_ratio"].adapter_required_fields == (
        "peer_first_answered_question_count",
        "answered_user_question_count",
    )

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


def test_semantic_coverage_adapter_matches_campaign_formula() -> None:
    source = pd.DataFrame(
        {
            "observation_id": ["a", "b"],
            "covered": [2, 0],
            "partially_covered": [2, 1],
            "total_claims": [5, 2],
        }
    )
    adapted = adapt_metric_source(
        "semantic_campaign_coverage",
        source,
        observation_key_columns=OBSERVATION_KEYS,
    )
    assert adapted.to_dict("records") == [
        {
            "observation_id": "a",
            "semantic_campaign_coverage": 0.6,
            ADAPTER_REASON_COLUMN: "observed",
        },
        {
            "observation_id": "b",
            "semantic_campaign_coverage": 0.25,
            ADAPTER_REASON_COLUMN: "observed",
        },
    ]


def test_depth_and_latency_adapters_use_canonical_upstream_fields() -> None:
    depth = adapt_metric_source(
        "conversation_propagation_depth",
        pd.DataFrame({"observation_id": ["a"], "conversation_depth": [4]}),
        observation_key_columns=OBSERVATION_KEYS,
    )
    latency = adapt_metric_source(
        "community_response_latency",
        pd.DataFrame({"observation_id": ["a"], "response_latency_seconds": [45.0]}),
        observation_key_columns=OBSERVATION_KEYS,
    )
    assert depth.iloc[0].to_dict() == {
        "observation_id": "a",
        "conversation_propagation_depth": 4.0,
        ADAPTER_REASON_COLUMN: "observed",
    }
    assert latency.iloc[0].to_dict() == {
        "observation_id": "a",
        "community_response_latency": 45.0,
        ADAPTER_REASON_COLUMN: "observed",
    }


def test_peer_support_adapter_requires_episode_counts_and_rejects_activation_ratio() -> None:
    incompatible = pd.DataFrame(
        {
            "observation_id": ["a"],
            "peer_support_ratio": [0.5],
            "peer_reply_edge_count": [1],
            "user_to_user_reply_edge_count": [2],
        }
    )
    with pytest.raises(ValueError, match="incompatible.*Activation|episode-derived"):
        adapt_metric_source(
            "peer_support_ratio",
            incompatible,
            observation_key_columns=OBSERVATION_KEYS,
        )

    adapted = adapt_metric_source(
        "peer_support_ratio",
        pd.DataFrame(
            {
                "observation_id": ["a", "b"],
                "peer_first_answered_question_count": [2, 1],
                "answered_user_question_count": [4, 4],
            }
        ),
        observation_key_columns=OBSERVATION_KEYS,
    )
    assert adapted["peer_support_ratio"].tolist() == [0.5, 0.25]
    assert adapted[ADAPTER_REASON_COLUMN].tolist() == ["observed", "observed"]


def test_latency_adapter_preserves_no_response_rows_with_explicit_reason() -> None:
    with_denominator = adapt_metric_source(
        "community_response_latency",
        pd.DataFrame(
            {
                "observation_id": ["no-response", "responded"],
                "response_latency_seconds": [np.nan, 30.0],
                "response_latency_denominator_count": [0, 1],
            }
        ),
        observation_key_columns=OBSERVATION_KEYS,
    )
    without_denominator = adapt_metric_source(
        "community_response_latency",
        pd.DataFrame(
            {
                "observation_id": ["no-response"],
                "response_latency_seconds": [np.nan],
            }
        ),
        observation_key_columns=OBSERVATION_KEYS,
    )

    assert with_denominator["observation_id"].tolist() == ["no-response", "responded"]
    assert np.isnan(with_denominator.loc[0, "community_response_latency"])
    assert with_denominator[ADAPTER_REASON_COLUMN].tolist() == [
        "zero_denominator",
        "observed",
    ]
    assert np.isnan(without_denominator.loc[0, "community_response_latency"])
    assert without_denominator.loc[0, ADAPTER_REASON_COLUMN] == "no_observation"

    validation = _validate(
        with_denominator,
        None,
        metric_columns=("community_response_latency",),
        minimum_sample_size=3,
    )[0]
    assert validation.sample_size == 2
    assert validation.raw_missing_count == 1


def test_peer_adapter_preserves_zero_answered_question_denominator() -> None:
    adapted = adapt_metric_source(
        "peer_support_ratio",
        pd.DataFrame(
            {
                "observation_id": ["none-answered", "answered"],
                "peer_first_answered_question_count": [0, 1],
                "answered_user_question_count": [0, 4],
            }
        ),
        observation_key_columns=OBSERVATION_KEYS,
    )

    assert adapted["observation_id"].tolist() == ["answered", "none-answered"]
    assert adapted.loc[0, "peer_support_ratio"] == pytest.approx(0.25)
    assert adapted.loc[0, ADAPTER_REASON_COLUMN] == "observed"
    assert np.isnan(adapted.loc[1, "peer_support_ratio"])
    assert adapted.loc[1, ADAPTER_REASON_COLUMN] == "zero_denominator"


@pytest.mark.parametrize(
    ("metric_name", "source"),
    [
        (
            "semantic_campaign_coverage",
            {"covered": [True], "partially_covered": [0], "total_claims": [1]},
        ),
        (
            "semantic_campaign_coverage",
            {"covered": [0.5], "partially_covered": [0], "total_claims": [1]},
        ),
        (
            "semantic_campaign_coverage",
            {"covered": [-1], "partially_covered": [0], "total_claims": [1]},
        ),
        (
            "semantic_campaign_coverage",
            {"covered": [1], "partially_covered": [1], "total_claims": [1]},
        ),
        ("conversation_propagation_depth", {"conversation_depth": [True]}),
        ("conversation_propagation_depth", {"conversation_depth": [1.5]}),
        (
            "peer_support_ratio",
            {
                "peer_first_answered_question_count": [2],
                "answered_user_question_count": [1],
            },
        ),
    ],
)
def test_count_adapters_reject_noninteger_negative_bool_and_inconsistent_counts(
    metric_name: str,
    source: dict[str, list[object]],
) -> None:
    with pytest.raises(ValueError, match="count|integer|consistent|numerator"):
        adapt_metric_source(
            metric_name,
            pd.DataFrame({"observation_id": ["a"], **source}),
            observation_key_columns=OBSERVATION_KEYS,
        )


def test_catalog_and_results_are_deeply_immutable() -> None:
    catalog = metric_catalog()
    with pytest.raises(TypeError):
        catalog["changed"] = catalog["peer_support_ratio"]
    with pytest.raises(FrozenInstanceError):
        catalog["peer_support_ratio"].formula = "changed"

    result = _validate(
        _metric_frame(metric=[0, 1, 2, 3, 4]),
        None,
        metric_columns=("metric",),
    )[0]
    with pytest.raises(FrozenInstanceError):
        result.status = "Rejected"
    with pytest.raises(TypeError):
        result.reasons[0] = "changed"


def test_observation_keys_are_required_even_without_outcomes() -> None:
    frame = _metric_frame(metric=[0, 1, 2, 3, 4])
    with pytest.raises(ValueError, match="observation_key_columns.*required"):
        validate_metrics(
            frame,
            None,
            observation_key_columns=(),
            metric_columns=("metric",),
        )


def test_duplicate_and_missing_observation_keys_are_rejected_without_outcomes() -> None:
    duplicate = _metric_frame(metric=[0, 1, 2, 3, 4])
    duplicate.loc[1, "observation_id"] = "obs-00"
    with pytest.raises(ValueError, match="metric frame.*unique"):
        _validate(duplicate, None, metric_columns=("metric",))

    missing = _metric_frame(metric=[0, 1, 2, 3, 4])
    missing.loc[1, "observation_id"] = None
    with pytest.raises(ValueError, match="metric frame.*missing observation key"):
        _validate(missing, None, metric_columns=("metric",))

    blank = _metric_frame(metric=[0, 1, 2, 3, 4])
    blank.loc[1, "observation_id"] = "  "
    with pytest.raises(ValueError, match="metric frame.*blank observation key"):
        _validate(blank, None, metric_columns=("metric",))


def test_outcome_keys_are_validated_even_with_no_selected_numeric_outcomes() -> None:
    metrics = _metric_frame(metric=[0, 1, 2, 3, 4])
    outcomes = _outcome_frame(note=["a", "b", "c", "d", "e"])
    outcomes.loc[1, "observation_id"] = "obs-00"
    with pytest.raises(ValueError, match="outcome frame.*unique"):
        _validate(
            metrics,
            outcomes,
            metric_columns=("metric",),
            outcome_columns=(),
        )


def test_outcomes_require_shared_keys_and_exact_key_universe() -> None:
    metrics = _metric_frame(metric=[0, 1, 2, 3, 4])
    no_key = pd.DataFrame({"different_id": range(5), "retention": range(5)})
    with pytest.raises(ValueError, match="outcome frame.*observation_id"):
        _validate(
            metrics,
            no_key,
            metric_columns=("metric",),
            outcome_columns=("retention",),
        )

    unmatched = _outcome_frame(retention=[0, 1, 2, 3, 4])
    unmatched.loc[4, "observation_id"] = "other"
    with pytest.raises(ValueError, match="key universe.*metric_only=1.*outcome_only=1"):
        _validate(
            metrics,
            unmatched,
            metric_columns=("metric",),
            outcome_columns=("retention",),
        )


def test_metric_quality_counts_are_disjoint() -> None:
    values = [None, "bad", np.inf, -np.inf, 1.0, 2.0, 3.0, 4.0, 5.0]
    result = _validate(
        _metric_frame(metric=values),
        None,
        metric_columns=("metric",),
    )[0]
    assert result.raw_missing_count == 1
    assert result.invalid_nonnumeric_count == 1
    assert result.positive_infinity_count == 1
    assert result.negative_infinity_count == 1
    assert result.finite_count == 5
    assert (
        sum(
            (
                result.raw_missing_count,
                result.invalid_nonnumeric_count,
                result.positive_infinity_count,
                result.negative_infinity_count,
                result.finite_count,
            )
        )
        == result.sample_size
    )
    assert result.status == "Rejected"


def test_outcome_quality_counts_are_disjoint_and_invalid_values_block_inference() -> None:
    metric = _metric_frame(metric=list(range(9)))
    outcomes = _outcome_frame(retention=[None, "bad", np.inf, -np.inf, 1.0, 2.0, 3.0, 4.0, 5.0])
    association = _validate(
        metric,
        outcomes,
        metric_columns=("metric",),
        outcome_columns=("retention",),
    )[0].associations[0]
    assert association.outcome_raw_missing_count == 1
    assert association.outcome_invalid_nonnumeric_count == 1
    assert association.outcome_positive_infinity_count == 1
    assert association.outcome_negative_infinity_count == 1
    assert association.outcome_finite_count == 5
    assert association.reason == "invalid_outcome_values"
    assert association.raw_p_value is None
    assert association.adjusted_p_value is None


def test_constant_outcome_is_explicitly_rejected_for_association() -> None:
    association = _validate(
        _metric_frame(metric=list(range(6))),
        _outcome_frame(retention=[1.0] * 6),
        metric_columns=("metric",),
        outcome_columns=("retention",),
    )[0].associations[0]
    assert association.reason == "zero_variance_outcome"
    assert association.inference_method == "not_estimated"
    assert association.raw_p_value is None


def test_all_missing_outcome_is_explicit_and_not_inferred() -> None:
    association = _validate(
        _metric_frame(metric=list(range(5))),
        _outcome_frame(retention=[np.nan] * 5),
        metric_columns=("metric",),
        outcome_columns=("retention",),
    )[0].associations[0]
    assert association.outcome_raw_missing_count == 5
    assert association.outcome_finite_count == 0
    assert association.reason == "no_finite_pairs"
    assert association.raw_p_value is None


@pytest.mark.parametrize(
    ("values", "expected_reason"),
    [
        ([1.0] * 5, "zero_variance"),
        ([np.nan] * 5, "all_missing"),
        ([1.0, 2.0, np.inf, 4.0, 5.0], "infinite_values"),
        ([1.0, 2.0], "insufficient_sample"),
    ],
)
def test_invalid_metric_series_is_rejected(values: list[float], expected_reason: str) -> None:
    result = _validate(
        _metric_frame(metric=values),
        None,
        metric_columns=("metric",),
        minimum_sample_size=3,
    )[0]
    assert result.status == "Rejected"
    assert expected_reason in result.reasons


@pytest.mark.parametrize(
    ("sample_size", "expected_p", "expected_status"),
    [(3, 2 / 6, "Candidate"), (4, 2 / 24, "Candidate"), (5, 2 / 120, "Promising")],
)
def test_small_sample_uses_exact_permutation_spearman(
    sample_size: int,
    expected_p: float,
    expected_status: str,
) -> None:
    values = list(range(sample_size))
    result = _validate(
        _metric_frame(metric=values),
        _outcome_frame(retention=values),
        metric_columns=("metric",),
        outcome_columns=("retention",),
        minimum_sample_size=3,
        minimum_group_size=1,
    )[0]
    association = result.associations[0]
    assert association.inference_method == "exact_two_sided_permutation_spearman"
    assert association.raw_p_value == pytest.approx(expected_p)
    assert association.adjusted_p_value == pytest.approx(expected_p)
    assert association.confidence_interval_95 is None
    assert association.uncertainty_reason == "population_interval_unavailable_for_exact_test"
    assert result.status == expected_status


def test_intermediate_sample_is_descriptive_only_not_promoted() -> None:
    values = list(range(9))
    result = _validate(
        _metric_frame(metric=values),
        _outcome_frame(retention=values),
        metric_columns=("metric",),
        outcome_columns=("retention",),
    )[0]
    association = result.associations[0]
    assert association.spearman_rho == pytest.approx(1.0)
    assert association.inference_method == "descriptive_only_small_sample"
    assert association.raw_p_value is None
    assert association.reason == "inferential_sample_too_small_for_asymptotic_test"
    assert result.status == "Candidate"


def test_large_sample_uses_labeled_asymptotic_inference_without_degenerate_ci() -> None:
    values = list(range(20))
    result = _validate(
        _metric_frame(metric=values),
        _outcome_frame(retention=values),
        metric_columns=("metric",),
        outcome_columns=("retention",),
    )[0]
    association = result.associations[0]
    assert association.inference_method == "asymptotic_spearman"
    assert association.raw_p_value is not None
    assert association.adjusted_p_value is not None
    assert association.raw_p_value > 0.0
    assert association.adjusted_p_value > 0.0
    assert association.p_value_floor > 0.0
    assert association.raw_p_value == association.p_value_floor
    assert association.below_reporting_precision is True
    assert "floor" in association.p_value_reporting_note
    assert association.confidence_interval_95 is not None
    assert association.confidence_interval_95 != (1.0, 1.0)
    assert result.status == "Promising"


def test_holm_adjustment_records_multiplicity_and_controls_promotion() -> None:
    values = list(range(5))
    outcomes = _outcome_frame(
        outcome_a=values,
        outcome_b=list(reversed(values)),
        outcome_c=values,
        outcome_d=values,
    )
    result = _validate(
        _metric_frame(metric=values),
        outcomes,
        metric_columns=("metric",),
        outcome_columns=("outcome_d", "outcome_b", "outcome_a", "outcome_c"),
        minimum_sample_size=3,
        minimum_group_size=1,
    )[0]
    assert tuple(item.outcome_name for item in result.associations) == (
        "outcome_a",
        "outcome_b",
        "outcome_c",
        "outcome_d",
    )
    assert all(item.outcomes_tested_count == 4 for item in result.associations)
    assert all(item.adjustment_method == "Holm" for item in result.associations)
    assert all(item.raw_p_value == pytest.approx(2 / 120) for item in result.associations)
    assert all(item.adjusted_p_value == pytest.approx(4 * 2 / 120) for item in result.associations)
    assert result.status == "Candidate"


def test_holm_family_is_global_across_all_metric_outcome_hypotheses() -> None:
    values = list(range(5))
    results = _validate(
        _metric_frame(metric_a=values, metric_b=list(reversed(values))),
        _outcome_frame(outcome_a=values, outcome_b=list(reversed(values))),
        metric_columns=("metric_b", "metric_a"),
        outcome_columns=("outcome_b", "outcome_a"),
        minimum_sample_size=3,
        minimum_group_size=1,
    )

    associations = tuple(association for result in results for association in result.associations)
    assert len(associations) == 4
    assert all(association.multiplicity_family_count == 4 for association in associations)
    assert all(
        association.multiplicity_family_definition
        == "all selected metric-outcome hypotheses in one validate_metrics call"
        for association in associations
    )
    assert all(association.raw_p_value == pytest.approx(2 / 120) for association in associations)
    assert all(
        association.adjusted_p_value == pytest.approx(4 * 2 / 120) for association in associations
    )
    assert {result.status for result in results} == {"Candidate"}


def test_group_diagnostics_are_explicit_and_descriptive() -> None:
    result = _validate(
        _metric_frame(metric=[0.0, 3.0, 6.0, 0.0, 3.0, 6.0]),
        None,
        metric_columns=("metric",),
        minimum_group_size=2,
    )[0]
    community = result.community_diagnostics
    assert community is not None
    assert community.status == "descriptive_comparison"
    assert community.group_count == 3
    assert community.adequate_group_count == 3
    assert community.spread == pytest.approx(6.0)
    assert "not evidence of stability" in community.interpretation
    assert tuple(item.group_value for item in community.groups) == (
        "community-0",
        "community-1",
        "community-2",
    )
    assert all(item.finite_count == 2 for item in community.groups)


def test_fewer_than_two_adequate_groups_has_no_spread() -> None:
    frame = pd.DataFrame(
        {
            "observation_id": ["a", "b", "c"],
            "community_id": ["one", "one", "tiny"],
            "language": ["en", "en", "es"],
            "metric": [1.0, 2.0, 100.0],
        }
    )
    result = _validate(
        frame,
        None,
        metric_columns=("metric",),
        minimum_sample_size=3,
        minimum_group_size=2,
    )[0]
    assert result.community_diagnostics is not None
    assert result.community_diagnostics.status == "insufficient_groups"
    assert result.community_diagnostics.adequate_group_count == 1
    assert result.community_diagnostics.spread is None
    assert result.language_diagnostics is not None
    assert result.language_diagnostics.status == "insufficient_groups"
    assert result.language_diagnostics.spread is None


def test_missing_and_blank_group_dimensions_are_counted_but_never_compared() -> None:
    frame = pd.DataFrame(
        {
            "observation_id": ["a", "b", "c", "d", "e"],
            "community_id": ["real", "real", None, "  ", ""],
            "language": ["en", "en", None, "  ", ""],
            "metric": [1.0, 2.0, 100.0, 200.0, 300.0],
        }
    )
    result = _validate(
        frame,
        None,
        metric_columns=("metric",),
        minimum_group_size=2,
    )[0]

    for diagnostic, expected_group in (
        (result.community_diagnostics, "real"),
        (result.language_diagnostics, "en"),
    ):
        assert diagnostic is not None
        assert diagnostic.raw_missing_group_count == 1
        assert diagnostic.blank_group_count == 2
        assert diagnostic.excluded_group_count == 3
        assert diagnostic.group_count == 1
        assert diagnostic.adequate_group_count == 1
        assert tuple(item.group_value for item in diagnostic.groups) == (expected_group,)
        assert diagnostic.status == "insufficient_groups"
        assert diagnostic.spread is None


def test_redundancy_diagnostics_are_symmetric_directional_and_deterministic() -> None:
    values = list(range(8))
    results = _validate(
        _metric_frame(
            metric_a=values,
            metric_b=[value * 10 for value in values],
            metric_c=list(reversed(values)),
        ),
        None,
        metric_columns=("metric_c", "metric_a", "metric_b"),
        minimum_sample_size=5,
    )
    a = _result(results, "metric_a")
    b = _result(results, "metric_b")
    ab_from_a = next(
        item
        for item in a.redundancy_diagnostics
        if (item.metric_a, item.metric_b) == ("metric_a", "metric_b")
    )
    ab_from_b = next(
        item
        for item in b.redundancy_diagnostics
        if (item.metric_a, item.metric_b) == ("metric_a", "metric_b")
    )
    assert ab_from_a == ab_from_b
    assert ab_from_a.spearman_rho == pytest.approx(1.0)
    assert ab_from_a.direction == "positive"
    assert ab_from_a.paired_sample_size == 8
    assert ab_from_a.threshold == pytest.approx(0.9)
    assert ab_from_a.reason == "absolute_spearman_at_or_above_threshold"
    assert a.redundant_with == ("metric_b", "metric_c")
    assert tuple(result.metric_name for result in results) == (
        "metric_a",
        "metric_b",
        "metric_c",
    )


def test_valid_metric_without_outcome_remains_candidate() -> None:
    result = _validate(
        _metric_frame(metric=[0.0, 2.0, 1.0, 5.0, 3.0]),
        None,
        metric_columns=("metric",),
    )[0]
    assert result.status == "Candidate"
    assert result.associations == ()
    assert "no_outcome_frame" in result.reasons


def test_results_are_deterministic_and_never_expose_score_weight_or_validated() -> None:
    frame = _metric_frame(z_metric=list(range(20)), a_metric=list(reversed(range(20))))
    outcomes = _outcome_frame(retention=list(range(20)))
    first = _validate(
        frame,
        outcomes,
        metric_columns=("z_metric", "a_metric"),
        outcome_columns=("retention",),
    )
    second = _validate(
        frame.sample(frac=1, random_state=7),
        outcomes.sample(frac=1, random_state=11),
        metric_columns=("a_metric", "z_metric"),
        outcome_columns=("retention",),
    )
    assert first == second
    assert {item.status for item in first} <= {"Candidate", "Promising", "Rejected"}
    assert all(not hasattr(item, "score") for item in first)
    assert all(not hasattr(item, "weight") for item in first)

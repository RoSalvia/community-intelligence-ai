"""Statistically bounded candidate-metric definitions and validation.

The metric lab reports data quality, dispersion, redundancy, and descriptive
outcome associations. It does not create a composite score, assign weights, or
make causal claims. Synthetic evidence can never produce a Validated status.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import atanh, isclose, sqrt, tanh
from types import MappingProxyType
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

MetricStatus = Literal["Candidate", "Promising", "Rejected"]

_IDENTIFIER_COLUMNS = (
    "observation_id",
    "campaign_id",
    "community_id",
    "language",
    "window_start",
    "window_end",
)
_PROMISING_ABSOLUTE_RHO = 0.3
_PROMISING_P_VALUE = 0.05
_REDUNDANCY_ABSOLUTE_RHO = 0.9


@dataclass(frozen=True)
class MetricDefinition:
    """Auditable business and computation contract for one candidate metric."""

    metric_name: str
    business_meaning: str
    formula: str
    denominator: str
    required_fields: tuple[str, ...]
    unit_of_analysis: str
    time_window: str
    why_it_may_matter: str
    biases: tuple[str, ...]
    limitations: tuple[str, ...]
    evidence_requirements: tuple[str, ...]


@dataclass(frozen=True)
class GroupSpread:
    """Difference between group-level means for a descriptive scope column."""

    group_column: str
    group_count: int
    minimum_group_mean: float
    maximum_group_mean: float
    mean_range: float


@dataclass(frozen=True)
class OutcomeAssociation:
    """A descriptive Spearman association with an optional uncertainty interval."""

    outcome_name: str
    paired_sample_size: int
    spearman_rho: float | None
    p_value: float | None
    confidence_interval_95: tuple[float, float] | None
    reason: str | None
    interpretation: str


@dataclass(frozen=True)
class MetricValidationResult:
    """Immutable statistical diagnostics for one candidate metric column."""

    metric_name: str
    status: MetricStatus
    synthetic: bool
    sample_size: int
    missing_count: int
    missing_rate: float
    nonfinite_count: int
    finite_sample_size: int
    variance: float | None
    community_spread: GroupSpread | None
    language_spread: GroupSpread | None
    redundant_with: tuple[str, ...]
    associations: tuple[OutcomeAssociation, ...]
    minimum_sample_size: int
    promising_absolute_rho_threshold: float
    promising_p_value_threshold: float
    redundancy_absolute_rho_threshold: float
    reasons: tuple[str, ...]
    interpretation: str


def _definition(
    metric_name: str,
    business_meaning: str,
    formula: str,
    denominator: str,
    required_fields: tuple[str, ...],
    unit_of_analysis: str,
    time_window: str,
    why_it_may_matter: str,
    biases: tuple[str, ...],
    limitations: tuple[str, ...],
    evidence_requirements: tuple[str, ...],
) -> MetricDefinition:
    return MetricDefinition(
        metric_name=metric_name,
        business_meaning=business_meaning,
        formula=formula,
        denominator=denominator,
        required_fields=required_fields,
        unit_of_analysis=unit_of_analysis,
        time_window=time_window,
        why_it_may_matter=why_it_may_matter,
        biases=biases,
        limitations=limitations,
        evidence_requirements=evidence_requirements,
    )


_CATALOG = MappingProxyType(
    {
        "campaign_discussion_share": _definition(
            "campaign_discussion_share",
            "Share of real-user messages in scope that discuss the named campaign.",
            "campaign-related real-user messages / all real-user messages",
            "all real-user messages in the analysis window",
            ("message_id", "timestamp", "user_role", "campaign_id", "community_id"),
            "community-campaign window",
            "Explicit campaign start and end timestamps; never an inferred rolling window.",
            "May distinguish user discussion from administrator posting volume.",
            ("Campaign aliases may miss indirect references.", "High-volume users may dominate."),
            (
                "Discussion volume does not establish persuasion or conversion.",
                "Comparisons require equivalent campaign windows and inclusion rules.",
            ),
            ("source message IDs", "campaign ID", "window bounds", "matching rule version"),
        ),
        "community_response_latency": _definition(
            "community_response_latency",
            "Elapsed time until the first qualifying community response to a user message.",
            "sum of first qualifying response latencies / user messages with a response",
            "user messages receiving a qualifying response in the analysis window",
            ("message_id", "reply_to_message_id", "timestamp", "user_role", "community_id"),
            "community-window response episode",
            "Explicit reporting-window start and end timestamps.",
            "May reveal whether questions receive timely attention.",
            ("Time zones and inactive hours can change expected latency.",),
            (
                "Unanswered messages are excluded from the latency denominator "
                "and reported separately.",
                "A fast response is not necessarily a correct or useful response.",
            ),
            ("source message and response IDs", "timestamps", "response rule version"),
        ),
        "conversation_propagation_depth": _definition(
            "conversation_propagation_depth",
            "Maximum reply-graph distance reached by a conversation episode.",
            "maximum number of reply edges from the episode root to any descendant",
            "one conversation episode rooted in the analysis window",
            ("message_id", "reply_to_message_id", "timestamp", "community_id"),
            "conversation episode",
            "Explicit episode-anchor window plus a documented reply-follow-up horizon.",
            "May separate one-off posting from sustained participant exchange.",
            ("Missing reply links understate depth.", "Long arguments can increase depth."),
            (
                "Depth does not measure sentiment, correctness, or healthy interaction.",
                "Cross-platform replies are unavailable in an offline Telegram export.",
            ),
            ("root and descendant source message IDs", "reply edges", "episode rule version"),
        ),
        "meaningful_interaction_ratio": _definition(
            "meaningful_interaction_ratio",
            "Share of real-user messages passing the documented language-specific "
            "interaction rule.",
            "qualifying real-user messages / all real-user messages",
            "all real-user messages in the analysis window",
            ("message_id", "text", "language", "user_role", "timestamp", "community_id"),
            "community-language window",
            "Explicit reporting-window start and end timestamps.",
            "May expose activity dominated by filler rather than substantive exchange.",
            ("Language-specific length and filler rules are not equivalent quality scales.",),
            (
                "Rule qualification is not a judgment of message value or user intent.",
                "Cross-language ranking is unsupported without separate validation.",
            ),
            ("source message IDs", "language", "rule ID and version", "raw rule measurements"),
        ),
        "organic_project_mention_rate": _definition(
            "organic_project_mention_rate",
            "Share of non-campaign real-user messages that mention the project "
            "without a linked campaign.",
            "qualifying organic project mentions / non-campaign real-user messages",
            "all non-campaign real-user messages in the analysis window",
            ("message_id", "text", "user_role", "campaign_id", "timestamp", "community_id"),
            "community-language window",
            "Explicit reporting-window start and end timestamps.",
            "May indicate participant-initiated project attention outside scheduled promotion.",
            ("Alias rules can miss paraphrases or count unrelated homonyms.",),
            (
                "A mention can be positive, negative, uncertain, or off-topic.",
                "Organic labeling requires explicit exclusion of campaign-linked messages.",
            ),
            ("source message IDs", "matched alias evidence", "campaign exclusion", "rule version"),
        ),
        "peer_support_ratio": _definition(
            "peer_support_ratio",
            "Share of answered user questions whose first qualifying answer "
            "comes from another user.",
            "answered user questions first answered by a different user / "
            "all answered user questions",
            "all answered user questions in the analysis window",
            ("message_id", "reply_to_message_id", "text", "user_id_hash", "user_role", "timestamp"),
            "community-language window",
            "Explicit question-anchor window plus a documented answer-follow-up horizon.",
            "May reveal support behavior that does not depend entirely on moderators.",
            ("Question and candidate-answer rules may differ by language.",),
            (
                "Candidate answers are not verified as correct or helpful.",
                "Unanswered questions belong in a separate metric.",
            ),
            ("question and answer source message IDs", "actor roles", "answer rule version"),
        ),
        "semantic_campaign_coverage": _definition(
            "semantic_campaign_coverage",
            "Share of atomic campaign claims covered or partially covered in one community.",
            "claims judged covered or partially_covered / all atomic claims",
            "all atomic campaign claims evaluated for the community in the campaign window",
            ("claim_id", "campaign_id", "community_id", "judgment", "message_id"),
            "campaign-community claim set",
            "The campaign's explicit start and end timestamps.",
            "May identify where important campaign information was not transmitted.",
            ("Claim extraction and multilingual matching errors can change coverage.",),
            (
                "Coverage does not prove audience comprehension or acceptance.",
                "Covered and partially_covered remain separate evidence statuses; "
                "no weights are used.",
            ),
            (
                "claim IDs and source message IDs",
                "judgment, confidence, and review status",
                "model or rule version",
            ),
        ),
        "semantic_drift_rate": _definition(
            "semantic_drift_rate",
            "Share of evaluated atomic claims that are contradicted or materially incorrect.",
            "contradicted or incorrect claim judgments / all evaluated atomic claims",
            "all atomic campaign claims evaluated for the community in the campaign window",
            ("claim_id", "campaign_id", "community_id", "judgment", "message_id"),
            "campaign-community claim set",
            "The campaign's explicit start and end timestamps.",
            "May flag communities where transmitted details diverge from the campaign brief.",
            ("Translation ambiguity may be mistaken for semantic drift.",),
            (
                "Drift labels require human-reviewable evidence and uncertainty.",
                "A descriptive difference must not be presented as deliberate misinformation.",
            ),
            ("claim and source message IDs", "translation", "confidence", "review status"),
        ),
        "unanswered_question_rate": _definition(
            "unanswered_question_rate",
            "Share of detected real-user questions without a qualifying response "
            "in the follow-up horizon.",
            "unanswered real-user questions / all detected real-user questions",
            "all detected real-user questions anchored in the analysis window",
            ("message_id", "reply_to_message_id", "text", "user_role", "timestamp", "community_id"),
            "community-language window",
            "Explicit question-anchor window plus a documented answer-follow-up horizon.",
            "May identify recurring gaps in community response capacity.",
            ("Question detection and incomplete reply graphs can inflate the rate.",),
            (
                "A reply outside the captured horizon may be incorrectly treated as absent.",
                "This metric does not establish who was responsible for responding.",
            ),
            (
                "question source message IDs",
                "candidate response IDs",
                "follow-up horizon",
                "rule version",
            ),
        ),
        "user_to_user_interaction_ratio": _definition(
            "user_to_user_interaction_ratio",
            "Share of real-user messages that are direct replies between different users.",
            "direct different-user reply messages / all real-user messages",
            "all real-user messages in the analysis window",
            ("message_id", "reply_to_message_id", "user_id_hash", "user_role", "timestamp"),
            "community window",
            "Explicit reporting-window start and end timestamps.",
            "May distinguish participant exchange from moderator-led or isolated activity.",
            ("Missing reply metadata understates interaction.",),
            (
                "Self-replies, bot replies, and moderator replies are excluded by definition.",
                "Interaction frequency does not establish interaction quality.",
            ),
            ("parent and reply source message IDs", "hashed actor IDs", "role and exclusion rules"),
        ),
    }
)


def metric_catalog() -> Mapping[str, MetricDefinition]:
    """Return the deterministic, read-only candidate metric catalog."""

    return _CATALOG


def _ordered_columns(
    frame: pd.DataFrame,
    requested: Sequence[str] | None,
    *,
    excluded: set[str],
) -> tuple[str, ...]:
    if requested is not None:
        columns = tuple(requested)
        if len(columns) != len(set(columns)):
            raise ValueError("column names must be unique")
        missing = sorted(set(columns) - set(frame.columns))
        if missing:
            raise ValueError(f"missing requested columns: {missing}")
        return tuple(sorted(columns))
    return tuple(
        sorted(
            column
            for column in frame.columns
            if column not in excluded and pd.api.types.is_numeric_dtype(frame[column])
        )
    )


def _numeric_values(series: pd.Series) -> tuple[pd.Series, int]:
    numeric = pd.to_numeric(series, errors="coerce").astype(float)
    non_numeric_count = int((series.notna() & numeric.isna()).sum())
    return numeric, non_numeric_count


def _group_spread(frame: pd.DataFrame, metric_name: str, group_name: str) -> GroupSpread | None:
    if group_name not in frame.columns:
        return None
    values, _ = _numeric_values(frame[metric_name])
    finite_mask = values.notna() & np.isfinite(values)
    scoped = pd.DataFrame({group_name: frame[group_name], "metric": values})[finite_mask]
    scoped = scoped[scoped[group_name].notna()]
    if scoped.empty:
        return None
    means = scoped.groupby(group_name, sort=True, dropna=True)["metric"].mean()
    if means.empty:
        return None
    minimum = float(means.min())
    maximum = float(means.max())
    return GroupSpread(
        group_column=group_name,
        group_count=len(means),
        minimum_group_mean=minimum,
        maximum_group_mean=maximum,
        mean_range=maximum - minimum,
    )


def _join_frames(metric_frame: pd.DataFrame, outcome_frame: pd.DataFrame) -> pd.DataFrame:
    if "observation_id" in metric_frame.columns and "observation_id" in outcome_frame.columns:
        join_columns = ("observation_id",)
    else:
        join_columns = tuple(
            column
            for column in _IDENTIFIER_COLUMNS[1:]
            if column in metric_frame.columns and column in outcome_frame.columns
        )
    if join_columns:
        label = ", ".join(join_columns)
        if metric_frame.duplicated(list(join_columns)).any():
            raise ValueError(f"metric frame must have unique {label}")
        if outcome_frame.duplicated(list(join_columns)).any():
            raise ValueError(f"outcome frame must have unique {label}")
        return metric_frame.merge(
            outcome_frame,
            how="inner",
            on=list(join_columns),
            suffixes=("", "__outcome"),
            sort=True,
            validate="one_to_one",
        )
    if len(metric_frame) != len(outcome_frame):
        raise ValueError("frames without shared identifiers must have equal row counts")
    left = metric_frame.reset_index(drop=True)
    right = outcome_frame.reset_index(drop=True)
    overlap = (set(left.columns) & set(right.columns)) - set(_IDENTIFIER_COLUMNS)
    if overlap:
        right = right.rename(columns={column: f"{column}__outcome" for column in overlap})
    return pd.concat([left, right], axis=1)


def _fisher_interval(rho: float, sample_size: int) -> tuple[float, float] | None:
    if sample_size <= 3:
        return None
    if isclose(abs(rho), 1.0, abs_tol=1e-12):
        endpoint = 1.0 if rho > 0 else -1.0
        return (endpoint, endpoint)
    transformed = atanh(float(np.clip(rho, -0.999999, 0.999999)))
    margin = 1.96 / sqrt(sample_size - 3)
    return (tanh(transformed - margin), tanh(transformed + margin))


def _association(
    joined: pd.DataFrame,
    metric_name: str,
    outcome_name: str,
    minimum_sample_size: int,
) -> OutcomeAssociation:
    outcome_column = (
        f"{outcome_name}__outcome" if f"{outcome_name}__outcome" in joined.columns else outcome_name
    )
    metric, _ = _numeric_values(joined[metric_name])
    outcome, _ = _numeric_values(joined[outcome_column])
    finite = metric.notna() & outcome.notna() & np.isfinite(metric) & np.isfinite(outcome)
    paired_metric = metric[finite]
    paired_outcome = outcome[finite]
    paired_count = len(paired_metric)
    reason: str | None = None
    if paired_count == 0:
        reason = "no_finite_pairs"
    elif paired_count < minimum_sample_size:
        reason = "insufficient_paired_sample"
    elif float(paired_metric.var(ddof=0)) == 0.0:
        reason = "zero_variance_metric"
    elif float(paired_outcome.var(ddof=0)) == 0.0:
        reason = "zero_variance_outcome"
    if reason is not None:
        return OutcomeAssociation(
            outcome_name=outcome_name,
            paired_sample_size=paired_count,
            spearman_rho=None,
            p_value=None,
            confidence_interval_95=None,
            reason=reason,
            interpretation="No valid descriptive association was estimated; no causal conclusion.",
        )
    statistic = spearmanr(paired_metric.to_numpy(), paired_outcome.to_numpy())
    rho = float(statistic.statistic)
    p_value = float(statistic.pvalue)
    return OutcomeAssociation(
        outcome_name=outcome_name,
        paired_sample_size=paired_count,
        spearman_rho=rho,
        p_value=p_value,
        confidence_interval_95=_fisher_interval(rho, paired_count),
        reason=None,
        interpretation=(
            "Descriptive Spearman association with an approximate Fisher-z 95% interval; "
            "association is not causality."
        ),
    )


def _redundancy_map(
    frame: pd.DataFrame,
    metric_columns: tuple[str, ...],
    minimum_sample_size: int,
) -> dict[str, tuple[str, ...]]:
    redundant: dict[str, set[str]] = {name: set() for name in metric_columns}
    for index, left_name in enumerate(metric_columns):
        left, _ = _numeric_values(frame[left_name])
        for right_name in metric_columns[index + 1 :]:
            right, _ = _numeric_values(frame[right_name])
            finite = left.notna() & right.notna() & np.isfinite(left) & np.isfinite(right)
            if int(finite.sum()) < minimum_sample_size:
                continue
            scoped_left = left[finite]
            scoped_right = right[finite]
            if float(scoped_left.var(ddof=0)) == 0.0 or float(scoped_right.var(ddof=0)) == 0.0:
                continue
            rho = float(spearmanr(scoped_left.to_numpy(), scoped_right.to_numpy()).statistic)
            if np.isfinite(rho) and abs(rho) >= _REDUNDANCY_ABSOLUTE_RHO:
                redundant[left_name].add(right_name)
                redundant[right_name].add(left_name)
    return {name: tuple(sorted(others)) for name, others in redundant.items()}


def validate_metrics(
    metric_frame: pd.DataFrame,
    outcome_frame: pd.DataFrame | None,
    *,
    metric_columns: Sequence[str] | None = None,
    outcome_columns: Sequence[str] | None = None,
    minimum_sample_size: int = 5,
    synthetic: bool = True,
) -> tuple[MetricValidationResult, ...]:
    """Validate explicit metric columns without producing a score or causal claim.

    Rows are joined by a unique ``observation_id`` when available, otherwise by
    shared scope columns, and finally by position only when row counts match.
    Any result derived from synthetic data is limited to Candidate, Promising,
    or Rejected; this function never emits Validated.
    """

    if minimum_sample_size < 3:
        raise ValueError("minimum_sample_size must be at least 3")
    if not isinstance(metric_frame, pd.DataFrame):
        raise TypeError("metric_frame must be a pandas DataFrame")
    if outcome_frame is not None and not isinstance(outcome_frame, pd.DataFrame):
        raise TypeError("outcome_frame must be a pandas DataFrame or None")

    metrics = _ordered_columns(
        metric_frame,
        metric_columns,
        excluded=set(_IDENTIFIER_COLUMNS),
    )
    if not metrics:
        raise ValueError("metric_frame contains no metric columns")

    joined: pd.DataFrame | None = None
    outcomes: tuple[str, ...] = ()
    if outcome_frame is not None:
        outcomes = _ordered_columns(
            outcome_frame,
            outcome_columns,
            excluded=set(_IDENTIFIER_COLUMNS) | set(metrics),
        )
        if outcomes:
            joined = _join_frames(metric_frame, outcome_frame)

    redundancy = _redundancy_map(metric_frame, metrics, minimum_sample_size)
    results: list[MetricValidationResult] = []
    for metric_name in metrics:
        values, non_numeric_count = _numeric_values(metric_frame[metric_name])
        sample_size = len(values)
        missing_count = int(values.isna().sum())
        infinite_count = int((values.notna() & ~np.isfinite(values)).sum())
        finite = values[values.notna() & np.isfinite(values)]
        finite_sample_size = len(finite)
        variance = float(finite.var(ddof=0)) if finite_sample_size else None

        reasons: list[str] = []
        if missing_count == sample_size:
            reasons.append("all_missing")
        if non_numeric_count:
            reasons.append("non_numeric_values")
        if infinite_count:
            reasons.append("nonfinite_values")
        if finite_sample_size < minimum_sample_size:
            reasons.append("insufficient_sample")
        if finite_sample_size and variance == 0.0:
            reasons.append("zero_variance")

        associations = (
            tuple(
                _association(joined, metric_name, outcome_name, minimum_sample_size)
                for outcome_name in outcomes
            )
            if joined is not None
            else ()
        )
        if outcome_frame is None:
            reasons.append("no_outcome_frame")
        elif not outcomes:
            reasons.append("no_outcome_columns")

        rejected = any(
            reason
            in {
                "all_missing",
                "non_numeric_values",
                "nonfinite_values",
                "insufficient_sample",
                "zero_variance",
            }
            for reason in reasons
        )
        promising = any(
            association.spearman_rho is not None
            and association.p_value is not None
            and abs(association.spearman_rho) >= _PROMISING_ABSOLUTE_RHO
            and association.p_value <= _PROMISING_P_VALUE
            for association in associations
        )
        status: MetricStatus
        if rejected:
            status = "Rejected"
        elif promising:
            status = "Promising"
            reasons.append("synthetic_association_only" if synthetic else "association_observed")
        else:
            status = "Candidate"

        results.append(
            MetricValidationResult(
                metric_name=metric_name,
                status=status,
                synthetic=synthetic,
                sample_size=sample_size,
                missing_count=missing_count,
                missing_rate=missing_count / sample_size if sample_size else 1.0,
                nonfinite_count=infinite_count + non_numeric_count,
                finite_sample_size=finite_sample_size,
                variance=variance,
                community_spread=_group_spread(metric_frame, metric_name, "community_id"),
                language_spread=_group_spread(metric_frame, metric_name, "language"),
                redundant_with=redundancy[metric_name],
                associations=associations,
                minimum_sample_size=minimum_sample_size,
                promising_absolute_rho_threshold=_PROMISING_ABSOLUTE_RHO,
                promising_p_value_threshold=_PROMISING_P_VALUE,
                redundancy_absolute_rho_threshold=_REDUNDANCY_ABSOLUTE_RHO,
                reasons=tuple(dict.fromkeys(reasons)),
                interpretation=(
                    "Synthetic candidate-metric diagnostics report descriptive association only; "
                    "association is not causality and human review is required."
                    if synthetic
                    else (
                        "Candidate-metric diagnostics report association only, not a causal effect."
                    )
                ),
            )
        )
    return tuple(sorted(results, key=lambda item: item.metric_name))

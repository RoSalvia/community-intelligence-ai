"""Statistically bounded candidate-metric definitions and validation.

The metric lab reports data quality, dispersion, redundancy, and descriptive
outcome associations. It does not create a composite score, assign weights, or
make causal claims. Synthetic evidence can never produce a Validated status.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import permutations
from math import atanh, factorial, sqrt, tanh
from types import MappingProxyType
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

from community_intelligence.campaign import SEMANTIC_COVERAGE_FORMULA

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
_EXACT_PERMUTATION_MAXIMUM_SAMPLE = 8
_ASYMPTOTIC_MINIMUM_SAMPLE = 20


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
    adapter_required_fields: tuple[str, ...] = ()
    adapter_incompatible_fields: tuple[str, ...] = ()
    adapter_contract: str = "Not implemented"


@dataclass(frozen=True)
class GroupValueDiagnostic:
    group_value: str
    sample_size: int
    raw_missing_count: int
    invalid_nonnumeric_count: int
    positive_infinity_count: int
    negative_infinity_count: int
    finite_count: int
    mean: float | None


@dataclass(frozen=True)
class GroupDiagnostics:
    group_column: str
    status: Literal["descriptive_comparison", "insufficient_groups"]
    group_count: int
    adequate_group_count: int
    minimum_group_size: int
    groups: tuple[GroupValueDiagnostic, ...]
    spread: float | None
    interpretation: str

    @property
    def mean_range(self) -> float | None:
        """Compatibility alias for the descriptive group-mean range."""

        return self.spread


@dataclass(frozen=True)
class RedundancyDiagnostic:
    metric_a: str
    metric_b: str
    spearman_rho: float | None
    direction: Literal["positive", "negative", "none", "unavailable"]
    paired_sample_size: int
    threshold: float
    reason: str


@dataclass(frozen=True)
class OutcomeAssociation:
    """A descriptive Spearman association with an optional uncertainty interval."""

    outcome_name: str
    paired_sample_size: int
    outcome_raw_missing_count: int
    outcome_invalid_nonnumeric_count: int
    outcome_positive_infinity_count: int
    outcome_negative_infinity_count: int
    outcome_finite_count: int
    spearman_rho: float | None
    raw_p_value: float | None
    adjusted_p_value: float | None
    outcomes_tested_count: int
    adjustment_method: str
    inference_method: str
    confidence_interval_95: tuple[float, float] | None
    uncertainty_reason: str | None
    reason: str | None
    interpretation: str

    @property
    def p_value(self) -> float | None:
        """Compatibility alias for the unadjusted p-value."""

        return self.raw_p_value


@dataclass(frozen=True)
class MetricValidationResult:
    """Immutable statistical diagnostics for one candidate metric column."""

    metric_name: str
    status: MetricStatus
    synthetic: bool
    sample_size: int
    raw_missing_count: int
    invalid_nonnumeric_count: int
    positive_infinity_count: int
    negative_infinity_count: int
    finite_count: int
    variance: float | None
    community_diagnostics: GroupDiagnostics | None
    language_diagnostics: GroupDiagnostics | None
    redundancy_diagnostics: tuple[RedundancyDiagnostic, ...]
    associations: tuple[OutcomeAssociation, ...]
    minimum_sample_size: int
    minimum_group_size: int
    promising_absolute_rho_threshold: float
    promising_p_value_threshold: float
    redundancy_absolute_rho_threshold: float
    reasons: tuple[str, ...]
    interpretation: str

    @property
    def missing_count(self) -> int:
        return self.raw_missing_count

    @property
    def missing_rate(self) -> float:
        return self.raw_missing_count / self.sample_size if self.sample_size else 1.0

    @property
    def nonfinite_count(self) -> int:
        return (
            self.invalid_nonnumeric_count
            + self.positive_infinity_count
            + self.negative_infinity_count
        )

    @property
    def finite_sample_size(self) -> int:
        return self.finite_count

    @property
    def community_spread(self) -> GroupDiagnostics | None:
        return self.community_diagnostics

    @property
    def language_spread(self) -> GroupDiagnostics | None:
        return self.language_diagnostics

    @property
    def redundant_with(self) -> tuple[str, ...]:
        names: set[str] = set()
        for diagnostic in self.redundancy_diagnostics:
            if diagnostic.reason != "absolute_spearman_at_or_above_threshold":
                continue
            names.add(
                diagnostic.metric_b
                if diagnostic.metric_a == self.metric_name
                else diagnostic.metric_a
            )
        return tuple(sorted(names))


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
    adapter_required_fields: tuple[str, ...] = (),
    adapter_incompatible_fields: tuple[str, ...] = (),
    adapter_contract: str = "Not implemented",
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
        adapter_required_fields=adapter_required_fields,
        adapter_incompatible_fields=adapter_incompatible_fields,
        adapter_contract=adapter_contract,
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
            "Mean elapsed seconds to the first direct moderator reply for each "
            "eligible user message.",
            "sum of first direct moderator reply latency seconds / "
            "eligible real-user messages with a direct moderator reply",
            "eligible real-user messages with a direct moderator reply in the analysis window",
            ("message_id", "reply_to_message_id", "timestamp", "user_role", "community_id"),
            "community-window response episode",
            "Explicit reporting-window start and end timestamps.",
            "May reveal whether eligible user messages receive timely moderator attention.",
            ("Time zones and inactive hours can change expected latency.",),
            (
                "Messages without a direct moderator reply are excluded from the latency "
                "denominator and reported separately.",
                "A fast response is not necessarily a correct or useful response.",
            ),
            ("source message and moderator reply IDs", "timestamps", "response rule version"),
            ("response_latency_seconds",),
            (),
            "Identity adapter from ActivationResult response_latency_seconds, whose metadata "
            "uses the first chronological direct moderator reply per eligible real-user message.",
        ),
        "conversation_propagation_depth": _definition(
            "conversation_propagation_depth",
            "Message-node count on the longest reply path in a conversation episode.",
            "number of message nodes on the episode's longest reply path",
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
            ("conversation_depth",),
            ("reply_edge_depth",),
            "Identity adapter from ConversationEpisode.conversation_depth; the upstream value "
            "is longest-path edge count plus one message node.",
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
            ("peer_first_answered_question_count", "answered_user_question_count"),
            ("peer_support_ratio", "peer_reply_edge_count", "user_to_user_reply_edge_count"),
            "Compute from episode-level answered-question evidence only. ActivationResult's "
            "peer_support_ratio uses a different reply-edge denominator and is incompatible.",
        ),
        "semantic_campaign_coverage": _definition(
            "semantic_campaign_coverage",
            "Partial-credit share of atomic campaign claims covered in one community.",
            SEMANTIC_COVERAGE_FORMULA,
            "all atomic campaign claims evaluated for the community in the campaign window",
            ("claim_id", "campaign_id", "community_id", "judgment", "message_id"),
            "campaign-community claim set",
            "The campaign's explicit start and end timestamps.",
            "May identify where important campaign information was not transmitted.",
            ("Claim extraction and multilingual matching errors can change coverage.",),
            (
                "Coverage does not prove audience comprehension or acceptance.",
                "The 0.5 partial-credit factor is a candidate design choice and must be "
                "reported separately from the underlying statuses.",
                "The 0.5 factor is not a moderator score or a validated business weight.",
            ),
            (
                "claim IDs and source message IDs",
                "judgment, confidence, and review status",
                "model or rule version",
            ),
            ("covered", "partially_covered", "total_claims"),
            (),
            "Compute from a complete campaign-community claim universe using campaign.py's "
            "canonical summary formula.",
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


@dataclass(frozen=True)
class _SeriesQuality:
    raw_missing_count: int
    invalid_nonnumeric_count: int
    positive_infinity_count: int
    negative_infinity_count: int
    finite_count: int


def _observation_keys(columns: Sequence[str]) -> tuple[str, ...]:
    keys = tuple(columns)
    if not keys:
        raise ValueError("observation_key_columns are required")
    if len(keys) != len(set(keys)) or any(not key.strip() for key in keys):
        raise ValueError("observation_key_columns must be unique non-empty names")
    return keys


def _validate_observation_keys(
    frame: pd.DataFrame,
    keys: tuple[str, ...],
    *,
    frame_name: str,
) -> None:
    missing_columns = [key for key in keys if key not in frame.columns]
    if missing_columns:
        raise ValueError(f"{frame_name} is missing observation key columns: {missing_columns}")
    if frame.loc[:, list(keys)].isna().any(axis=None):
        raise ValueError(f"{frame_name} contains a missing observation key")
    blank = frame.loc[:, list(keys)].map(lambda value: isinstance(value, str) and not value.strip())
    if blank.any(axis=None):
        raise ValueError(f"{frame_name} contains a blank observation key")
    if frame.duplicated(list(keys)).any():
        raise ValueError(f"{frame_name} must have unique observation key values")


def _key_universe(frame: pd.DataFrame, keys: tuple[str, ...]) -> set[tuple[object, ...]]:
    try:
        return set(frame.loc[:, list(keys)].itertuples(index=False, name=None))
    except TypeError as error:
        raise ValueError("observation key values must be hashable") from error


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


def _series_quality(series: pd.Series) -> tuple[pd.Series, _SeriesQuality]:
    raw_missing = series.isna()
    numeric = pd.to_numeric(series, errors="coerce").astype(float)
    invalid = ~raw_missing & numeric.isna()
    positive_infinity = numeric == np.inf
    negative_infinity = numeric == -np.inf
    finite = ~raw_missing & ~invalid & np.isfinite(numeric)
    quality = _SeriesQuality(
        raw_missing_count=int(raw_missing.sum()),
        invalid_nonnumeric_count=int(invalid.sum()),
        positive_infinity_count=int(positive_infinity.sum()),
        negative_infinity_count=int(negative_infinity.sum()),
        finite_count=int(finite.sum()),
    )
    if sum(quality.__dict__.values()) != len(series):
        raise AssertionError("series quality categories must be disjoint and exhaustive")
    return numeric, quality


def _strict_adapter_values(source: pd.DataFrame, field: str) -> pd.Series:
    numeric, quality = _series_quality(source[field])
    if (
        quality.raw_missing_count
        or quality.invalid_nonnumeric_count
        or quality.positive_infinity_count
        or quality.negative_infinity_count
    ):
        raise ValueError(f"adapter field {field} must contain only finite numeric values")
    return numeric


def adapt_metric_source(
    metric_name: str,
    source_frame: pd.DataFrame,
    *,
    observation_key_columns: Sequence[str],
) -> pd.DataFrame:
    """Construct a canonical metric from explicitly compatible upstream fields."""

    if metric_name not in _CATALOG:
        raise ValueError(f"unknown metric: {metric_name}")
    if not isinstance(source_frame, pd.DataFrame):
        raise TypeError("source_frame must be a pandas DataFrame")
    keys = _observation_keys(observation_key_columns)
    _validate_observation_keys(source_frame, keys, frame_name="source frame")
    definition = _CATALOG[metric_name]
    if not definition.adapter_required_fields:
        raise ValueError(f"{metric_name} has no implemented source adapter")
    incompatible = tuple(
        field for field in definition.adapter_incompatible_fields if field in source_frame.columns
    )
    if incompatible:
        raise ValueError(
            f"incompatible source fields {incompatible}; use the documented episode-derived "
            "or canonical upstream fields, not Activation's incompatible ratio"
        )
    missing = tuple(
        field for field in definition.adapter_required_fields if field not in source_frame.columns
    )
    if missing:
        raise ValueError(f"missing canonical adapter fields for {metric_name}: {missing}")

    output = source_frame.loc[:, list(keys)].copy()
    if metric_name == "semantic_campaign_coverage":
        covered = _strict_adapter_values(source_frame, "covered")
        partial = _strict_adapter_values(source_frame, "partially_covered")
        total = _strict_adapter_values(source_frame, "total_claims")
        if ((covered < 0) | (partial < 0) | (total <= 0) | (covered + partial > total)).any():
            raise ValueError("campaign claim counts must be non-negative and fit total_claims")
        output[metric_name] = (covered + 0.5 * partial) / total
    elif metric_name == "conversation_propagation_depth":
        depth = _strict_adapter_values(source_frame, "conversation_depth")
        if ((depth < 1) | (depth % 1 != 0)).any():
            raise ValueError("conversation_depth must be a positive message-node count")
        output[metric_name] = depth
    elif metric_name == "community_response_latency":
        latency = _strict_adapter_values(source_frame, "response_latency_seconds")
        if (latency < 0).any():
            raise ValueError("response_latency_seconds must be non-negative")
        output[metric_name] = latency
    elif metric_name == "peer_support_ratio":
        numerator = _strict_adapter_values(source_frame, "peer_first_answered_question_count")
        denominator = _strict_adapter_values(source_frame, "answered_user_question_count")
        if (numerator < 0).any() or (denominator <= 0).any() or (numerator > denominator).any():
            raise ValueError(
                "peer-support episode counts must satisfy 0 <= numerator <= denominator"
            )
        output[metric_name] = numerator / denominator
    else:  # pragma: no cover - guarded by adapter_required_fields
        raise ValueError(f"{metric_name} has no implemented source adapter")
    return output.sort_values(list(keys), kind="mergesort").reset_index(drop=True)


def _group_diagnostics(
    frame: pd.DataFrame,
    metric_name: str,
    group_name: str,
    minimum_group_size: int,
) -> GroupDiagnostics | None:
    if group_name not in frame.columns:
        return None
    group_series = frame[group_name]
    unique_groups = sorted(
        (value for value in group_series.dropna().unique()),
        key=lambda value: str(value),
    )
    if group_series.isna().any():
        unique_groups.append(None)
    diagnostics: list[GroupValueDiagnostic] = []
    adequate_means: list[float] = []
    for group_value in unique_groups:
        mask = group_series.isna() if group_value is None else group_series == group_value
        scoped_numeric, quality = _series_quality(frame.loc[mask, metric_name])
        finite = scoped_numeric[np.isfinite(scoped_numeric)]
        mean = float(finite.mean()) if quality.finite_count else None
        diagnostics.append(
            GroupValueDiagnostic(
                group_value="<MISSING>" if group_value is None else str(group_value),
                sample_size=int(mask.sum()),
                raw_missing_count=quality.raw_missing_count,
                invalid_nonnumeric_count=quality.invalid_nonnumeric_count,
                positive_infinity_count=quality.positive_infinity_count,
                negative_infinity_count=quality.negative_infinity_count,
                finite_count=quality.finite_count,
                mean=mean,
            )
        )
        if quality.finite_count >= minimum_group_size and mean is not None:
            adequate_means.append(mean)
    adequate_count = len(adequate_means)
    spread = max(adequate_means) - min(adequate_means) if adequate_count >= 2 else None
    status: Literal["descriptive_comparison", "insufficient_groups"] = (
        "descriptive_comparison" if adequate_count >= 2 else "insufficient_groups"
    )
    return GroupDiagnostics(
        group_column=group_name,
        status=status,
        group_count=len(diagnostics),
        adequate_group_count=adequate_count,
        minimum_group_size=minimum_group_size,
        groups=tuple(diagnostics),
        spread=spread,
        interpretation=(
            "Group means are a descriptive comparison only and are not evidence of stability."
            if status == "descriptive_comparison"
            else "Fewer than two adequately sized groups; no spread or stability claim."
        ),
    )


def _fisher_interval(rho: float, sample_size: int) -> tuple[float, float]:
    bounded_rho = float(np.clip(rho, -0.999999, 0.999999))
    transformed = atanh(bounded_rho)
    margin = 1.96 / sqrt(sample_size - 3)
    return (tanh(transformed - margin), tanh(transformed + margin))


def _exact_permutation_p_value(metric: np.ndarray, outcome: np.ndarray) -> float:
    metric_ranks = rankdata(metric).astype(float)
    outcome_ranks = rankdata(outcome).astype(float)
    centered_metric = metric_ranks - metric_ranks.mean()
    centered_outcome = outcome_ranks - outcome_ranks.mean()
    denominator = float(np.linalg.norm(centered_metric) * np.linalg.norm(centered_outcome))
    observed = float(np.dot(centered_metric, centered_outcome) / denominator)
    extreme = 0
    for permutation in permutations(centered_outcome):
        rho = float(np.dot(centered_metric, permutation) / denominator)
        if abs(rho) >= abs(observed) - 1e-12:
            extreme += 1
    return extreme / factorial(len(metric))


def _empty_association(
    outcome_name: str,
    outcome_quality: _SeriesQuality,
    paired_sample_size: int,
    reason: str,
    outcomes_tested_count: int,
) -> OutcomeAssociation:
    return OutcomeAssociation(
        outcome_name=outcome_name,
        paired_sample_size=paired_sample_size,
        outcome_raw_missing_count=outcome_quality.raw_missing_count,
        outcome_invalid_nonnumeric_count=outcome_quality.invalid_nonnumeric_count,
        outcome_positive_infinity_count=outcome_quality.positive_infinity_count,
        outcome_negative_infinity_count=outcome_quality.negative_infinity_count,
        outcome_finite_count=outcome_quality.finite_count,
        spearman_rho=None,
        raw_p_value=None,
        adjusted_p_value=None,
        outcomes_tested_count=outcomes_tested_count,
        adjustment_method="Holm",
        inference_method="not_estimated",
        confidence_interval_95=None,
        uncertainty_reason=reason,
        reason=reason,
        interpretation="No valid association was estimated; no causal conclusion.",
    )


def _association(
    joined: pd.DataFrame,
    metric_name: str,
    outcome_name: str,
    minimum_sample_size: int,
    outcomes_tested_count: int,
) -> OutcomeAssociation:
    metric, metric_quality = _series_quality(joined[metric_name])
    outcome, outcome_quality = _series_quality(joined[f"__outcome__{outcome_name}"])
    finite = np.isfinite(metric) & np.isfinite(outcome)
    paired_metric = metric[finite].to_numpy()
    paired_outcome = outcome[finite].to_numpy()
    paired_count = len(paired_metric)
    if (
        metric_quality.invalid_nonnumeric_count
        or metric_quality.positive_infinity_count
        or metric_quality.negative_infinity_count
    ):
        return _empty_association(
            outcome_name,
            outcome_quality,
            paired_count,
            "invalid_metric_values",
            outcomes_tested_count,
        )
    if (
        outcome_quality.invalid_nonnumeric_count
        or outcome_quality.positive_infinity_count
        or outcome_quality.negative_infinity_count
    ):
        return _empty_association(
            outcome_name,
            outcome_quality,
            paired_count,
            "invalid_outcome_values",
            outcomes_tested_count,
        )
    if paired_count == 0:
        return _empty_association(
            outcome_name, outcome_quality, 0, "no_finite_pairs", outcomes_tested_count
        )
    if paired_count < minimum_sample_size:
        return _empty_association(
            outcome_name,
            outcome_quality,
            paired_count,
            "insufficient_paired_sample",
            outcomes_tested_count,
        )
    if float(np.var(paired_metric)) == 0.0:
        return _empty_association(
            outcome_name,
            outcome_quality,
            paired_count,
            "zero_variance_metric",
            outcomes_tested_count,
        )
    if float(np.var(paired_outcome)) == 0.0:
        return _empty_association(
            outcome_name,
            outcome_quality,
            paired_count,
            "zero_variance_outcome",
            outcomes_tested_count,
        )

    statistic = spearmanr(paired_metric, paired_outcome)
    rho = float(statistic.statistic)
    if paired_count <= _EXACT_PERMUTATION_MAXIMUM_SAMPLE:
        raw_p_value = _exact_permutation_p_value(paired_metric, paired_outcome)
        inference_method = "exact_two_sided_permutation_spearman"
        interval = None
        uncertainty_reason = "population_interval_unavailable_for_exact_test"
        reason = None
    elif paired_count < _ASYMPTOTIC_MINIMUM_SAMPLE:
        raw_p_value = None
        inference_method = "descriptive_only_small_sample"
        interval = None
        uncertainty_reason = "inferential_sample_too_small_for_asymptotic_test"
        reason = "inferential_sample_too_small_for_asymptotic_test"
    else:
        raw_p_value = float(statistic.pvalue)
        inference_method = "asymptotic_spearman"
        interval = _fisher_interval(rho, paired_count)
        uncertainty_reason = "approximate_fisher_z_interval_for_spearman"
        reason = None
    return OutcomeAssociation(
        outcome_name=outcome_name,
        paired_sample_size=paired_count,
        outcome_raw_missing_count=outcome_quality.raw_missing_count,
        outcome_invalid_nonnumeric_count=outcome_quality.invalid_nonnumeric_count,
        outcome_positive_infinity_count=outcome_quality.positive_infinity_count,
        outcome_negative_infinity_count=outcome_quality.negative_infinity_count,
        outcome_finite_count=outcome_quality.finite_count,
        spearman_rho=rho,
        raw_p_value=raw_p_value,
        adjusted_p_value=None,
        outcomes_tested_count=outcomes_tested_count,
        adjustment_method="Holm",
        inference_method=inference_method,
        confidence_interval_95=interval,
        uncertainty_reason=uncertainty_reason,
        reason=reason,
        interpretation="Spearman association is descriptive and is not a causal effect.",
    )


def _holm_adjust(associations: tuple[OutcomeAssociation, ...]) -> tuple[OutcomeAssociation, ...]:
    family_size = len(associations)
    ordered = sorted(
        (
            (index, association.raw_p_value, association.outcome_name)
            for index, association in enumerate(associations)
            if association.raw_p_value is not None
        ),
        key=lambda item: (item[1], item[2]),
    )
    adjusted_by_index: dict[int, float] = {}
    running_maximum = 0.0
    for rank, (index, raw_p_value, _) in enumerate(ordered):
        if raw_p_value is None:  # pragma: no cover - excluded above
            continue
        candidate = min(1.0, (family_size - rank) * raw_p_value)
        running_maximum = max(running_maximum, candidate)
        adjusted_by_index[index] = running_maximum
    return tuple(
        replace(association, adjusted_p_value=adjusted_by_index.get(index))
        for index, association in enumerate(associations)
    )


def _redundancy_diagnostics(
    frame: pd.DataFrame,
    metric_columns: tuple[str, ...],
    minimum_sample_size: int,
) -> dict[str, tuple[RedundancyDiagnostic, ...]]:
    by_metric: dict[str, list[RedundancyDiagnostic]] = {name: [] for name in metric_columns}
    for index, left_name in enumerate(metric_columns):
        left, left_quality = _series_quality(frame[left_name])
        for right_name in metric_columns[index + 1 :]:
            right, right_quality = _series_quality(frame[right_name])
            finite = np.isfinite(left) & np.isfinite(right)
            left_values = left[finite].to_numpy()
            right_values = right[finite].to_numpy()
            paired_count = len(left_values)
            rho: float | None = None
            direction: Literal["positive", "negative", "none", "unavailable"] = "unavailable"
            has_invalid = any(
                (
                    left_quality.invalid_nonnumeric_count,
                    left_quality.positive_infinity_count,
                    left_quality.negative_infinity_count,
                    right_quality.invalid_nonnumeric_count,
                    right_quality.positive_infinity_count,
                    right_quality.negative_infinity_count,
                )
            )
            if has_invalid:
                reason = "invalid_metric_values"
            elif paired_count < minimum_sample_size:
                reason = "insufficient_paired_sample"
            elif float(np.var(left_values)) == 0.0 or float(np.var(right_values)) == 0.0:
                reason = "zero_variance_metric"
            else:
                rho = float(spearmanr(left_values, right_values).statistic)
                direction = "positive" if rho > 0 else "negative" if rho < 0 else "none"
                reason = (
                    "absolute_spearman_at_or_above_threshold"
                    if abs(rho) >= _REDUNDANCY_ABSOLUTE_RHO
                    else "absolute_spearman_below_threshold"
                )
            diagnostic = RedundancyDiagnostic(
                metric_a=left_name,
                metric_b=right_name,
                spearman_rho=rho,
                direction=direction,
                paired_sample_size=paired_count,
                threshold=_REDUNDANCY_ABSOLUTE_RHO,
                reason=reason,
            )
            by_metric[left_name].append(diagnostic)
            by_metric[right_name].append(diagnostic)
    return {
        name: tuple(sorted(items, key=lambda item: (item.metric_a, item.metric_b)))
        for name, items in by_metric.items()
    }


def validate_metrics(
    metric_frame: pd.DataFrame,
    outcome_frame: pd.DataFrame | None,
    *,
    observation_key_columns: Sequence[str],
    metric_columns: Sequence[str] | None = None,
    outcome_columns: Sequence[str] | None = None,
    minimum_sample_size: int = 5,
    minimum_group_size: int = 2,
    synthetic: bool = True,
) -> tuple[MetricValidationResult, ...]:
    """Validate keyed candidate metrics without positional joins or causal claims."""

    if minimum_sample_size < 3:
        raise ValueError("minimum_sample_size must be at least 3")
    if minimum_group_size < 1:
        raise ValueError("minimum_group_size must be at least 1")
    if not isinstance(metric_frame, pd.DataFrame):
        raise TypeError("metric_frame must be a pandas DataFrame")
    if outcome_frame is not None and not isinstance(outcome_frame, pd.DataFrame):
        raise TypeError("outcome_frame must be a pandas DataFrame or None")

    keys = _observation_keys(observation_key_columns)
    _validate_observation_keys(metric_frame, keys, frame_name="metric frame")
    metrics = _ordered_columns(
        metric_frame,
        metric_columns,
        excluded=set(_IDENTIFIER_COLUMNS) | set(keys),
    )
    if not metrics:
        raise ValueError("metric_frame contains no metric columns")

    joined: pd.DataFrame | None = None
    outcomes: tuple[str, ...] = ()
    if outcome_frame is not None:
        _validate_observation_keys(outcome_frame, keys, frame_name="outcome frame")
        metric_universe = _key_universe(metric_frame, keys)
        outcome_universe = _key_universe(outcome_frame, keys)
        if metric_universe != outcome_universe:
            raise ValueError(
                "metric and outcome key universe mismatch: "
                f"metric_only={len(metric_universe - outcome_universe)}, "
                f"outcome_only={len(outcome_universe - metric_universe)}"
            )
        outcomes = _ordered_columns(
            outcome_frame,
            outcome_columns,
            excluded=set(_IDENTIFIER_COLUMNS) | set(keys),
        )
        renamed_outcomes = outcome_frame.loc[:, [*keys, *outcomes]].rename(
            columns={name: f"__outcome__{name}" for name in outcomes}
        )
        joined = metric_frame.merge(
            renamed_outcomes,
            how="inner",
            on=list(keys),
            sort=True,
            validate="one_to_one",
        )

    redundancy = _redundancy_diagnostics(metric_frame, metrics, minimum_sample_size)
    results: list[MetricValidationResult] = []
    for metric_name in metrics:
        values, quality = _series_quality(metric_frame[metric_name])
        finite = values[np.isfinite(values)]
        variance = float(finite.var(ddof=0)) if quality.finite_count else None
        reasons: list[str] = []
        if quality.raw_missing_count == len(metric_frame):
            reasons.append("all_missing")
        if quality.invalid_nonnumeric_count:
            reasons.append("invalid_nonnumeric_values")
        if quality.positive_infinity_count or quality.negative_infinity_count:
            reasons.append("infinite_values")
        if quality.finite_count < minimum_sample_size:
            reasons.append("insufficient_sample")
        if quality.finite_count and variance == 0.0:
            reasons.append("zero_variance")

        associations = (
            _holm_adjust(
                tuple(
                    _association(
                        joined,
                        metric_name,
                        outcome_name,
                        minimum_sample_size,
                        len(outcomes),
                    )
                    for outcome_name in outcomes
                )
            )
            if joined is not None and outcomes
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
                "invalid_nonnumeric_values",
                "infinite_values",
                "insufficient_sample",
                "zero_variance",
            }
            for reason in reasons
        )
        promising = any(
            association.reason is None
            and association.spearman_rho is not None
            and association.adjusted_p_value is not None
            and abs(association.spearman_rho) >= _PROMISING_ABSOLUTE_RHO
            and association.adjusted_p_value <= _PROMISING_P_VALUE
            and association.inference_method
            in {"exact_two_sided_permutation_spearman", "asymptotic_spearman"}
            for association in associations
        )
        status: MetricStatus = "Rejected" if rejected else "Promising" if promising else "Candidate"
        if status == "Promising":
            reasons.append("synthetic_association_only" if synthetic else "association_observed")

        results.append(
            MetricValidationResult(
                metric_name=metric_name,
                status=status,
                synthetic=synthetic,
                sample_size=len(metric_frame),
                raw_missing_count=quality.raw_missing_count,
                invalid_nonnumeric_count=quality.invalid_nonnumeric_count,
                positive_infinity_count=quality.positive_infinity_count,
                negative_infinity_count=quality.negative_infinity_count,
                finite_count=quality.finite_count,
                variance=variance,
                community_diagnostics=_group_diagnostics(
                    metric_frame, metric_name, "community_id", minimum_group_size
                ),
                language_diagnostics=_group_diagnostics(
                    metric_frame, metric_name, "language", minimum_group_size
                ),
                redundancy_diagnostics=redundancy[metric_name],
                associations=associations,
                minimum_sample_size=minimum_sample_size,
                minimum_group_size=minimum_group_size,
                promising_absolute_rho_threshold=_PROMISING_ABSOLUTE_RHO,
                promising_p_value_threshold=_PROMISING_P_VALUE,
                redundancy_absolute_rho_threshold=_REDUNDANCY_ABSOLUTE_RHO,
                reasons=tuple(dict.fromkeys(reasons)),
                interpretation=(
                    "Synthetic diagnostics report association only; association is not "
                    "causality, group comparisons are descriptive, and human review is required."
                    if synthetic
                    else "Diagnostics report association only, not a causal effect."
                ),
            )
        )
    return tuple(sorted(results, key=lambda item: item.metric_name))

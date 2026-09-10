"""Community-scoped campaign judgments from explicit curated resources."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Literal

from community_intelligence.message_rules import normalize_text, validate_message_graph
from community_intelligence.models import CampaignRecord, ClaimRecord, MessageRecord

CampaignJudgmentStatus = Literal[
    "covered",
    "partially_covered",
    "contradicted",
    "incorrect",
    "not_covered",
    "uncertain",
]

SEMANTIC_COVERAGE_FORMULA = "(covered + 0.5 * partially_covered) / total_claims"
CLAIM_COMPLETENESS_FORMULA = "covered / total_claims"
CAMPAIGN_SUMMARY_DENOMINATOR = "all atomic claims for the campaign in this community"
BASELINE_LIMITATION = (
    "Deterministic curated phrase baseline; literal matching is not full semantic AI and "
    "requires human review."
)
CONFIDENCE_SEMANTICS = "deterministic curated evidence strength; not a correctness probability"


@dataclass(frozen=True)
class CampaignClaimResource:
    """Explicit multilingual phrases for one atomic campaign claim."""

    claim_id: str
    aliases: tuple[str, ...]
    partial_aliases: tuple[str, ...] = ()
    contradiction_patterns: tuple[str, ...] = ()
    incorrect_patterns: tuple[str, ...] = ()
    uncertain_patterns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.claim_id.strip():
            raise ValueError("claim_id must not be empty")
        if not self.aliases:
            raise ValueError("aliases must not be empty")
        patterns = (
            self.aliases
            + self.partial_aliases
            + self.contradiction_patterns
            + self.incorrect_patterns
            + self.uncertain_patterns
        )
        if any(not item.strip() for item in patterns):
            raise ValueError("campaign match patterns must not be empty")


@dataclass(frozen=True)
class CampaignResource:
    campaign_id: str
    claims: tuple[CampaignClaimResource, ...]

    def __post_init__(self) -> None:
        claim_ids = [claim.claim_id for claim in self.claims]
        if not self.campaign_id.strip():
            raise ValueError("campaign_id must not be empty")
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("campaign resource claim_id values must be unique")


@dataclass(frozen=True)
class CampaignClaimJudgment:
    campaign_id: str
    claim_id: str
    community_id: str
    status: CampaignJudgmentStatus
    confidence: float
    evidence_message_ids: tuple[str, ...]
    evidence_text: tuple[str, ...]
    translation: str | None
    notes: str
    method: str
    review_status: str
    match_strength: float
    confidence_semantics: str = CONFIDENCE_SEMANTICS
    general_semantic_ai: str = "Not implemented"


@dataclass(frozen=True)
class CampaignCommunitySummary:
    campaign_id: str
    community_id: str
    total_claims: int
    semantic_coverage: float
    claim_completeness: float
    accuracy_warning_count: int
    semantic_drift_count: int
    status_counts: tuple[tuple[str, int], ...]
    semantic_coverage_formula: str = SEMANTIC_COVERAGE_FORMULA
    claim_completeness_formula: str = CLAIM_COMPLETENESS_FORMULA
    denominator: str = CAMPAIGN_SUMMARY_DENOMINATOR
    method: str = "curated_alias_baseline"
    interpretation_limit: str = BASELINE_LIMITATION


@dataclass(frozen=True)
class _Match:
    message: MessageRecord
    status: CampaignJudgmentStatus
    strength: float


def _longest_matched_pattern(
    text: str,
    patterns: tuple[str, ...],
) -> int:
    normalized_text = normalize_text(text)
    lengths = [
        len(normalize_text(pattern))
        for pattern in patterns
        if normalize_text(pattern) in normalized_text
    ]
    return max(lengths, default=0)


def _claim_matches(
    messages: tuple[MessageRecord, ...], resource: CampaignClaimResource
) -> list[_Match]:
    status_patterns: tuple[tuple[CampaignJudgmentStatus, tuple[str, ...]], ...] = (
        ("covered", resource.aliases),
        ("partially_covered", resource.partial_aliases),
        ("contradicted", resource.contradiction_patterns),
        ("incorrect", resource.incorrect_patterns),
        ("uncertain", resource.uncertain_patterns),
    )
    matches: list[_Match] = []
    for message in messages:
        matched_lengths = {
            status: _longest_matched_pattern(message.text, patterns)
            for status, patterns in status_patterns
            if patterns
        }
        longest_match = max(matched_lengths.values(), default=0)
        matches.extend(
            _Match(
                message=message,
                status=status,
                strength={"partially_covered": 0.6, "uncertain": 0.5}.get(status, 1.0),
            )
            for status, length in matched_lengths.items()
            if length == longest_match and length > 0
        )
    return matches


def _judgment(
    campaign_id: str,
    claim_id: str,
    community_id: str,
    matches: list[_Match],
) -> CampaignClaimJudgment:
    matched_statuses = {match.status for match in matches}
    if not matches:
        status: CampaignJudgmentStatus = "not_covered"
    elif len(matched_statuses) == 1:
        status = next(iter(matched_statuses))
    else:
        status = "uncertain"

    evidence_by_id = {match.message.message_id: match.message for match in matches}
    evidence = sorted(
        evidence_by_id.values(),
        key=lambda message: (message.timestamp, message.message_id),
    )
    match_strength = (
        0.5
        if len(matched_statuses) > 1
        else max((match.strength for match in matches), default=0.0)
    )
    notes = BASELINE_LIMITATION
    if len(matched_statuses) > 1:
        notes = f"Conflicting curated evidence categories: {sorted(matched_statuses)}. {notes}"
    return CampaignClaimJudgment(
        campaign_id=campaign_id,
        claim_id=claim_id,
        community_id=community_id,
        status=status,
        confidence=round(match_strength, 6),
        evidence_message_ids=tuple(message.message_id for message in evidence),
        evidence_text=tuple(message.text for message in evidence),
        translation=None,
        notes=notes,
        method="curated_alias_baseline",
        review_status="pending",
        match_strength=round(match_strength, 6),
    )


def analyze_campaign(
    campaign: CampaignRecord,
    claims: list[ClaimRecord],
    messages: list[MessageRecord],
    resource: CampaignResource,
    *,
    community_ids: list[str] | None = None,
) -> tuple[CampaignClaimJudgment, ...]:
    """Judge each atomic claim independently in every requested community."""

    if resource.campaign_id != campaign.campaign_id:
        raise ValueError("resource campaign_id must match campaign")
    if any(claim.campaign_id != campaign.campaign_id for claim in claims):
        raise ValueError("all claims must belong to the campaign")
    claim_ids = [claim.claim_id for claim in claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("claim_id values must be unique")
    resource_claim_ids = {item.claim_id for item in resource.claims}
    if set(claim_ids) != resource_claim_ids:
        raise ValueError("claim IDs and campaign resource claim IDs must be exactly equal")

    validated = validate_message_graph(messages)
    requested_communities = (
        tuple(validated.community_ids) if community_ids is None else tuple(sorted(community_ids))
    )
    if len(requested_communities) != len(set(requested_communities)) or any(
        not community_id.strip() for community_id in requested_communities
    ):
        raise ValueError("community_ids must be unique non-empty values")

    scoped_by_community: dict[str, list[MessageRecord]] = defaultdict(list)
    for message in validated.messages:
        if (
            message.community_id in requested_communities
            and message.campaign_id == campaign.campaign_id
            and campaign.start_time <= message.timestamp < campaign.end_time
        ):
            scoped_by_community[message.community_id].append(message)

    resource_by_claim = {item.claim_id: item for item in resource.claims}

    judgments: list[CampaignClaimJudgment] = []
    for community_id in requested_communities:
        community_messages = tuple(scoped_by_community[community_id])
        for claim in claims:
            judgments.append(
                _judgment(
                    campaign.campaign_id,
                    claim.claim_id,
                    community_id,
                    _claim_matches(community_messages, resource_by_claim[claim.claim_id]),
                )
            )
    return tuple(judgments)


def summarize_campaign(
    judgments: tuple[CampaignClaimJudgment, ...] | list[CampaignClaimJudgment],
    *,
    expected_claim_ids: tuple[str, ...] | list[str],
) -> tuple[CampaignCommunitySummary, ...]:
    """Aggregate claim judgments using explicit formulas and denominators."""

    expected = tuple(expected_claim_ids)
    if (
        not expected
        or len(expected) != len(set(expected))
        or any(not claim_id.strip() for claim_id in expected)
    ):
        raise ValueError("expected_claim_ids must be unique non-empty values")
    expected_set = set(expected)

    grouped: dict[tuple[str, str], list[CampaignClaimJudgment]] = defaultdict(list)
    for judgment in judgments:
        grouped[(judgment.campaign_id, judgment.community_id)].append(judgment)

    summaries: list[CampaignCommunitySummary] = []
    for (campaign_id, community_id), group in sorted(grouped.items()):
        claim_ids = [judgment.claim_id for judgment in group]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("campaign summary requires one judgment per claim and community")
        if set(claim_ids) != expected_set:
            raise ValueError(
                "campaign summary requires the complete expected claim universe per community"
            )
        counts = Counter(judgment.status for judgment in group)
        total_claims = len(group)
        summaries.append(
            CampaignCommunitySummary(
                campaign_id=campaign_id,
                community_id=community_id,
                total_claims=total_claims,
                semantic_coverage=(counts["covered"] + 0.5 * counts["partially_covered"])
                / total_claims,
                claim_completeness=counts["covered"] / total_claims,
                accuracy_warning_count=sum(
                    counts[status] for status in ("contradicted", "incorrect", "uncertain")
                ),
                semantic_drift_count=counts["contradicted"] + counts["incorrect"],
                status_counts=tuple(sorted(counts.items())),
            )
        )
    return tuple(summaries)

"""Deterministic campaign-claim coverage from explicit curated resources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from community_intelligence.message_rules import normalize_text, validate_message_graph
from community_intelligence.models import CampaignRecord, ClaimRecord, MessageRecord

CampaignJudgmentStatus = Literal["covered", "missing", "incorrect", "ambiguous"]


@dataclass(frozen=True)
class CampaignClaimResource:
    """Explicit multilingual phrases for one atomic campaign claim."""

    claim_id: str
    aliases: tuple[str, ...]
    contradiction_patterns: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.claim_id.strip():
            raise ValueError("claim_id must not be empty")
        if not self.aliases:
            raise ValueError("aliases must not be empty")
        if any(not item.strip() for item in self.aliases + self.contradiction_patterns):
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
    claim_id: str
    status: CampaignJudgmentStatus
    confidence: float
    match_strength: float
    evidence_message_ids: tuple[str, ...]
    evidence_texts: tuple[str, ...]
    method: str = "curated_alias_baseline"
    general_semantic_ai: str = "Not implemented"


@dataclass(frozen=True)
class _Match:
    message: MessageRecord
    strength: float


def _pattern_strength(pattern: str, longest_pattern_length: int) -> float:
    return len(normalize_text(pattern)) / longest_pattern_length


def _best_match(
    text: str,
    patterns: tuple[str, ...],
    longest_pattern_length: int,
) -> float:
    normalized_text = normalize_text(text)
    strengths = [
        _pattern_strength(pattern, longest_pattern_length)
        for pattern in patterns
        if normalize_text(pattern) in normalized_text
    ]
    return max(strengths, default=0.0)


def _claim_matches(
    messages: tuple[MessageRecord, ...], resource: CampaignClaimResource
) -> tuple[list[_Match], list[_Match]]:
    all_patterns = resource.aliases + resource.contradiction_patterns
    longest_pattern_length = max(len(normalize_text(pattern)) for pattern in all_patterns)
    positive: list[_Match] = []
    negative: list[_Match] = []
    for message in messages:
        positive_strength = _best_match(message.text, resource.aliases, longest_pattern_length)
        negative_strength = _best_match(
            message.text, resource.contradiction_patterns, longest_pattern_length
        )
        if positive_strength > negative_strength:
            positive.append(_Match(message, positive_strength))
        elif negative_strength > positive_strength:
            negative.append(_Match(message, negative_strength))
        elif positive_strength:
            positive.append(_Match(message, positive_strength))
            negative.append(_Match(message, negative_strength))
    return positive, negative


def analyze_campaign(
    campaign: CampaignRecord,
    claims: list[ClaimRecord],
    messages: list[MessageRecord],
    resource: CampaignResource,
) -> list[CampaignClaimJudgment]:
    """Judge atomic claims without consulting synthetic annotation labels."""

    if resource.campaign_id != campaign.campaign_id:
        raise ValueError("resource campaign_id must match campaign")
    if any(claim.campaign_id != campaign.campaign_id for claim in claims):
        raise ValueError("all claims must belong to the campaign")

    validated = validate_message_graph(messages)
    scoped_messages = tuple(
        message
        for message in validated.messages
        if message.campaign_id == campaign.campaign_id
        and campaign.start_time <= message.timestamp < campaign.end_time
    )
    resource_by_claim = {item.claim_id: item for item in resource.claims}
    missing_resources = [
        claim.claim_id for claim in claims if claim.claim_id not in resource_by_claim
    ]
    if missing_resources:
        raise ValueError(f"missing campaign resources for claims: {', '.join(missing_resources)}")

    judgments: list[CampaignClaimJudgment] = []
    for claim in claims:
        positive, negative = _claim_matches(scoped_messages, resource_by_claim[claim.claim_id])
        if positive and negative:
            status: CampaignJudgmentStatus = "ambiguous"
            evidence = positive + negative
        elif positive:
            status = "covered"
            evidence = positive
        elif negative:
            status = "incorrect"
            evidence = negative
        else:
            status = "missing"
            evidence = []

        evidence_by_id = {match.message.message_id: match for match in evidence}
        ordered_evidence = sorted(
            evidence_by_id.values(),
            key=lambda match: (
                match.message.timestamp,
                match.message.community_id,
                match.message.message_id,
            ),
        )
        match_strength = max((match.strength for match in evidence), default=0.0)
        judgments.append(
            CampaignClaimJudgment(
                claim_id=claim.claim_id,
                status=status,
                confidence=round(match_strength, 6),
                match_strength=round(match_strength, 6),
                evidence_message_ids=tuple(
                    match.message.message_id for match in ordered_evidence
                ),
                evidence_texts=tuple(match.message.text for match in ordered_evidence),
            )
        )
    return judgments

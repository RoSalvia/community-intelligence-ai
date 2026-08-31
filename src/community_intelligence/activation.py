"""Deterministic real-user activation metrics separated from moderator activity."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from community_intelligence.episodes import is_question
from community_intelligence.message_rules import (
    MeaningfulTextRule,
    classify_meaningful_text,
    validate_message_graph,
)
from community_intelligence.models import MessageRecord

RULE_VERSION = "2.0.0"


@dataclass(frozen=True)
class ActivationEvidence:
    metric_id: str
    rule_id: str
    rule_version: str
    threshold: int | float | str | None
    raw_metric: int | float | str | None
    supporting_message_ids: tuple[str, ...]


@dataclass(frozen=True)
class MetricMetadata:
    numerator: str
    denominator: str
    numerator_value: float
    denominator_count: int
    observation_count: int
    aggregation_method: str
    unit: str
    inclusion_rules: str

    @property
    def numerator_count(self) -> float:
        """Compatibility accessor for count-based ratio metadata."""

        return self.numerator_value


@dataclass(frozen=True)
class ActivationResult:
    unique_engaged_users: int
    moderator_messages: int
    user_messages: int
    self_reply_count: int
    user_to_user_interaction_ratio: float
    peer_support_ratio: float
    meaningful_interaction_ratio: float
    response_latency_seconds: float | None
    included_community_ids: tuple[str, ...]
    observed_start: datetime | None
    observed_end: datetime | None
    analysis_rule_version: str
    meaningful_interaction_rules: tuple[MeaningfulTextRule, ...]
    metadata: Mapping[str, MetricMetadata]
    evidence: tuple[ActivationEvidence, ...]

    @property
    def response_latency(self) -> float | None:
        """Compatibility name for mean first-moderator-response latency."""

        return self.response_latency_seconds


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def analyze_activation(messages: list[MessageRecord]) -> ActivationResult:
    """Calculate scoped activity and real-user activation observations.

    Bots are excluded. Cross-user interaction requires different user IDs;
    self-replies are reported separately. Meaningful interaction uses exposed
    language-specific rules. Response latency is the mean first direct moderator
    reply per user message, not the mean of every moderator reply.
    """

    validated = validate_message_graph(messages)
    ordered = validated.messages
    message_by_id = validated.message_by_id
    user_messages = tuple(message for message in ordered if message.user_role == "user")
    moderator_messages = tuple(
        message for message in ordered if message.user_role == "moderator"
    )
    evidence: list[ActivationEvidence] = []

    meaningful_ids: list[str] = []
    meaningful_rules: dict[str, MeaningfulTextRule] = {}
    for message in user_messages:
        classification = classify_meaningful_text(message.text, message.language)
        rule = classification.rule
        meaningful_rules[rule.primary_language] = rule
        if not classification.is_meaningful:
            continue
        meaningful_ids.append(message.message_id)
        evidence.append(
            ActivationEvidence(
                metric_id="meaningful_interaction_ratio",
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                threshold=rule.minimum_characters,
                raw_metric=classification.normalized_character_count,
                supporting_message_ids=(message.message_id,),
            )
        )

    user_edges: list[tuple[MessageRecord, MessageRecord]] = []
    self_edges: list[tuple[MessageRecord, MessageRecord]] = []
    peer_edges: list[tuple[MessageRecord, MessageRecord]] = []
    moderator_replies: dict[str, list[MessageRecord]] = {}
    for child in ordered:
        parent = message_by_id.get(child.reply_to_message_id or "")
        if parent is None:
            continue
        if parent.user_role == "user" and child.user_role == "user":
            if parent.user_id_hash == child.user_id_hash:
                self_edges.append((parent, child))
                evidence.append(
                    ActivationEvidence(
                        metric_id="self_reply_count",
                        rule_id="direct_self_reply_v1",
                        rule_version=RULE_VERSION,
                        threshold=None,
                        raw_metric=1,
                        supporting_message_ids=(parent.message_id, child.message_id),
                    )
                )
            else:
                user_edges.append((parent, child))
                evidence.append(
                    ActivationEvidence(
                        metric_id="user_to_user_interaction_ratio",
                        rule_id="direct_different_user_reply_v1",
                        rule_version=RULE_VERSION,
                        threshold=None,
                        raw_metric=1,
                        supporting_message_ids=(parent.message_id, child.message_id),
                    )
                )
                if is_question(parent.text) and not is_question(child.text):
                    peer_edges.append((parent, child))
                    evidence.append(
                        ActivationEvidence(
                            metric_id="peer_support_ratio",
                            rule_id="peer_non_question_reply_v1",
                            rule_version=RULE_VERSION,
                            threshold=None,
                            raw_metric=1,
                            supporting_message_ids=(parent.message_id, child.message_id),
                        )
                    )
        if parent.user_role == "user" and child.user_role == "moderator":
            moderator_replies.setdefault(parent.message_id, []).append(child)

    first_responses = [
        (
            message_by_id[parent_id],
            min(replies, key=lambda reply: (reply.timestamp, reply.message_id)),
        )
        for parent_id, replies in moderator_replies.items()
    ]
    first_responses.sort(key=lambda pair: (pair[0].timestamp, pair[0].message_id))
    latencies = tuple(
        (child.timestamp - parent.timestamp).total_seconds()
        for parent, child in first_responses
    )
    evidence.extend(
        ActivationEvidence(
            metric_id="response_latency_seconds",
            rule_id="first_moderator_reply_latency_v1",
            rule_version=RULE_VERSION,
            threshold=None,
            raw_metric=(child.timestamp - parent.timestamp).total_seconds(),
            supporting_message_ids=(parent.message_id, child.message_id),
        )
        for parent, child in first_responses
    )

    user_count = len(user_messages)
    user_edge_count = len(user_edges)
    peer_count = len(peer_edges)
    meaningful_count = len(meaningful_ids)
    metadata = {
        "user_to_user_interaction_ratio": MetricMetadata(
            numerator="direct different-real-user reply edges",
            denominator="all real-user messages",
            numerator_value=float(user_edge_count),
            denominator_count=user_count,
            observation_count=user_count,
            aggregation_method="ratio",
            unit="ratio",
            inclusion_rules="user role only; bots, moderators, and self-replies excluded",
        ),
        "peer_support_ratio": MetricMetadata(
            numerator="different-user, non-question replies to user questions",
            denominator="direct real-user-to-different-real-user reply edges",
            numerator_value=float(peer_count),
            denominator_count=user_edge_count,
            observation_count=user_edge_count,
            aggregation_method="ratio",
            unit="ratio",
            inclusion_rules="transparent question rule; bots and self-replies excluded",
        ),
        "meaningful_interaction_ratio": MetricMetadata(
            numerator="real-user messages passing their language-specific rule",
            denominator="all real-user messages",
            numerator_value=float(meaningful_count),
            denominator_count=user_count,
            observation_count=user_count,
            aggregation_method="ratio",
            unit="ratio",
            inclusion_rules=(
                "language-specific filler and minimum-length rules; no cross-language "
                "quality claim"
            ),
        ),
        "response_latency_seconds": MetricMetadata(
            numerator="total first-response latency seconds",
            denominator="real-user messages with a direct moderator reply",
            numerator_value=float(sum(latencies)),
            denominator_count=len(latencies),
            observation_count=len(latencies),
            aggregation_method="mean",
            unit="seconds",
            inclusion_rules="first chronological moderator reply per real-user message",
        ),
    }
    return ActivationResult(
        unique_engaged_users=len({message.user_id_hash for message in user_messages}),
        moderator_messages=len(moderator_messages),
        user_messages=user_count,
        self_reply_count=len(self_edges),
        user_to_user_interaction_ratio=_safe_ratio(user_edge_count, user_count),
        peer_support_ratio=_safe_ratio(peer_count, user_edge_count),
        meaningful_interaction_ratio=_safe_ratio(meaningful_count, user_count),
        response_latency_seconds=sum(latencies) / len(latencies) if latencies else None,
        included_community_ids=validated.community_ids,
        observed_start=ordered[0].timestamp if ordered else None,
        observed_end=ordered[-1].timestamp if ordered else None,
        analysis_rule_version=RULE_VERSION,
        meaningful_interaction_rules=tuple(
            meaningful_rules[language] for language in sorted(meaningful_rules)
        ),
        metadata=MappingProxyType(metadata),
        evidence=tuple(evidence),
    )

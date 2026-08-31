"""Deterministic real-user activation metrics separated from moderator activity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from community_intelligence.episodes import is_question
from community_intelligence.hygiene import FILLER_TERMS, normalize_text
from community_intelligence.models import MessageRecord

RULE_VERSION = "1.0.0"
MEANINGFUL_MINIMUM_CHARACTERS = 4


@dataclass(frozen=True)
class ActivationEvidence:
    metric_id: str
    rule_id: str
    rule_version: str
    threshold: int | float | str | None
    raw_metric: int | float | str | None
    supporting_message_ids: list[str]


@dataclass(frozen=True)
class MetricMetadata:
    numerator: str
    denominator: str
    numerator_count: int
    denominator_count: int
    unit: str
    inclusion_rules: str


@dataclass(frozen=True)
class ActivationResult:
    unique_engaged_users: int
    moderator_messages: int
    user_messages: int
    user_to_user_interaction_ratio: float
    peer_support_ratio: float
    meaningful_interaction_ratio: float
    response_latency_seconds: float | None
    metadata: dict[str, MetricMetadata]
    evidence: list[ActivationEvidence]

    @property
    def response_latency(self) -> float | None:
        """Compatibility name for the mean moderator response latency in seconds."""

        return self.response_latency_seconds


def _message_key(message: MessageRecord) -> tuple[datetime, str, str]:
    return (message.timestamp, message.community_id, message.message_id)


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def analyze_activation(messages: list[MessageRecord]) -> ActivationResult:
    """Calculate activity and real-user activation as separate observations.

    Bots are excluded from every activation metric. User-to-user interaction
    divides direct user-to-user reply edges by all real-user messages. Peer
    support divides non-question replies to user questions by all user-to-user
    reply edges. Meaningful interaction divides non-filler user messages with at
    least four normalized characters by all real-user messages. Response latency
    is the arithmetic mean for direct moderator replies to real-user messages.
    """

    ordered = sorted(messages, key=_message_key)
    message_by_id = {message.message_id: message for message in ordered}
    user_message_records = [message for message in ordered if message.user_role == "user"]
    moderator_message_records = [
        message for message in ordered if message.user_role == "moderator"
    ]
    unique_engaged_users = len({message.user_id_hash for message in user_message_records})

    evidence: list[ActivationEvidence] = []
    meaningful_message_ids: list[str] = []
    for message in user_message_records:
        normalized = normalize_text(message.text)
        if normalized in FILLER_TERMS or len(normalized) < MEANINGFUL_MINIMUM_CHARACTERS:
            continue
        meaningful_message_ids.append(message.message_id)
        evidence.append(
            ActivationEvidence(
                metric_id="meaningful_interaction_ratio",
                rule_id="non_filler_minimum_length.v1",
                rule_version=RULE_VERSION,
                threshold=MEANINGFUL_MINIMUM_CHARACTERS,
                raw_metric=len(normalized),
                supporting_message_ids=[message.message_id],
            )
        )

    user_to_user_edges: list[tuple[MessageRecord, MessageRecord]] = []
    peer_support_edges: list[tuple[MessageRecord, MessageRecord]] = []
    moderator_response_pairs: list[tuple[MessageRecord, MessageRecord]] = []
    for child in ordered:
        parent = message_by_id.get(child.reply_to_message_id or "")
        if parent is None:
            continue
        if parent.user_role == "user" and child.user_role == "user":
            user_to_user_edges.append((parent, child))
            evidence.append(
                ActivationEvidence(
                    metric_id="user_to_user_interaction_ratio",
                    rule_id="direct_user_reply.v1",
                    rule_version=RULE_VERSION,
                    threshold=None,
                    raw_metric=1,
                    supporting_message_ids=[parent.message_id, child.message_id],
                )
            )
            if (
                parent.user_id_hash != child.user_id_hash
                and is_question(parent.text)
                and not is_question(child.text)
            ):
                peer_support_edges.append((parent, child))
                evidence.append(
                    ActivationEvidence(
                        metric_id="peer_support_ratio",
                        rule_id="peer_reply_to_question.v1",
                        rule_version=RULE_VERSION,
                        threshold=None,
                        raw_metric=1,
                        supporting_message_ids=[parent.message_id, child.message_id],
                    )
                )
        if parent.user_role == "user" and child.user_role == "moderator":
            moderator_response_pairs.append((parent, child))
            latency = (child.timestamp - parent.timestamp).total_seconds()
            evidence.append(
                ActivationEvidence(
                    metric_id="response_latency_seconds",
                    rule_id="direct_moderator_reply_latency.v1",
                    rule_version=RULE_VERSION,
                    threshold=None,
                    raw_metric=latency,
                    supporting_message_ids=[parent.message_id, child.message_id],
                )
            )

    user_message_count = len(user_message_records)
    user_to_user_count = len(user_to_user_edges)
    peer_support_count = len(peer_support_edges)
    meaningful_count = len(meaningful_message_ids)
    latencies = [
        (child.timestamp - parent.timestamp).total_seconds()
        for parent, child in moderator_response_pairs
    ]
    response_latency_seconds = sum(latencies) / len(latencies) if latencies else None

    metadata = {
        "user_to_user_interaction_ratio": MetricMetadata(
            numerator="direct real-user-to-real-user reply edges",
            denominator="all real-user messages",
            numerator_count=user_to_user_count,
            denominator_count=user_message_count,
            unit="ratio",
            inclusion_rules="user role only; bots and moderators excluded",
        ),
        "peer_support_ratio": MetricMetadata(
            numerator="different-user, non-question replies to user questions",
            denominator="direct real-user-to-real-user reply edges",
            numerator_count=peer_support_count,
            denominator_count=user_to_user_count,
            unit="ratio",
            inclusion_rules=(
                "user role only; transparent question rule; bots and self-replies excluded"
            ),
        ),
        "meaningful_interaction_ratio": MetricMetadata(
            numerator="non-filler real-user messages meeting minimum normalized length",
            denominator="all real-user messages",
            numerator_count=meaningful_count,
            denominator_count=user_message_count,
            unit="ratio",
            inclusion_rules="user role only; NFKC/casefold/whitespace normalization",
        ),
        "response_latency_seconds": MetricMetadata(
            numerator="direct moderator reply latency observations",
            denominator="direct moderator replies to real-user messages",
            numerator_count=len(latencies),
            denominator_count=len(latencies),
            unit="seconds",
            inclusion_rules="arithmetic mean; bot replies and non-reply posts excluded",
        ),
    }
    return ActivationResult(
        unique_engaged_users=unique_engaged_users,
        moderator_messages=len(moderator_message_records),
        user_messages=user_message_count,
        user_to_user_interaction_ratio=_safe_ratio(user_to_user_count, user_message_count),
        peer_support_ratio=_safe_ratio(peer_support_count, user_to_user_count),
        meaningful_interaction_ratio=_safe_ratio(meaningful_count, user_message_count),
        response_latency_seconds=response_latency_seconds,
        metadata=metadata,
        evidence=evidence,
    )

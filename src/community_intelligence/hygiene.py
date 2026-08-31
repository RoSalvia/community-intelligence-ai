"""Deterministic, evidence-backed community hygiene signals."""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from community_intelligence.models import MessageRecord

RULE_VERSION = "1.0.0"
DEFAULT_SHORT_MESSAGE_MAX_CHARS = 3
DEFAULT_REPEATED_CONTENT_MINIMUM = 3
DEFAULT_BURST_MINIMUM_MESSAGES = 3
DEFAULT_BURST_WINDOW_SECONDS = 60

FILLER_TERMS = frozenset(
    {
        "cool",
        "great",
        "gracias",
        "好",
        "好的",
        "lol",
        "nice",
        "ok",
        "okay",
        "sí",
        "thanks",
        "thank you",
        "thx",
        "yes",
        "赞",
        "谢谢",
        "👍",
        "👌",
    }
)


@dataclass(frozen=True)
class RuleEvidence:
    """Inspectable support for one deterministic rule match."""

    rule_id: str
    rule_version: str
    threshold: int | float | str | None
    raw_metric: int | float | str | None
    window_seconds: int | None
    supporting_message_ids: list[str]


@dataclass(frozen=True)
class RatioMetadata:
    """Formula details for an aggregate ratio."""

    numerator: str
    denominator: str
    numerator_count: int
    denominator_count: int
    unit_of_analysis: str = "message"


@dataclass(frozen=True)
class BurstEvent:
    community_id: str
    user_id_hash: str
    started_at: datetime
    ended_at: datetime
    message_ids: list[str]
    rule_id: str
    rule_version: str
    threshold: int
    raw_metric: int
    window_seconds: int


@dataclass(frozen=True)
class HygieneResult:
    duplicate_ratio: float
    filler_ratio: float
    repetitive_content_ratio: float
    burst_events: list[BurstEvent]
    evidence: list[RuleEvidence]
    metadata: dict[str, RatioMetadata]
    normalized_text_by_message_id: dict[str, str]


def normalize_text(text: str) -> str:
    """Return an NFKC, casefolded, whitespace-collapsed copy of ``text``."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(normalized.split())


def _message_key(message: MessageRecord) -> tuple[datetime, str, str]:
    return (message.timestamp, message.community_id, message.message_id)


def _validate_burst_thresholds(minimum_messages: int, window_seconds: int) -> None:
    if minimum_messages < 2:
        raise ValueError("minimum_messages must be at least 2")
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")


def detect_bursts(
    messages: list[MessageRecord],
    *,
    minimum_messages: int = DEFAULT_BURST_MINIMUM_MESSAGES,
    window_seconds: int = DEFAULT_BURST_WINDOW_SECONDS,
) -> list[BurstEvent]:
    """Find UTC rolling-window bursts, scoped to one community and actor."""

    _validate_burst_thresholds(minimum_messages, window_seconds)
    grouped: dict[tuple[str, str], list[MessageRecord]] = defaultdict(list)
    for message in messages:
        grouped[(message.community_id, message.user_id_hash)].append(message)

    events: list[BurstEvent] = []
    for (community_id, user_id_hash), group in sorted(grouped.items()):
        ordered = sorted(group, key=_message_key)
        candidate_windows: list[set[int]] = []
        left = 0
        for right, current in enumerate(ordered):
            while (
                current.timestamp - ordered[left].timestamp
            ).total_seconds() > window_seconds:
                left += 1
            if right - left + 1 >= minimum_messages:
                candidate_windows.append(set(range(left, right + 1)))

        maximal_windows = [
            candidate
            for candidate in candidate_windows
            if not any(candidate < other for other in candidate_windows)
        ]
        for candidate in maximal_windows:
            member_indices = sorted(candidate)
            members = [ordered[index] for index in member_indices]
            events.append(
                BurstEvent(
                    community_id=community_id,
                    user_id_hash=user_id_hash,
                    started_at=members[0].timestamp,
                    ended_at=members[-1].timestamp,
                    message_ids=[message.message_id for message in members],
                    rule_id="posting_burst.v1",
                    rule_version=RULE_VERSION,
                    threshold=minimum_messages,
                    raw_metric=len(members),
                    window_seconds=window_seconds,
                )
            )

    return sorted(
        events,
        key=lambda event: (event.started_at, event.community_id, event.user_id_hash),
    )


def analyze_hygiene(
    messages: list[MessageRecord],
    *,
    short_message_max_chars: int = DEFAULT_SHORT_MESSAGE_MAX_CHARS,
    repeated_content_minimum: int = DEFAULT_REPEATED_CONTENT_MINIMUM,
    burst_minimum_messages: int = DEFAULT_BURST_MINIMUM_MESSAGES,
    burst_window_seconds: int = DEFAULT_BURST_WINDOW_SECONDS,
) -> HygieneResult:
    """Calculate deterministic hygiene ratios without mutating source records.

    All three ratios use every input message as their denominator. Duplicate
    messages are occurrences after the first normalized match within a
    community. Repetitive-content messages are every occurrence in a group of
    at least ``repeated_content_minimum`` posts by the same community actor.
    """

    if short_message_max_chars < 0:
        raise ValueError("short_message_max_chars must be non-negative")
    if repeated_content_minimum < 2:
        raise ValueError("repeated_content_minimum must be at least 2")
    if burst_minimum_messages < 2:
        raise ValueError("burst_minimum_messages must be at least 2")
    if burst_window_seconds <= 0:
        raise ValueError("burst_window_seconds must be positive")

    ordered = sorted(messages, key=_message_key)
    normalized = {message.message_id: normalize_text(message.text) for message in ordered}
    evidence: list[RuleEvidence] = []

    duplicate_groups: dict[tuple[str, str], list[MessageRecord]] = defaultdict(list)
    for message in ordered:
        duplicate_groups[(message.community_id, normalized[message.message_id])].append(message)
    duplicate_count = 0
    for group in duplicate_groups.values():
        if len(group) < 2:
            continue
        duplicate_count += len(group) - 1
        evidence.append(
            RuleEvidence(
                rule_id="exact_duplicate.v1",
                rule_version=RULE_VERSION,
                threshold=2,
                raw_metric=len(group),
                window_seconds=None,
                supporting_message_ids=[message.message_id for message in group],
            )
        )

    filler_count = 0
    for message in ordered:
        text = normalized[message.message_id]
        character_count = len(text)
        if text not in FILLER_TERMS and character_count > short_message_max_chars:
            continue
        filler_count += 1
        evidence.append(
            RuleEvidence(
                rule_id="filler_or_short.v1",
                rule_version=RULE_VERSION,
                threshold=short_message_max_chars,
                raw_metric=character_count,
                window_seconds=None,
                supporting_message_ids=[message.message_id],
            )
        )

    repeated_groups: dict[tuple[str, str, str], list[MessageRecord]] = defaultdict(list)
    for message in ordered:
        repeated_groups[
            (message.community_id, message.user_id_hash, normalized[message.message_id])
        ].append(message)
    repeated_count = 0
    for group in repeated_groups.values():
        if len(group) < repeated_content_minimum:
            continue
        repeated_count += len(group)
        evidence.append(
            RuleEvidence(
                rule_id="repeated_content.v1",
                rule_version=RULE_VERSION,
                threshold=repeated_content_minimum,
                raw_metric=len(group),
                window_seconds=None,
                supporting_message_ids=[message.message_id for message in group],
            )
        )

    burst_events = detect_bursts(
        ordered,
        minimum_messages=burst_minimum_messages,
        window_seconds=burst_window_seconds,
    )
    evidence.extend(
        RuleEvidence(
            rule_id=event.rule_id,
            rule_version=event.rule_version,
            threshold=event.threshold,
            raw_metric=event.raw_metric,
            window_seconds=event.window_seconds,
            supporting_message_ids=list(event.message_ids),
        )
        for event in burst_events
    )

    denominator_count = len(ordered)

    def ratio(numerator: int) -> float:
        return numerator / denominator_count if denominator_count else 0.0

    metadata = {
        "duplicate_ratio": RatioMetadata(
            numerator="normalized duplicate occurrences after the first per community",
            denominator="all input messages",
            numerator_count=duplicate_count,
            denominator_count=denominator_count,
        ),
        "filler_ratio": RatioMetadata(
            numerator="messages matching the filler lexicon or short-message threshold",
            denominator="all input messages",
            numerator_count=filler_count,
            denominator_count=denominator_count,
        ),
        "repetitive_content_ratio": RatioMetadata(
            numerator="messages in repeated normalized-content groups by community and actor",
            denominator="all input messages",
            numerator_count=repeated_count,
            denominator_count=denominator_count,
        ),
    }
    return HygieneResult(
        duplicate_ratio=ratio(duplicate_count),
        filler_ratio=ratio(filler_count),
        repetitive_content_ratio=ratio(repeated_count),
        burst_events=burst_events,
        evidence=evidence,
        metadata=metadata,
        normalized_text_by_message_id=normalized,
    )

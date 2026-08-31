"""Neutral deterministic rules shared by message analyzers."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

import networkx as nx

from community_intelligence.models import MessageRecord

MEANINGFUL_RULE_ID = "language_filler_or_min_length_v1"
MEANINGFUL_RULE_VERSION = "1.0.0"
COMPARISON_LIMIT = (
    "language-specific deterministic baseline; no cross-language quality claim"
)

_LANGUAGE_FILLERS = MappingProxyType(
    {
        "en": ("cool", "great", "lol", "nice", "ok", "okay", "thank you", "thanks", "thx", "yes"),
        "es": ("genial", "gracias", "ok", "sí", "vale"),
        "tr": ("evet", "tamam", "teşekkür ederim", "teşekkürler"),
        "ar": ("تم", "حسنا", "شكرا", "شكراً", "نعم"),
        "zh": ("好", "好的", "收到", "明白", "谢谢", "赞"),
    }
)
_MINIMUM_CHARACTERS = MappingProxyType({"en": 4, "es": 4, "tr": 4, "ar": 4, "zh": 2})
_GLOBAL_FILLERS = ("👍", "👌")


@dataclass(frozen=True)
class MeaningfulTextRule:
    primary_language: str
    minimum_characters: int
    filler_terms: tuple[str, ...]
    rule_id: str = MEANINGFUL_RULE_ID
    rule_version: str = MEANINGFUL_RULE_VERSION
    comparison_limit: str = COMPARISON_LIMIT


@dataclass(frozen=True)
class MeaningfulTextClassification:
    is_filler: bool
    is_meaningful: bool
    normalized_character_count: int
    rule: MeaningfulTextRule


@dataclass(frozen=True)
class ValidatedMessageGraph:
    """Stable, read-only view of validated public analyzer input."""

    messages: tuple[MessageRecord, ...]
    message_by_id: Mapping[str, MessageRecord]
    community_ids: tuple[str, ...]
    parent_by_child: Mapping[str, str]
    children_by_parent: Mapping[str, tuple[str, ...]]


def message_sort_key(message: MessageRecord) -> tuple[datetime, str, str]:
    return (message.timestamp, message.community_id, message.message_id)


def normalize_text(text: str) -> str:
    """Return an NFKC, casefolded, whitespace-collapsed copy of text."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(normalized.split())


def meaningful_text_rule(language: str) -> MeaningfulTextRule:
    primary_language = language.split("-", 1)[0].casefold()
    filler_terms = _LANGUAGE_FILLERS.get(primary_language, ()) + _GLOBAL_FILLERS
    return MeaningfulTextRule(
        primary_language=primary_language,
        minimum_characters=_MINIMUM_CHARACTERS.get(primary_language, 4),
        filler_terms=tuple(filler_terms),
    )


def classify_meaningful_text(text: str, language: str) -> MeaningfulTextClassification:
    normalized = normalize_text(text)
    rule = meaningful_text_rule(language)
    is_filler = normalized in rule.filler_terms
    return MeaningfulTextClassification(
        is_filler=is_filler,
        is_meaningful=not is_filler and len(normalized) >= rule.minimum_characters,
        normalized_character_count=len(normalized),
        rule=rule,
    )


def validate_unique_message_ids(messages: list[MessageRecord]) -> None:
    """Reject ambiguous message identities without imposing reply-graph rules."""

    if len({message.message_id for message in messages}) != len(messages):
        raise ValueError("message_id values must be unique")


def validate_message_graph(messages: list[MessageRecord]) -> ValidatedMessageGraph:
    """Validate the strict reply-graph contract used by public analyzers."""

    validate_unique_message_ids(messages)

    ordered = tuple(sorted(messages, key=message_sort_key))
    message_by_id = {message.message_id: message for message in ordered}
    parent_by_child: dict[str, str] = {}
    children_by_parent: dict[str, list[str]] = {}
    graph = nx.DiGraph()
    graph.add_nodes_from(message_by_id)

    for child in ordered:
        parent_id = child.reply_to_message_id
        if parent_id is None:
            continue
        parent = message_by_id.get(parent_id)
        if parent is None:
            raise ValueError(
                f"reply parent must exist: {child.message_id} -> {parent_id}"
            )
        if child.community_id != parent.community_id:
            raise ValueError("replies must remain within a community")
        if (
            child.campaign_id is not None
            and parent.campaign_id is not None
            and child.campaign_id != parent.campaign_id
        ):
            raise ValueError("replies must remain within a campaign")
        parent_by_child[child.message_id] = parent_id
        children_by_parent.setdefault(parent_id, []).append(child.message_id)
        graph.add_edge(parent_id, child.message_id)

    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("reply graph must be acyclic")

    for child_id, parent_id in parent_by_child.items():
        if message_by_id[child_id].timestamp <= message_by_id[parent_id].timestamp:
            raise ValueError("reply timestamp must be after parent timestamp")

    immutable_children = {
        parent_id: tuple(
            sorted(child_ids, key=lambda child_id: message_sort_key(message_by_id[child_id]))
        )
        for parent_id, child_ids in children_by_parent.items()
    }
    return ValidatedMessageGraph(
        messages=ordered,
        message_by_id=MappingProxyType(message_by_id),
        community_ids=tuple(sorted({message.community_id for message in ordered})),
        parent_by_child=MappingProxyType(parent_by_child),
        children_by_parent=MappingProxyType(immutable_children),
    )

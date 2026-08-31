"""Deterministic conversation episodes built from reply graphs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import networkx as nx

from community_intelligence.hygiene import normalize_text
from community_intelligence.models import MessageRecord

QUESTION_RULE_ID = "punctuation_or_phrase_question.v1"
QUESTION_RULE_VERSION = "1.0.0"
QUESTION_DETECTION_METHOD = (
    "transparent punctuation (?, ？, ؟) or language-specific question phrase rule"
)
QUESTION_PREFIXES = (
    "are ",
    "can ",
    "could ",
    "did ",
    "do ",
    "does ",
    "how ",
    "is ",
    "what ",
    "when ",
    "where ",
    "who ",
    "why ",
    "would ",
    "cómo ",
    "cuándo ",
    "dónde ",
    "por qué ",
    "pueden ",
    "qué ",
    "أين ",
    "كيف ",
    "لماذا ",
    "متى ",
    "هل ",
)
QUESTION_PHRASES = ("是不是", "为什么", "为何", "怎么", "如何")
QUESTION_SUFFIXES = ("吗", "呢")


@dataclass(frozen=True)
class ConversationEpisode:
    episode_id: str
    root_message_id: str
    community_id: str
    message_ids: list[str]
    unique_participants: int
    moderator_messages: int
    user_messages: int
    user_to_user_replies: int
    moderator_response_count: int
    first_response_latency_seconds: float | None
    conversation_depth: int
    branching_factor: float
    question_count: int
    resolved_question_count: int
    unanswered_question_count: int
    duration_seconds: float
    question_message_ids: list[str]
    resolved_question_message_ids: list[str]
    unanswered_question_message_ids: list[str]
    question_rule_id: str
    question_rule_version: str
    question_detection_method: str
    interpretation_limit: str


def is_question(text: str) -> bool:
    """Apply the exposed deterministic punctuation/phrase question rule."""

    normalized = normalize_text(text)
    if any(mark in normalized for mark in ("?", "？", "؟")):
        return True
    if normalized.startswith(QUESTION_PREFIXES):
        return True
    return any(phrase in normalized for phrase in QUESTION_PHRASES) or normalized.endswith(
        QUESTION_SUFFIXES
    )


def _message_key(message: MessageRecord) -> tuple[datetime, str, str]:
    return (message.timestamp, message.community_id, message.message_id)


def _episode_from_nodes(
    graph: nx.DiGraph,
    nodes: set[str],
    message_by_id: dict[str, MessageRecord],
) -> ConversationEpisode:
    subgraph = graph.subgraph(nodes)
    roots = [node for node in nodes if subgraph.in_degree(node) == 0]
    root_id = min(roots, key=lambda node: _message_key(message_by_id[node]))
    ordered = sorted((message_by_id[node] for node in nodes), key=_message_key)
    message_ids = [message.message_id for message in ordered]

    human_participants = {
        message.user_id_hash for message in ordered if message.user_role != "bot"
    }
    moderator_messages = sum(message.user_role == "moderator" for message in ordered)
    user_messages = sum(message.user_role == "user" for message in ordered)
    user_to_user_replies = 0
    moderator_response_count = 0
    for parent_id, child_id in subgraph.edges:
        parent = message_by_id[parent_id]
        child = message_by_id[child_id]
        if parent.user_role == "user" and child.user_role == "user":
            user_to_user_replies += 1
        if parent.user_role == "user" and child.user_role == "moderator":
            moderator_response_count += 1

    root = message_by_id[root_id]
    responses = [
        message
        for message in ordered
        if message.message_id != root_id and message.user_role != "bot"
    ]
    first_response_latency_seconds = (
        (responses[0].timestamp - root.timestamp).total_seconds() if responses else None
    )

    conversation_depth = nx.dag_longest_path_length(subgraph) + 1
    parent_degrees = [degree for _, degree in subgraph.out_degree if degree > 0]
    branching_factor = sum(parent_degrees) / len(parent_degrees) if parent_degrees else 0.0

    question_message_ids = [
        message.message_id for message in ordered if is_question(message.text)
    ]
    resolved_question_message_ids: list[str] = []
    for question_id in question_message_ids:
        question = message_by_id[question_id]
        answer_ids = sorted(
            subgraph.successors(question_id),
            key=lambda node: _message_key(message_by_id[node]),
        )
        if any(
            message_by_id[answer_id].user_role != "bot"
            and message_by_id[answer_id].user_id_hash != question.user_id_hash
            and not is_question(message_by_id[answer_id].text)
            for answer_id in answer_ids
        ):
            resolved_question_message_ids.append(question_id)
    unanswered_question_message_ids = [
        question_id
        for question_id in question_message_ids
        if question_id not in resolved_question_message_ids
    ]

    duration_seconds = (ordered[-1].timestamp - ordered[0].timestamp).total_seconds()
    return ConversationEpisode(
        episode_id=f"episode:{root_id}",
        root_message_id=root_id,
        community_id=root.community_id,
        message_ids=message_ids,
        unique_participants=len(human_participants),
        moderator_messages=moderator_messages,
        user_messages=user_messages,
        user_to_user_replies=user_to_user_replies,
        moderator_response_count=moderator_response_count,
        first_response_latency_seconds=first_response_latency_seconds,
        conversation_depth=conversation_depth,
        branching_factor=branching_factor,
        question_count=len(question_message_ids),
        resolved_question_count=len(resolved_question_message_ids),
        unanswered_question_count=len(unanswered_question_message_ids),
        duration_seconds=duration_seconds,
        question_message_ids=question_message_ids,
        resolved_question_message_ids=resolved_question_message_ids,
        unanswered_question_message_ids=unanswered_question_message_ids,
        question_rule_id=QUESTION_RULE_ID,
        question_rule_version=QUESTION_RULE_VERSION,
        question_detection_method=QUESTION_DETECTION_METHOD,
        interpretation_limit="descriptive reply-graph metrics; no causal claim",
    )


def build_episodes(messages: list[MessageRecord]) -> list[ConversationEpisode]:
    """Build one deterministic episode per reply-graph connected component."""

    if not messages:
        return []
    message_by_id = {message.message_id: message for message in messages}
    if len(message_by_id) != len(messages):
        raise ValueError("message_id values must be unique")

    graph = nx.DiGraph()
    graph.add_nodes_from(message_by_id)
    for message in messages:
        parent_id = message.reply_to_message_id
        if parent_id in message_by_id:
            graph.add_edge(parent_id, message.message_id)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("reply graph must be acyclic")

    episodes = [
        _episode_from_nodes(graph, set(component), message_by_id)
        for component in nx.weakly_connected_components(graph)
    ]
    return sorted(
        episodes,
        key=lambda episode: _message_key(message_by_id[episode.root_message_id]),
    )

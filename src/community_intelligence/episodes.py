"""Deterministic conversation episodes built from reply graphs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import networkx as nx

from community_intelligence.message_rules import normalize_text, validate_message_graph
from community_intelligence.models import MessageRecord

QUESTION_RULE_ID = "punctuation_or_phrase_question.v1"
QUESTION_RULE_VERSION = "1.0.0"
CANDIDATE_ANSWER_RULE_ID = "candidate_non_question_reply_v1"
CANDIDATE_ANSWER_RULE_VERSION = "1.0.0"
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
class CandidateAnswerEvidence:
    """Structural reply evidence that does not assert semantic resolution."""

    question_id: str
    candidate_answer_id: str
    rule_id: str
    rule_version: str


@dataclass(frozen=True)
class ConversationEpisode:
    episode_id: str
    root_message_id: str
    community_id: str
    message_ids: tuple[str, ...]
    unique_participants: int
    moderator_messages: int
    user_messages: int
    self_reply_count: int
    user_to_user_replies: int
    moderator_response_count: int
    first_response_latency_seconds: float | None
    conversation_depth: int
    branching_factor: float
    question_count: int
    candidate_answered_question_count: int
    resolved_question_count: int
    unanswered_question_count: int
    duration_seconds: float
    question_message_ids: tuple[str, ...]
    resolved_question_message_ids: tuple[str, ...]
    unanswered_question_message_ids: tuple[str, ...]
    candidate_answer_evidence: tuple[CandidateAnswerEvidence, ...]
    question_rule_id: str
    question_rule_version: str
    question_detection_method: str
    candidate_answer_rule_id: str
    candidate_answer_rule_version: str
    resolution_interpretation: str
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


def _candidate_answer_ids(
    question_id: str,
    subgraph: nx.DiGraph,
    message_by_id: dict[str, MessageRecord],
) -> tuple[str, ...]:
    """Follow question-only clarification chains to structural answer candidates."""

    question = message_by_id[question_id]
    pending = list(subgraph.successors(question_id))
    visited: set[str] = set()
    candidates: list[str] = []
    while pending:
        reply_id = min(pending, key=lambda node: _message_key(message_by_id[node]))
        pending.remove(reply_id)
        if reply_id in visited:
            continue
        visited.add(reply_id)
        reply = message_by_id[reply_id]
        if reply.user_role == "bot":
            continue
        if is_question(reply.text):
            pending.extend(subgraph.successors(reply_id))
            continue
        if reply.user_id_hash != question.user_id_hash:
            candidates.append(reply_id)
    return tuple(candidates)


def _episode_from_nodes(
    graph: nx.DiGraph,
    nodes: set[str],
    message_by_id: dict[str, MessageRecord],
) -> ConversationEpisode:
    subgraph = graph.subgraph(nodes)
    roots = [node for node in nodes if subgraph.in_degree(node) == 0]
    root_id = min(roots, key=lambda node: _message_key(message_by_id[node]))
    ordered = sorted((message_by_id[node] for node in nodes), key=_message_key)
    message_ids = tuple(message.message_id for message in ordered)

    human_participants = {
        message.user_id_hash for message in ordered if message.user_role != "bot"
    }
    moderator_messages = sum(message.user_role == "moderator" for message in ordered)
    user_messages = sum(message.user_role == "user" for message in ordered)
    user_to_user_replies = 0
    self_reply_count = 0
    moderator_response_count = 0
    for parent_id, child_id in subgraph.edges:
        parent = message_by_id[parent_id]
        child = message_by_id[child_id]
        if parent.user_role == "user" and child.user_role == "user":
            if parent.user_id_hash == child.user_id_hash:
                self_reply_count += 1
            else:
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

    question_message_ids = tuple(
        message.message_id for message in ordered if is_question(message.text)
    )
    candidate_answer_evidence: list[CandidateAnswerEvidence] = []
    for question_id in question_message_ids:
        candidate_answer_evidence.extend(
            CandidateAnswerEvidence(
                question_id=question_id,
                candidate_answer_id=answer_id,
                rule_id=CANDIDATE_ANSWER_RULE_ID,
                rule_version=CANDIDATE_ANSWER_RULE_VERSION,
            )
            for answer_id in _candidate_answer_ids(question_id, subgraph, message_by_id)
        )
    candidate_answered_question_ids = tuple(
        question_id
        for question_id in question_message_ids
        if any(item.question_id == question_id for item in candidate_answer_evidence)
    )
    unanswered_question_message_ids = tuple(
        question_id
        for question_id in question_message_ids
        if question_id not in candidate_answered_question_ids
    )

    duration_seconds = (ordered[-1].timestamp - ordered[0].timestamp).total_seconds()
    return ConversationEpisode(
        episode_id=f"episode:{root_id}",
        root_message_id=root_id,
        community_id=root.community_id,
        message_ids=message_ids,
        unique_participants=len(human_participants),
        moderator_messages=moderator_messages,
        user_messages=user_messages,
        self_reply_count=self_reply_count,
        user_to_user_replies=user_to_user_replies,
        moderator_response_count=moderator_response_count,
        first_response_latency_seconds=first_response_latency_seconds,
        conversation_depth=conversation_depth,
        branching_factor=branching_factor,
        question_count=len(question_message_ids),
        candidate_answered_question_count=len(candidate_answered_question_ids),
        resolved_question_count=len(candidate_answered_question_ids),
        unanswered_question_count=len(unanswered_question_message_ids),
        duration_seconds=duration_seconds,
        question_message_ids=question_message_ids,
        resolved_question_message_ids=candidate_answered_question_ids,
        unanswered_question_message_ids=unanswered_question_message_ids,
        candidate_answer_evidence=tuple(candidate_answer_evidence),
        question_rule_id=QUESTION_RULE_ID,
        question_rule_version=QUESTION_RULE_VERSION,
        question_detection_method=QUESTION_DETECTION_METHOD,
        candidate_answer_rule_id=CANDIDATE_ANSWER_RULE_ID,
        candidate_answer_rule_version=CANDIDATE_ANSWER_RULE_VERSION,
        resolution_interpretation=(
            "resolved_question_count is a compatibility alias for structural candidate "
            "answers; no semantic resolution claim"
        ),
        interpretation_limit="descriptive reply-graph metrics; no causal claim",
    )


def build_episodes(messages: list[MessageRecord]) -> list[ConversationEpisode]:
    """Build one deterministic episode per reply-graph connected component."""

    validated = validate_message_graph(messages)
    if not validated.messages:
        return []
    message_by_id = validated.message_by_id

    graph = nx.DiGraph()
    graph.add_nodes_from(message_by_id)
    graph.add_edges_from(
        (parent_id, child_id)
        for child_id, parent_id in validated.parent_by_child.items()
    )

    episodes = [
        _episode_from_nodes(graph, set(component), message_by_id)
        for component in nx.weakly_connected_components(graph)
    ]
    return sorted(
        episodes,
        key=lambda episode: _message_key(message_by_id[episode.root_message_id]),
    )

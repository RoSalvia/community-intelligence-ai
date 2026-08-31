"""Transparent behavior seed rules and review-first unsupervised clusters."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from community_intelligence.episodes import is_question
from community_intelligence.message_rules import normalize_text, validate_message_graph
from community_intelligence.models import MessageRecord


@dataclass(frozen=True)
class SeedBehaviorLabel:
    message_id: str
    behavior: str
    confidence: float
    evidence_message_ids: tuple[str, ...]
    evidence_texts: tuple[str, ...]
    rule_id: str
    method: str = "deterministic_seed_rule"
    general_semantic_ai: str = "Not implemented"


@dataclass(frozen=True)
class BehaviorCluster:
    cluster_id: str
    message_ids: tuple[str, ...]
    representative_message_ids: tuple[str, ...]
    language_distribution: tuple[tuple[str, int], ...]
    role_distribution: tuple[tuple[str, int], ...]
    top_terms: tuple[str, ...]
    review_status: str = "pending"
    reviewed_name: str | None = None
    method: str = "tfidf_kmeans"


def _label(
    message: MessageRecord,
    behavior: str,
    rule_id: str,
    parent: MessageRecord | None = None,
) -> SeedBehaviorLabel:
    evidence = (parent, message) if parent is not None else (message,)
    return SeedBehaviorLabel(
        message_id=message.message_id,
        behavior=behavior,
        confidence=1.0,
        evidence_message_ids=tuple(item.message_id for item in evidence),
        evidence_texts=tuple(item.text for item in evidence),
        rule_id=rule_id,
    )


def classify_seed_behaviors(
    messages: list[MessageRecord],
) -> dict[str, SeedBehaviorLabel]:
    """Assign one deterministic primary seed label per message."""

    validated = validate_message_graph(messages)
    results: dict[str, SeedBehaviorLabel] = {}
    for message in validated.messages:
        parent_id = validated.parent_by_child.get(message.message_id)
        parent = validated.message_by_id[parent_id] if parent_id is not None else None
        normalized = normalize_text(message.text)
        if is_question(message.text):
            result = _label(message, "question_asking", "question_rule_v1")
        elif (
            parent is not None
            and is_question(parent.text)
            and message.user_role != "bot"
            and message.user_id_hash != parent.user_id_hash
        ):
            result = _label(message, "question_answering", "reply_to_question_v1", parent)
        elif parent is not None and message.user_role == "moderator" and parent.user_role == "user":
            result = _label(message, "moderator_follow_up", "moderator_user_reply_v1", parent)
        elif any(
            term in normalized
            for term in (
                "confusing",
                "frustrating",
                "unclear",
                "confuso",
                "frustrante",
                "غير واضح",
                "محبط",
                "不清楚",
                "令人沮丧",
            )
        ):
            result = _label(message, "negative_feedback", "negative_phrase_v1")
        elif any(
            term in normalized
            for term in ("correction", "corrected", "actually", "更正", "纠正", "تصحيح")
        ):
            result = _label(message, "correction", "correction_phrase_v1")
        else:
            result = _label(message, "unclassified", "no_seed_rule_match_v1")
        results[message.message_id] = result
    return results


def _distribution(values: list[str]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(Counter(values).items()))


def discover_clusters(
    messages: list[MessageRecord],
    *,
    cluster_count: int,
    random_state: int,
) -> list[BehaviorCluster]:
    """Discover deterministic review candidates without assigning behavior names."""

    validated = validate_message_graph(messages)
    ordered = list(validated.messages)
    if cluster_count < 1 or cluster_count > len(ordered):
        raise ValueError("cluster_count must be between 1 and the number of messages")

    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        lowercase=True,
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(message.text for message in ordered)
    estimator = KMeans(n_clusters=cluster_count, random_state=random_state, n_init=10)
    raw_labels = estimator.fit_predict(matrix)
    terms = vectorizer.get_feature_names_out()

    raw_groups: list[tuple[int, list[int]]] = []
    for raw_label in sorted(set(int(label) for label in raw_labels)):
        member_indices = [
            index for index, label in enumerate(raw_labels) if int(label) == raw_label
        ]
        raw_groups.append((raw_label, member_indices))
    raw_groups.sort(key=lambda item: min(ordered[index].message_id for index in item[1]))

    clusters: list[BehaviorCluster] = []
    for stable_index, (raw_label, member_indices) in enumerate(raw_groups, start=1):
        members = [ordered[index] for index in member_indices]
        distances = np.linalg.norm(
            matrix[member_indices].toarray() - estimator.cluster_centers_[raw_label], axis=1
        )
        representative_indices = sorted(
            range(len(members)),
            key=lambda index: (float(distances[index]), members[index].message_id),
        )[:3]
        weighted_terms = sorted(
            enumerate(estimator.cluster_centers_[raw_label]),
            key=lambda item: (-float(item[1]), terms[item[0]]),
        )
        top_terms = tuple(terms[index] for index, weight in weighted_terms if weight > 0)[:8]
        clusters.append(
            BehaviorCluster(
                cluster_id=f"cluster_{stable_index:02d}",
                message_ids=tuple(sorted(message.message_id for message in members)),
                representative_message_ids=tuple(
                    members[index].message_id for index in representative_indices
                ),
                language_distribution=_distribution(
                    [message.language for message in members]
                ),
                role_distribution=_distribution([message.user_role for message in members]),
                top_terms=top_terms,
            )
        )
    return clusters

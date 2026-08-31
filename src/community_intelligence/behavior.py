"""Transparent behavior seed rules and review-first unsupervised clusters."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from community_intelligence.episodes import is_question
from community_intelligence.message_rules import (
    classify_meaningful_text,
    normalize_text,
    validate_message_graph,
)
from community_intelligence.models import MessageRecord

MODERATOR_SEED_TAXONOMY = (
    "campaign_propagation",
    "product_explanation",
    "question_answering",
    "conversation_initiation",
    "CTA",
    "user_onboarding",
    "conflict_handling",
    "sentiment_soothing",
    "translation",
    "misinformation_correction",
    "normal_chat",
    "filler",
    "duplicate_promotion",
    "spam",
)
USER_SEED_TAXONOMY = (
    "project_discussion",
    "campaign_question",
    "product_question",
    "complaint",
    "feedback",
    "feature_request",
    "FUD",
    "peer_support",
    "CTA_response",
    "off_topic",
    "external_information_sharing",
    "usage_intent",
)

_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


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
    top_terms: tuple[str, ...]
    representative_message_ids: tuple[str, ...]
    representative_messages: tuple[str, ...]
    language_distribution: tuple[tuple[str, int], ...]
    role_distribution: tuple[tuple[str, int], ...]
    message_count: int
    proposed_behavior_name: str | None
    behavior_description: str
    confidence: float
    review_status: str = "pending"
    method: str = "tfidf_kmeans"


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _label(
    message: MessageRecord,
    behavior: str,
    rule_id: str,
    evidence: tuple[MessageRecord, ...] | None = None,
) -> SeedBehaviorLabel:
    source = evidence or (message,)
    return SeedBehaviorLabel(
        message_id=message.message_id,
        behavior=behavior,
        confidence=1.0,
        evidence_message_ids=tuple(item.message_id for item in source),
        evidence_texts=tuple(item.text for item in source),
        rule_id=rule_id,
    )


def _moderator_label(
    message: MessageRecord,
    parent: MessageRecord | None,
    duplicates: tuple[MessageRecord, ...],
) -> SeedBehaviorLabel:
    normalized = normalize_text(message.text)
    if duplicates:
        return _label(
            message, "duplicate_promotion", "same_actor_exact_text_v1", duplicates
        )
    if classify_meaningful_text(message.text, message.language).is_filler:
        return _label(message, "filler", "language_filler_v1")
    if len(_URL_PATTERN.findall(message.text)) >= 2 or _contains_any(
        normalized, ("buy now", "guaranteed profit", "free airdrop now")
    ):
        return _label(message, "spam", "repeated_link_or_spam_phrase_v1")
    if (
        parent is not None
        and parent.user_role == "user"
        and is_question(parent.text)
        and message.user_id_hash != parent.user_id_hash
        and not is_question(message.text)
    ):
        return _label(
            message, "question_answering", "moderator_reply_to_question_v1", (parent, message)
        )
    if parent is None and is_question(message.text):
        return _label(message, "conversation_initiation", "moderator_root_question_v1")
    if _contains_any(
        normalized,
        ("correction", "corrected", "actually", "not 50", "更正", "纠正", "تصحيح"),
    ):
        return _label(message, "misinformation_correction", "correction_phrase_v1")
    if _contains_any(
        normalized, ("translation:", "translated:", "翻译：", "翻译:", "الترجمة:")
    ):
        return _label(message, "translation", "translation_marker_v1")
    if _contains_any(
        normalized,
        ("welcome new", "new members", "onboarding guide", "欢迎新成员", "新手指南"),
    ):
        return _label(message, "user_onboarding", "onboarding_phrase_v1")
    if _contains_any(
        normalized, ("resolve this dispute", "de-escalate", "conflict", "解决争议", "化解冲突")
    ):
        return _label(message, "conflict_handling", "conflict_phrase_v1")
    if _contains_any(
        normalized,
        (
            "understand your concern",
            "sorry this is frustrating",
            "we hear your concern",
            "理解你的担忧",
            "抱歉让你困扰",
        ),
    ):
        return _label(message, "sentiment_soothing", "soothing_phrase_v1")
    if _contains_any(
        normalized,
        (
            "join the campaign",
            "register now",
            "click the link",
            "stake now",
            "立即参加",
            "立即注册",
        ),
    ):
        return _label(message, "CTA", "call_to_action_phrase_v1")
    if _contains_any(
        normalized,
        (
            "product feature",
            "feature works",
            "how it works",
            "connect your wallet",
            "产品功能",
            "使用方法",
        ),
    ):
        return _label(message, "product_explanation", "product_explanation_phrase_v1")
    if message.campaign_id is not None and _contains_any(
        normalized,
        ("official campaign", "campaign update", "deadline", "reward", "活动公告", "截止", "奖励"),
    ):
        return _label(message, "campaign_propagation", "campaign_fact_phrase_v1")
    if _contains_any(
        normalized,
        ("good morning", "good afternoon", "how is everyone", "hope everyone", "大家好"),
    ):
        return _label(message, "normal_chat", "moderator_social_phrase_v1")
    return _label(message, "unclassified", "no_seed_rule_match_v1")


def _user_label(
    message: MessageRecord,
    parent: MessageRecord | None,
) -> SeedBehaviorLabel:
    normalized = normalize_text(message.text)
    if (
        parent is not None
        and parent.user_role == "user"
        and message.user_id_hash != parent.user_id_hash
        and not is_question(message.text)
    ):
        return _label(message, "peer_support", "user_reply_to_peer_v1", (parent, message))
    if is_question(message.text) and _contains_any(
        normalized, ("product", "wallet", "feature", "how does", "产品", "钱包", "功能")
    ):
        return _label(message, "product_question", "product_question_phrase_v1")
    if is_question(message.text) and (
        message.campaign_id is not None
        or _contains_any(normalized, ("campaign", "deadline", "reward", "活动", "截止", "奖励"))
    ):
        return _label(message, "campaign_question", "campaign_question_phrase_v1")
    if _contains_any(normalized, ("scam", "rug pull", "fraud", "dead project", "骗局", "跑路")):
        return _label(message, "FUD", "fud_phrase_v1")
    if _contains_any(
        normalized,
        (
            "feature request",
            "please add",
            "wish you would add",
            "can you add",
            "功能建议",
            "请增加",
        ),
    ):
        return _label(message, "feature_request", "feature_request_phrase_v1")
    if _contains_any(
        normalized,
        ("broken", "frustrating", "terrible", "disappointed", "complaint", "糟糕", "失望", "投诉"),
    ):
        return _label(message, "complaint", "complaint_phrase_v1")
    if _contains_any(normalized, ("my feedback", "feedback is", "my opinion", "反馈", "意见")):
        return _label(message, "feedback", "feedback_phrase_v1")
    if _contains_any(
        normalized,
        (
            "done, i registered",
            "i registered",
            "i joined",
            "i staked",
            "已报名",
            "已参加",
        ),
    ):
        return _label(message, "CTA_response", "cta_response_phrase_v1")
    if _contains_any(
        normalized,
        ("off topic", "football match", "weather today", "题外话", "足球比赛"),
    ):
        return _label(message, "off_topic", "off_topic_phrase_v1")
    if _URL_PATTERN.search(message.text) or _contains_any(
        normalized, ("external article", "external source", "外部文章", "新闻链接")
    ):
        return _label(
            message, "external_information_sharing", "external_source_or_url_v1"
        )
    if _contains_any(
        normalized,
        ("plan to use", "want to use", "will try", "intend to use", "准备使用", "打算使用"),
    ):
        return _label(message, "usage_intent", "usage_intent_phrase_v1")
    if _contains_any(
        normalized,
        ("project roadmap", "token utility", "project governance", "项目路线图", "代币用途"),
    ):
        return _label(message, "project_discussion", "project_discussion_phrase_v1")
    return _label(message, "unclassified", "no_seed_rule_match_v1")


def classify_seed_behaviors(
    messages: list[MessageRecord],
) -> dict[str, SeedBehaviorLabel]:
    """Assign one conservative, deterministic primary seed label per message."""

    validated = validate_message_graph(messages)
    duplicate_groups: dict[tuple[str, str, str], list[MessageRecord]] = defaultdict(list)
    for message in validated.messages:
        if message.user_role == "moderator":
            duplicate_groups[
                (message.community_id, message.user_id_hash, normalize_text(message.text))
            ].append(message)

    results: dict[str, SeedBehaviorLabel] = {}
    for message in validated.messages:
        parent_id = validated.parent_by_child.get(message.message_id)
        parent = validated.message_by_id[parent_id] if parent_id is not None else None
        duplicate_group = tuple(
            duplicate_groups[
                (message.community_id, message.user_id_hash, normalize_text(message.text))
            ]
        )
        duplicates = duplicate_group if len(duplicate_group) > 1 else ()
        if message.user_role == "moderator":
            result = _moderator_label(message, parent, duplicates)
        elif message.user_role == "user":
            result = _user_label(message, parent)
        else:
            result = _label(message, "unclassified", "bot_not_classified_v1")
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
        member_vectors = matrix[member_indices].toarray()
        centroid = estimator.cluster_centers_[raw_label]
        distances = np.linalg.norm(member_vectors - centroid, axis=1)
        representative_indices = sorted(
            range(len(members)),
            key=lambda index: (float(distances[index]), members[index].message_id),
        )[:3]
        weighted_terms = sorted(
            enumerate(centroid),
            key=lambda item: (-float(item[1]), terms[item[0]]),
        )
        top_terms = tuple(terms[index] for index, weight in weighted_terms if weight > 0)[:8]
        centroid_norm = float(np.linalg.norm(centroid))
        similarities = (
            member_vectors @ centroid / centroid_norm
            if centroid_norm
            else np.zeros(len(members))
        )
        representative_ids = tuple(
            members[index].message_id for index in representative_indices
        )
        clusters.append(
            BehaviorCluster(
                cluster_id=f"cluster_{stable_index:02d}",
                message_ids=tuple(sorted(message.message_id for message in members)),
                top_terms=top_terms,
                representative_message_ids=representative_ids,
                representative_messages=tuple(
                    validated.message_by_id[message_id].text
                    for message_id in representative_ids
                ),
                language_distribution=_distribution(
                    [message.language for message in members]
                ),
                role_distribution=_distribution([message.user_role for message in members]),
                message_count=len(members),
                proposed_behavior_name=None,
                behavior_description=(
                    "Unsupervised cluster pending human naming; inspect representative "
                    "source text, terms, language, and role distributions."
                ),
                confidence=round(float(np.mean(similarities)), 6),
            )
        )
    return clusters

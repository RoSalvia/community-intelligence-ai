from datetime import UTC, datetime, timedelta

import pytest

from community_intelligence.behavior import classify_seed_behaviors, discover_clusters
from community_intelligence.models import MessageRecord

BASE_TIME = datetime(2026, 9, 1, tzinfo=UTC)


def message(
    message_id: str,
    text: str,
    *,
    seconds: int,
    language: str = "en",
    user_role: str = "user",
    user_id_hash: str = "usr_01",
    reply_to_message_id: str | None = None,
) -> MessageRecord:
    return MessageRecord(
        message_id=message_id,
        community_id="community_a",
        language=language,
        user_id_hash=user_id_hash,
        user_role=user_role,
        timestamp=BASE_TIME + timedelta(seconds=seconds),
        text=text,
        reply_to_message_id=reply_to_message_id,
        campaign_id="campaign_stake",
    )


def test_seed_behavior_labels_keep_exact_evidence_and_rule_metadata() -> None:
    messages = [
        message("m_question", "Where is the staking guide?", seconds=0),
        message(
            "m_answer",
            "The staking guide is in the pinned post.",
            seconds=10,
            user_id_hash="usr_02",
            reply_to_message_id="m_question",
        ),
        message(
            "m_mod",
            "We will clarify the campaign today.",
            seconds=20,
            user_role="moderator",
            user_id_hash="usr_aa",
            reply_to_message_id="m_answer",
        ),
        message("m_negative", "This process is confusing and frustrating.", seconds=30),
    ]

    labels = classify_seed_behaviors(messages)

    assert labels["m_question"].behavior == "question_asking"
    assert labels["m_answer"].behavior == "question_answering"
    assert labels["m_mod"].behavior == "moderator_follow_up"
    assert labels["m_negative"].behavior == "negative_feedback"
    assert labels["m_answer"].evidence_message_ids == ("m_question", "m_answer")
    assert labels["m_answer"].evidence_texts == (
        "Where is the staking guide?",
        "The staking guide is in the pinned post.",
    )
    assert labels["m_answer"].method == "deterministic_seed_rule"
    assert labels["m_answer"].rule_id == "reply_to_question_v1"
    assert labels["m_answer"].confidence == 1.0


def test_seed_behavior_rules_do_not_consult_annotations_or_call_semantic_ai() -> None:
    neutral = message("m1", "Synthetic neutral statement for the test.", seconds=0)

    label = classify_seed_behaviors([neutral])["m1"]

    assert label.behavior == "unclassified"
    assert label.general_semantic_ai == "Not implemented"
    assert label.evidence_message_ids == ("m1",)


def cluster_messages() -> list[MessageRecord]:
    return [
        message("m01", "staking rewards deadline friday", seconds=1),
        message("m02", "stake tokens before friday deadline", seconds=2),
        message("m03", "referral friends invite rewards", seconds=3, language="es"),
        message("m04", "invite eligible friends referral", seconds=4, language="es"),
        message("m05", "产品反馈 功能 上线", seconds=5, language="zh", user_role="moderator"),
        message("m06", "功能 上线 欢迎 反馈", seconds=6, language="zh"),
    ]


def test_unsupervised_clusters_return_stable_reviewable_evidence() -> None:
    clusters = discover_clusters(cluster_messages(), cluster_count=3, random_state=7)

    assert [cluster.cluster_id for cluster in clusters] == [
        "cluster_01",
        "cluster_02",
        "cluster_03",
    ]
    assert all(cluster.representative_message_ids for cluster in clusters)
    assert all(cluster.top_terms for cluster in clusters)
    assert all(cluster.review_status == "pending" for cluster in clusters)
    assert all(cluster.reviewed_name is None for cluster in clusters)
    assert all(cluster.method == "tfidf_kmeans" for cluster in clusters)
    assert all(
        sum(count for _, count in cluster.language_distribution) == len(cluster.message_ids)
        for cluster in clusters
    )
    assert all(
        sum(count for _, count in cluster.role_distribution) == len(cluster.message_ids)
        for cluster in clusters
    )
    assert {
        message_id for cluster in clusters for message_id in cluster.message_ids
    } == {item.message_id for item in cluster_messages()}


def test_cluster_ids_and_members_are_stable_across_input_order() -> None:
    forward = discover_clusters(cluster_messages(), cluster_count=3, random_state=7)
    reverse = discover_clusters(list(reversed(cluster_messages())), cluster_count=3, random_state=7)

    assert forward == reverse


@pytest.mark.parametrize("cluster_count", [0, 7])
def test_cluster_count_must_fit_input(cluster_count: int) -> None:
    with pytest.raises(ValueError, match="cluster_count"):
        discover_clusters(cluster_messages(), cluster_count=cluster_count, random_state=7)

from datetime import UTC, datetime, timedelta

import pytest

from community_intelligence.behavior import (
    MODERATOR_SEED_TAXONOMY,
    USER_SEED_TAXONOMY,
    classify_seed_behaviors,
    discover_clusters,
)
from community_intelligence.models import MessageRecord

BASE_TIME = datetime(2026, 9, 1, tzinfo=UTC)
REQUIRED_MODERATOR_TAXONOMY = {
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
}
REQUIRED_USER_TAXONOMY = {
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
}


def message(
    message_id: str,
    text: str,
    *,
    seconds: int,
    language: str = "en",
    user_role: str = "user",
    user_id_hash: str = "usr_01",
    reply_to_message_id: str | None = None,
    campaign_id: str | None = "campaign_stake",
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
        campaign_id=campaign_id,
    )


def test_seed_taxonomy_exposes_every_required_candidate() -> None:
    assert set(MODERATOR_SEED_TAXONOMY) == REQUIRED_MODERATOR_TAXONOMY
    assert set(USER_SEED_TAXONOMY) == REQUIRED_USER_TAXONOMY


@pytest.mark.parametrize(
    ("behavior", "text", "role", "campaign_id"),
    [
        (
            "campaign_propagation",
            "Official campaign update: the deadline is Friday and reward is 100 tokens.",
            "moderator",
            "campaign_stake",
        ),
        (
            "product_explanation",
            "The product feature works by connecting your wallet.",
            "moderator",
            None,
        ),
        ("CTA", "Join the campaign and register now.", "moderator", "campaign_stake"),
        (
            "user_onboarding",
            "Welcome new members; start with the onboarding guide.",
            "moderator",
            None,
        ),
        ("conflict_handling", "Let's resolve this dispute calmly.", "moderator", None),
        (
            "sentiment_soothing",
            "We understand your concern and are sorry this is frustrating.",
            "moderator",
            None,
        ),
        ("translation", "Translation: the deadline is Friday.", "moderator", None),
        (
            "misinformation_correction",
            "Correction: the reward is 100, not 50.",
            "moderator",
            "campaign_stake",
        ),
        ("normal_chat", "Hope everyone is having a good afternoon.", "moderator", None),
        ("filler", "ok", "moderator", None),
        (
            "spam",
            "BUY NOW!!! http://spam.example/a http://spam.example/b",
            "moderator",
            None,
        ),
        (
            "project_discussion",
            "The project roadmap and token utility look interesting.",
            "user",
            None,
        ),
        ("campaign_question", "What is the campaign deadline?", "user", "campaign_stake"),
        ("product_question", "How does the wallet feature work?", "user", None),
        ("complaint", "This process is broken and frustrating.", "user", None),
        ("feedback", "My feedback is that the guide is useful.", "user", None),
        ("feature_request", "Feature request: please add dark mode.", "user", None),
        ("FUD", "This looks like a scam and a rug pull.", "user", None),
        ("CTA_response", "Done, I registered for the campaign.", "user", "campaign_stake"),
        ("off_topic", "Off topic: the football match was fun.", "user", None),
        (
            "external_information_sharing",
            "This external article explains it: https://example.com/news",
            "user",
            None,
        ),
        ("usage_intent", "I plan to use this feature tomorrow.", "user", None),
    ],
)
def test_seed_taxonomy_has_conservative_lexical_trigger_boundaries(
    behavior: str, text: str, role: str, campaign_id: str | None
) -> None:
    item = message(
        "m1", text, seconds=0, user_role=role, campaign_id=campaign_id
    )

    label = classify_seed_behaviors([item])["m1"]

    assert label.behavior == behavior
    assert label.evidence_message_ids == ("m1",)
    assert label.evidence_texts == (text,)
    assert label.method == "deterministic_seed_rule"
    assert label.rule_id


def test_conversation_initiation_is_a_moderator_root_question() -> None:
    item = message(
        "m1",
        "What should we discuss in today's community session?",
        seconds=0,
        user_role="moderator",
        campaign_id=None,
    )

    assert classify_seed_behaviors([item])["m1"].behavior == "conversation_initiation"


def test_question_answering_and_peer_support_require_reply_evidence() -> None:
    question = message("q1", "Where is the staking guide?", seconds=0)
    moderator_answer = message(
        "a1",
        "The staking guide is in the pinned post.",
        seconds=10,
        user_role="moderator",
        user_id_hash="usr_aa",
        reply_to_message_id="q1",
    )
    peer_answer = message(
        "a2",
        "I also found it in the pinned post.",
        seconds=20,
        user_id_hash="usr_02",
        reply_to_message_id="q1",
    )

    labels = classify_seed_behaviors([question, moderator_answer, peer_answer])

    assert labels["a1"].behavior == "question_answering"
    assert labels["a2"].behavior == "peer_support"
    assert labels["a1"].evidence_message_ids == ("q1", "a1")
    assert labels["a2"].evidence_message_ids == ("q1", "a2")


def test_duplicate_promotion_requires_same_moderator_source_text() -> None:
    first = message(
        "m1",
        "Official promotion: join the synthetic staking campaign.",
        seconds=0,
        user_role="moderator",
        user_id_hash="usr_aa",
    )
    second = message(
        "m2",
        first.text,
        seconds=10,
        user_role="moderator",
        user_id_hash="usr_aa",
    )

    labels = classify_seed_behaviors([first, second])

    assert labels["m1"].behavior == "duplicate_promotion"
    assert labels["m2"].behavior == "duplicate_promotion"
    assert labels["m1"].evidence_message_ids == ("m1", "m2")
    assert labels["m1"].evidence_texts == (first.text, second.text)


def test_unmatched_rule_remains_explicit_and_does_not_claim_semantic_ai() -> None:
    neutral = message(
        "m1", "Synthetic neutral statement for the test.", seconds=0, campaign_id=None
    )

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


def test_unsupervised_clusters_return_complete_review_contract_and_source_text() -> None:
    messages = cluster_messages()
    source_by_id = {message.message_id: message.text for message in messages}

    clusters = discover_clusters(messages, cluster_count=3, random_state=7)

    assert [cluster.cluster_id for cluster in clusters] == [
        "cluster_01",
        "cluster_02",
        "cluster_03",
    ]
    for cluster in clusters:
        assert cluster.top_terms
        assert cluster.representative_message_ids
        assert cluster.representative_messages == tuple(
            source_by_id[message_id]
            for message_id in cluster.representative_message_ids
        )
        assert cluster.message_count == len(cluster.message_ids)
        assert cluster.proposed_behavior_name is None
        assert "pending human naming" in cluster.behavior_description
        assert 0 <= cluster.confidence <= 1
        assert cluster.review_status == "pending"
        assert cluster.method == "tfidf_kmeans"
        assert sum(count for _, count in cluster.language_distribution) == cluster.message_count
        assert sum(count for _, count in cluster.role_distribution) == cluster.message_count
    assert {
        message_id for cluster in clusters for message_id in cluster.message_ids
    } == set(source_by_id)


def test_cluster_ids_members_and_representative_text_are_stable_across_input_order() -> None:
    forward = discover_clusters(cluster_messages(), cluster_count=3, random_state=7)
    reverse = discover_clusters(list(reversed(cluster_messages())), cluster_count=3, random_state=7)

    assert forward == reverse


@pytest.mark.parametrize("cluster_count", [0, 7])
def test_cluster_count_must_fit_input(cluster_count: int) -> None:
    with pytest.raises(ValueError, match="cluster_count"):
        discover_clusters(cluster_messages(), cluster_count=cluster_count, random_state=7)

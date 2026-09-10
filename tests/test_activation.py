from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from community_intelligence.activation import analyze_activation
from community_intelligence.models import MessageRecord

BASE_TIME = datetime(2026, 9, 1, tzinfo=UTC)


def message(
    message_id: str,
    text: str,
    *,
    seconds: int,
    user_id_hash: str,
    user_role: str,
    reply_to_message_id: str | None = None,
    community_id: str = "community_a",
    campaign_id: str | None = None,
    language: str = "en",
) -> MessageRecord:
    return MessageRecord(
        message_id=message_id,
        community_id=community_id,
        language=language,
        user_id_hash=user_id_hash,
        user_role=user_role,
        timestamp=BASE_TIME + timedelta(seconds=seconds),
        text=text,
        reply_to_message_id=reply_to_message_id,
        campaign_id=campaign_id,
    )


def test_activation_separates_moderator_activity_from_two_engaged_users() -> None:
    messages = [
        message(
            "m1",
            "Synthetic campaign announcement",
            seconds=0,
            user_id_hash="usr_aa",
            user_role="moderator",
        ),
        message(
            "m2",
            "Where is the campaign guide?",
            seconds=10,
            user_id_hash="usr_01",
            user_role="user",
            reply_to_message_id="m1",
        ),
        message(
            "m3",
            "It is in the pinned post.",
            seconds=20,
            user_id_hash="usr_02",
            user_role="user",
            reply_to_message_id="m2",
        ),
    ]

    result = analyze_activation(messages)

    assert result.unique_engaged_users == 2
    assert result.moderator_messages == 1
    assert result.user_messages == 2
    assert result.user_to_user_interaction_ratio == pytest.approx(1 / 2)
    assert result.peer_support_ratio == 1.0
    assert result.meaningful_interaction_ratio == 1.0
    assert result.response_latency_seconds is None
    assert result.response_latency is None


def test_self_replies_are_reported_as_gaming_not_user_to_user_interaction() -> None:
    messages = [
        message(
            "m1",
            "Where is the campaign guide?",
            seconds=0,
            user_id_hash="usr_01",
            user_role="user",
        ),
        message(
            "m2",
            "I will answer my own post.",
            seconds=10,
            user_id_hash="usr_01",
            user_role="user",
            reply_to_message_id="m1",
        ),
        message(
            "m3",
            "The guide is pinned.",
            seconds=20,
            user_id_hash="usr_02",
            user_role="user",
            reply_to_message_id="m1",
        ),
    ]

    result = analyze_activation(messages)

    assert result.self_reply_count == 1
    assert result.user_to_user_interaction_ratio == pytest.approx(1 / 3)
    assert result.peer_support_ratio == 1.0
    interaction_ids = {
        tuple(item.supporting_message_ids)
        for item in result.evidence
        if item.metric_id == "user_to_user_interaction_ratio"
    }
    assert interaction_ids == {("m1", "m3")}


def test_moderator_heavy_activity_is_distinct_from_healthy_user_activation() -> None:
    moderator_heavy = [
        message(
            f"m{index}",
            "ok",
            seconds=index,
            user_id_hash="usr_aa",
            user_role="moderator",
        )
        for index in range(1, 5)
    ]
    moderator_heavy.append(
        message(
            "m5",
            "ok",
            seconds=5,
            user_id_hash="usr_01",
            user_role="user",
        )
    )
    healthy = [
        message(
            "h1",
            "Campaign announcement",
            seconds=0,
            user_id_hash="usr_aa",
            user_role="moderator",
        ),
        message(
            "h2",
            "I read the guide and plan to join.",
            seconds=10,
            user_id_hash="usr_01",
            user_role="user",
            reply_to_message_id="h1",
        ),
        message(
            "h3",
            "I can help with the setup steps.",
            seconds=20,
            user_id_hash="usr_02",
            user_role="user",
            reply_to_message_id="h2",
        ),
    ]

    heavy_result = analyze_activation(moderator_heavy)
    healthy_result = analyze_activation(healthy)

    assert heavy_result.moderator_messages > healthy_result.moderator_messages
    assert heavy_result.unique_engaged_users < healthy_result.unique_engaged_users
    assert heavy_result.meaningful_interaction_ratio == 0.0
    assert healthy_result.meaningful_interaction_ratio == 1.0


def test_response_latency_is_mean_direct_moderator_reply_latency() -> None:
    messages = [
        message(
            "m1",
            "Can you clarify the deadline?",
            seconds=0,
            user_id_hash="usr_01",
            user_role="user",
        ),
        message(
            "m2",
            "The deadline is Friday.",
            seconds=20,
            user_id_hash="usr_aa",
            user_role="moderator",
            reply_to_message_id="m1",
        ),
        message(
            "m5",
            "A second moderator reply must not add an observation.",
            seconds=25,
            user_id_hash="usr_ab",
            user_role="moderator",
            reply_to_message_id="m1",
        ),
        message(
            "m3",
            "Where is the form?",
            seconds=30,
            user_id_hash="usr_02",
            user_role="user",
        ),
        message(
            "m4",
            "The form is pinned.",
            seconds=70,
            user_id_hash="usr_aa",
            user_role="moderator",
            reply_to_message_id="m3",
        ),
    ]

    result = analyze_activation(messages)

    assert result.response_latency_seconds == 30.0
    assert result.response_latency == 30.0
    latency_metadata = result.metadata["response_latency_seconds"]
    assert latency_metadata.numerator == "total first-response latency seconds"
    assert latency_metadata.numerator_value == 60.0
    assert latency_metadata.observation_count == 2
    assert latency_metadata.denominator_count == 2
    assert latency_metadata.aggregation_method == "mean"
    assert latency_metadata.unit == "seconds"
    latency_pairs = {
        item.supporting_message_ids
        for item in result.evidence
        if item.metric_id == "response_latency_seconds"
    }
    assert latency_pairs == {("m1", "m2"), ("m3", "m4")}


def test_ratio_metadata_documents_all_zero_denominators() -> None:
    messages = [
        message(
            "m1",
            "Moderator only",
            seconds=0,
            user_id_hash="usr_aa",
            user_role="moderator",
        )
    ]

    result = analyze_activation(messages)

    assert result.unique_engaged_users == 0
    assert result.user_messages == 0
    assert result.user_to_user_interaction_ratio == 0.0
    assert result.peer_support_ratio == 0.0
    assert result.meaningful_interaction_ratio == 0.0
    assert result.response_latency_seconds is None
    assert result.metadata["user_to_user_interaction_ratio"].denominator == (
        "all real-user messages"
    )
    assert result.metadata["user_to_user_interaction_ratio"].denominator_count == 0
    assert result.metadata["peer_support_ratio"].denominator == (
        "direct real-user-to-different-real-user reply edges"
    )
    assert result.metadata["peer_support_ratio"].denominator_count == 0
    assert result.metadata["meaningful_interaction_ratio"].denominator_count == 0


def test_bots_are_excluded_from_users_interactions_and_latency() -> None:
    messages = [
        message(
            "m1",
            "Where is the guide?",
            seconds=0,
            user_id_hash="usr_01",
            user_role="user",
        ),
        message(
            "m2",
            "Automated answer",
            seconds=1,
            user_id_hash="usr_bb",
            user_role="bot",
            reply_to_message_id="m1",
        ),
    ]

    result = analyze_activation(messages)

    assert result.unique_engaged_users == 1
    assert result.moderator_messages == 0
    assert result.user_messages == 1
    assert result.user_to_user_interaction_ratio == 0.0
    assert result.peer_support_ratio == 0.0
    assert result.response_latency_seconds is None
    assert all("m2" not in item.supporting_message_ids for item in result.evidence)


def test_empty_input_returns_zero_activation_with_documented_denominators() -> None:
    result = analyze_activation([])

    assert result.unique_engaged_users == 0
    assert result.moderator_messages == 0
    assert result.user_messages == 0
    assert result.user_to_user_interaction_ratio == 0.0
    assert result.peer_support_ratio == 0.0
    assert result.meaningful_interaction_ratio == 0.0
    assert result.response_latency_seconds is None
    assert all(item.denominator_count == 0 for item in result.metadata.values())


@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("en-us", "thanks"),
        ("es-mx", "gracias"),
        ("tr-tr", "teşekkürler"),
        ("ar-eg", "شكرا"),
        ("zh-hans", "谢谢"),
        ("zh", "收到"),
    ],
)
def test_activation_applies_language_equivalent_filler_rules(language: str, text: str) -> None:
    result = analyze_activation(
        [
            message(
                "m1",
                text,
                seconds=0,
                user_id_hash="usr_01",
                user_role="user",
                language=language,
            )
        ]
    )

    assert result.meaningful_interaction_ratio == 0.0
    assert result.meaningful_interaction_rules[0].primary_language == language.split("-", 1)[0]
    assert result.meaningful_interaction_rules[0].comparison_limit == (
        "language-specific deterministic baseline; no cross-language quality claim"
    )


def test_activation_records_mixed_community_scope_and_observed_utc_bounds() -> None:
    messages = [
        message(
            "m1",
            "I can help with registration.",
            seconds=0,
            user_id_hash="usr_01",
            user_role="user",
            community_id="community_b",
        ),
        message(
            "m2",
            "Puedo ayudar con el registro.",
            seconds=10,
            user_id_hash="usr_02",
            user_role="user",
            community_id="community_a",
            language="es",
        ),
    ]

    result = analyze_activation(messages)

    assert result.included_community_ids == ("community_a", "community_b")
    assert result.observed_start == BASE_TIME
    assert result.observed_end == BASE_TIME + timedelta(seconds=10)
    assert result.observed_start.utcoffset() == timedelta(0)
    assert result.observed_end.utcoffset() == timedelta(0)
    assert not hasattr(result, "window_start")
    assert not hasattr(result, "window_end")
    assert result.analysis_rule_version == "2.0.0"


def test_activation_evidence_and_metadata_are_deeply_immutable() -> None:
    result = analyze_activation(
        [
            message(
                "m1",
                "I can help with registration.",
                seconds=0,
                user_id_hash="usr_01",
                user_role="user",
            )
        ]
    )

    assert isinstance(result.evidence, tuple)
    assert isinstance(result.evidence[0].supporting_message_ids, tuple)
    assert isinstance(result.meaningful_interaction_rules, tuple)
    with pytest.raises(TypeError):
        result.metadata["changed"] = result.metadata["meaningful_interaction_ratio"]
    with pytest.raises(FrozenInstanceError):
        result.evidence[0].metric_id = "changed"

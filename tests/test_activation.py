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
) -> MessageRecord:
    return MessageRecord(
        message_id=message_id,
        community_id="community_a",
        language="en",
        user_id_hash=user_id_hash,
        user_role=user_role,
        timestamp=BASE_TIME + timedelta(seconds=seconds),
        text=text,
        reply_to_message_id=reply_to_message_id,
        campaign_id=None,
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
    assert result.metadata["response_latency_seconds"].numerator_count == 2
    assert result.metadata["response_latency_seconds"].denominator_count == 2
    assert result.metadata["response_latency_seconds"].unit == "seconds"


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
        "direct real-user-to-real-user reply edges"
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

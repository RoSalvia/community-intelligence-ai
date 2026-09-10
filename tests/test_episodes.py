from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from community_intelligence.episodes import build_episodes
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
) -> MessageRecord:
    return MessageRecord(
        message_id=message_id,
        community_id=community_id,
        language="en",
        user_id_hash=user_id_hash,
        user_role=user_role,
        timestamp=BASE_TIME + timedelta(seconds=seconds),
        text=text,
        reply_to_message_id=reply_to_message_id,
        campaign_id=None,
    )


def test_silence_episode_has_zero_response_metrics() -> None:
    announcement = message(
        "m1",
        "Synthetic campaign announcement.",
        seconds=0,
        user_id_hash="usr_aa",
        user_role="moderator",
    )

    episode = build_episodes([announcement])[0]

    assert episode.root_message_id == "m1"
    assert episode.message_ids == ("m1",)
    assert episode.unique_participants == 1
    assert episode.moderator_messages == 1
    assert episode.user_messages == 0
    assert episode.user_to_user_replies == 0
    assert episode.moderator_response_count == 0
    assert episode.first_response_latency_seconds is None
    assert episode.conversation_depth == 1
    assert episode.branching_factor == 0.0
    assert episode.question_count == 0
    assert episode.resolved_question_count == 0
    assert episode.unanswered_question_count == 0
    assert episode.duration_seconds == 0.0


def test_answered_chain_builds_complete_reply_graph_metrics() -> None:
    messages = [
        message(
            "m1",
            "Campaign announcement",
            seconds=0,
            user_id_hash="usr_aa",
            user_role="moderator",
        ),
        message(
            "m2",
            "Can you confirm the deadline?",
            seconds=10,
            user_id_hash="usr_01",
            user_role="user",
            reply_to_message_id="m1",
        ),
        message(
            "m3",
            "The deadline is Friday.",
            seconds=30,
            user_id_hash="usr_aa",
            user_role="moderator",
            reply_to_message_id="m2",
        ),
        message(
            "m4",
            "Thanks, that is clear.",
            seconds=50,
            user_id_hash="usr_02",
            user_role="user",
            reply_to_message_id="m3",
        ),
    ]

    episode = build_episodes(messages)[0]

    assert episode.unique_participants == 3
    assert episode.moderator_messages == 2
    assert episode.user_messages == 2
    assert episode.user_to_user_replies == 0
    assert episode.moderator_response_count == 1
    assert episode.first_response_latency_seconds == 10.0
    assert episode.conversation_depth == 4
    assert episode.branching_factor == 1.0
    assert episode.question_count == 1
    assert episode.candidate_answered_question_count == 1
    assert episode.resolved_question_count == 1
    assert episode.unanswered_question_count == 0
    assert episode.duration_seconds == 50.0
    assert episode.question_message_ids == ("m2",)
    assert episode.resolved_question_message_ids == ("m2",)
    assert len(episode.candidate_answer_evidence) == 1
    candidate = episode.candidate_answer_evidence[0]
    assert candidate.rule_id == "candidate_non_question_reply_v1"
    assert candidate.rule_version == "1.0.0"
    assert (candidate.question_id, candidate.candidate_answer_id) == ("m2", "m3")
    assert episode.resolution_interpretation == (
        "resolved_question_count is a compatibility alias for structural candidate answers; "
        "no semantic resolution claim"
    )
    assert episode.question_rule_id == "punctuation_or_phrase_question.v1"
    assert episode.question_rule_version == "1.0.0"
    assert "punctuation" in episode.question_detection_method
    assert episode.interpretation_limit == "descriptive reply-graph metrics; no causal claim"


def test_peer_reply_counts_as_user_interaction_and_resolves_question() -> None:
    messages = [
        message(
            "m1",
            "Where is the synthetic guide?",
            seconds=0,
            user_id_hash="usr_01",
            user_role="user",
        ),
        message(
            "m2",
            "It is in the pinned post.",
            seconds=20,
            user_id_hash="usr_02",
            user_role="user",
            reply_to_message_id="m1",
        ),
    ]

    episode = build_episodes(messages)[0]

    assert episode.unique_participants == 2
    assert episode.user_to_user_replies == 1
    assert episode.moderator_response_count == 0
    assert episode.resolved_question_count == 1
    assert episode.unanswered_question_count == 0


def test_self_reply_is_reported_without_inflating_peer_interaction() -> None:
    messages = [
        message(
            "m1",
            "Where is the synthetic guide?",
            seconds=0,
            user_id_hash="usr_01",
            user_role="user",
        ),
        message(
            "m2",
            "I am replying to myself.",
            seconds=20,
            user_id_hash="usr_01",
            user_role="user",
            reply_to_message_id="m1",
        ),
    ]

    episode = build_episodes(messages)[0]

    assert episode.self_reply_count == 1
    assert episode.user_to_user_replies == 0
    assert episode.resolved_question_count == 0
    assert episode.unanswered_question_count == 1


def test_question_without_a_reply_remains_unanswered() -> None:
    question = message(
        "m1",
        "How do I join?",
        seconds=0,
        user_id_hash="usr_01",
        user_role="user",
    )

    episode = build_episodes([question])[0]

    assert episode.question_count == 1
    assert episode.resolved_question_count == 0
    assert episode.unanswered_question_count == 1
    assert episode.unanswered_question_message_ids == ("m1",)


def test_clarification_chain_retains_candidate_evidence_for_each_question() -> None:
    messages = [
        message(
            "m1",
            "Where is the form?",
            seconds=0,
            user_id_hash="usr_01",
            user_role="user",
        ),
        message(
            "m2",
            "Which form do you mean?",
            seconds=10,
            user_id_hash="usr_02",
            user_role="user",
            reply_to_message_id="m1",
        ),
        message(
            "m3",
            "The registration form is pinned.",
            seconds=20,
            user_id_hash="usr_03",
            user_role="user",
            reply_to_message_id="m2",
        ),
    ]

    episode = build_episodes(messages)[0]

    assert episode.question_count == 2
    assert episode.candidate_answered_question_count == 2
    assert episode.resolved_question_count == 2
    assert episode.unanswered_question_count == 0
    assert tuple(
        (item.question_id, item.candidate_answer_id) for item in episode.candidate_answer_evidence
    ) == (("m1", "m3"), ("m2", "m3"))


def test_same_asker_clarification_leads_to_final_moderator_candidate_answer() -> None:
    messages = [
        message(
            "m1",
            "Where is the registration form?",
            seconds=0,
            user_id_hash="usr_01",
            user_role="user",
        ),
        message(
            "m2",
            "Which form do you mean?",
            seconds=10,
            user_id_hash="usr_aa",
            user_role="moderator",
            reply_to_message_id="m1",
        ),
        message(
            "m3",
            "I mean the registration form.",
            seconds=20,
            user_id_hash="usr_01",
            user_role="user",
            reply_to_message_id="m2",
        ),
        message(
            "m4",
            "The registration form is pinned.",
            seconds=30,
            user_id_hash="usr_aa",
            user_role="moderator",
            reply_to_message_id="m3",
        ),
    ]

    episode = build_episodes(messages)[0]

    original_question_evidence = tuple(
        (item.question_id, item.candidate_answer_id)
        for item in episode.candidate_answer_evidence
        if item.question_id == "m1"
    )
    assert original_question_evidence == (("m1", "m4"),)
    assert "m1" in episode.resolved_question_message_ids


def test_episode_evidence_collections_are_deeply_immutable() -> None:
    messages = [
        message(
            "m1",
            "Where is the form?",
            seconds=0,
            user_id_hash="usr_01",
            user_role="user",
        ),
        message(
            "m2",
            "The form is pinned.",
            seconds=10,
            user_id_hash="usr_02",
            user_role="user",
            reply_to_message_id="m1",
        ),
    ]

    episode = build_episodes(messages)[0]

    assert isinstance(episode.message_ids, tuple)
    assert isinstance(episode.question_message_ids, tuple)
    assert isinstance(episode.candidate_answer_evidence, tuple)
    with pytest.raises(TypeError):
        episode.message_ids[0] = "changed"
    with pytest.raises(FrozenInstanceError):
        episode.candidate_answer_evidence[0].question_id = "changed"


def test_branching_factor_is_mean_children_per_non_leaf_message() -> None:
    messages = [
        message(
            "m1",
            "Campaign announcement",
            seconds=0,
            user_id_hash="usr_aa",
            user_role="moderator",
        ),
        message(
            "m2",
            "Is Friday the deadline?",
            seconds=10,
            user_id_hash="usr_01",
            user_role="user",
            reply_to_message_id="m1",
        ),
        message(
            "m3",
            "I plan to participate.",
            seconds=15,
            user_id_hash="usr_02",
            user_role="user",
            reply_to_message_id="m1",
        ),
        message(
            "m4",
            "Yes, Friday.",
            seconds=20,
            user_id_hash="usr_aa",
            user_role="moderator",
            reply_to_message_id="m2",
        ),
    ]

    episode = build_episodes(messages)[0]

    assert episode.conversation_depth == 3
    assert episode.branching_factor == pytest.approx(3 / 2)


def test_episode_and_message_order_is_stable_for_shuffled_input() -> None:
    first = message(
        "m2",
        "Second root",
        seconds=10,
        user_id_hash="usr_02",
        user_role="user",
        community_id="community_b",
    )
    earliest = message(
        "m1",
        "First root",
        seconds=0,
        user_id_hash="usr_01",
        user_role="user",
    )
    child = message(
        "m3",
        "Reply",
        seconds=20,
        user_id_hash="usr_03",
        user_role="user",
        reply_to_message_id="m1",
    )

    forward = build_episodes([first, child, earliest])
    reverse = build_episodes([earliest, child, first])

    assert forward == reverse
    assert [episode.root_message_id for episode in forward] == ["m1", "m2"]
    assert forward[0].message_ids == ("m1", "m3")


def test_empty_input_returns_no_episodes() -> None:
    assert build_episodes([]) == []

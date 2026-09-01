from datetime import UTC, datetime, timedelta

import pytest

from community_intelligence.activation import analyze_activation
from community_intelligence.episodes import build_episodes
from community_intelligence.hygiene import analyze_hygiene
from community_intelligence.message_rules import (
    classify_meaningful_text,
    validate_message_graph,
)
from community_intelligence.models import MessageRecord
from community_intelligence.synthetic import generate_dataset

BASE_TIME = datetime(2026, 9, 1, tzinfo=UTC)


def message(
    message_id: str,
    *,
    seconds: int,
    reply_to_message_id: str | None = None,
    community_id: str = "community_a",
    campaign_id: str | None = "campaign_a",
) -> MessageRecord:
    return MessageRecord(
        message_id=message_id,
        community_id=community_id,
        language="en",
        user_id_hash=f"usr_{int(seconds + 100):x}",
        user_role="user",
        timestamp=BASE_TIME + timedelta(seconds=seconds),
        text=f"Synthetic message {message_id}",
        reply_to_message_id=reply_to_message_id,
        campaign_id=campaign_id,
    )


def invalid_cases() -> list[tuple[list[MessageRecord], str]]:
    duplicate = [message("m1", seconds=0), message("m1", seconds=1)]
    missing_parent = [message("m1", seconds=1, reply_to_message_id="missing")]
    cross_community = [
        message("m1", seconds=0),
        message(
            "m2",
            seconds=1,
            reply_to_message_id="m1",
            community_id="community_b",
        ),
    ]
    cross_campaign = [
        message("m1", seconds=0),
        message(
            "m2",
            seconds=1,
            reply_to_message_id="m1",
            campaign_id="campaign_b",
        ),
    ]
    reversed_timestamp = [
        message("m1", seconds=5),
        message("m2", seconds=1, reply_to_message_id="m1"),
    ]
    cycle = [
        message("m1", seconds=0, reply_to_message_id="m2"),
        message("m2", seconds=1, reply_to_message_id="m1"),
    ]
    return [
        (duplicate, "message_id values must be unique"),
        (missing_parent, "reply parent must exist"),
        (cross_community, "replies must remain within a community"),
        (cross_campaign, "replies must remain within a campaign"),
        (reversed_timestamp, "reply timestamp must not be before parent timestamp"),
        (cycle, "reply graph must be acyclic"),
    ]


@pytest.mark.parametrize(("messages", "match"), invalid_cases())
def test_shared_message_graph_validation_rejects_adversarial_inputs(
    messages: list[MessageRecord], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        validate_message_graph(messages)


def test_shared_validation_allows_explicit_mixed_community_scope() -> None:
    messages = [
        message("m2", seconds=2, community_id="community_b"),
        message("m1", seconds=1, community_id="community_a"),
    ]

    validated = validate_message_graph(messages)

    assert tuple(item.message_id for item in validated.messages) == ("m1", "m2")
    assert validated.community_ids == ("community_a", "community_b")
    with pytest.raises(TypeError):
        validated.message_by_id["m3"] = messages[0]


@pytest.mark.parametrize(("messages", "match"), invalid_cases())
def test_public_analyzers_apply_the_shared_strict_validation(
    messages: list[MessageRecord], match: str
) -> None:
    for analyzer in (build_episodes, analyze_activation):
        with pytest.raises(ValueError, match=match):
            analyzer(messages)


@pytest.mark.parametrize(
    ("language", "text", "primary_language"),
    [
        ("en-us", "thanks", "en"),
        ("es-mx", "gracias", "es"),
        ("tr-tr", "teşekkürler", "tr"),
        ("ar-eg", "شكرا", "ar"),
        ("zh-hans", "谢谢", "zh"),
        ("zh", "收到", "zh"),
    ],
)
def test_language_equivalent_acknowledgements_are_consistently_filler(
    language: str, text: str, primary_language: str
) -> None:
    classification = classify_meaningful_text(text, language)

    assert classification.is_filler is True
    assert classification.is_meaningful is False
    assert classification.rule.primary_language == primary_language
    assert classification.rule.rule_id == "language_filler_or_min_length_v1"
    assert classification.rule.rule_version == "1.0.0"
    assert classification.rule.comparison_limit == (
        "language-specific deterministic baseline; no cross-language quality claim"
    )


@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("en", "I can help with registration."),
        ("es", "Puedo ayudar con el registro."),
        ("tr", "Kayıt konusunda yardımcı olabilirim."),
        ("ar", "يمكنني المساعدة في التسجيل."),
        ("zh", "我可以帮助完成注册。"),
    ],
)
def test_language_rules_retain_long_non_filler_interactions(
    language: str, text: str
) -> None:
    classification = classify_meaningful_text(text, language)

    assert classification.is_filler is False
    assert classification.is_meaningful is True
    assert classification.normalized_character_count >= classification.rule.minimum_characters


def test_generated_1200_message_analyzer_integration_preserves_evidence_and_source() -> None:
    dataset = generate_dataset(seed=20260901, message_count=1200)
    before = tuple(message.model_dump_json() for message in dataset.messages)
    valid_ids = {message.message_id for message in dataset.messages}

    hygiene = analyze_hygiene(dataset.messages)
    episodes = build_episodes(dataset.messages)
    activation = analyze_activation(dataset.messages)

    partitioned_ids = tuple(
        message_id for episode in episodes for message_id in episode.message_ids
    )
    assert len(partitioned_ids) == 1200
    assert len(set(partitioned_ids)) == 1200
    assert set(partitioned_ids) == valid_ids
    assert all(
        set(item.supporting_message_ids) <= valid_ids for item in hygiene.evidence
    )
    assert all(
        {item.question_id, item.candidate_answer_id} <= valid_ids
        for episode in episodes
        for item in episode.candidate_answer_evidence
    )
    assert all(
        set(item.supporting_message_ids) <= valid_ids for item in activation.evidence
    )
    assert activation.included_community_ids == tuple(dataset.manifest.community_ids)
    assert tuple(message.model_dump_json() for message in dataset.messages) == before

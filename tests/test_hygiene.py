from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from community_intelligence.hygiene import analyze_hygiene, detect_bursts, normalize_text
from community_intelligence.models import MessageRecord

BASE_TIME = datetime(2026, 9, 1, tzinfo=UTC)


def message(
    message_id: str,
    text: str,
    *,
    seconds: int = 0,
    community_id: str = "community_a",
    user_id_hash: str = "usr_01",
) -> MessageRecord:
    return MessageRecord(
        message_id=message_id,
        community_id=community_id,
        language="en",
        user_id_hash=user_id_hash,
        user_role="user",
        timestamp=BASE_TIME + timedelta(seconds=seconds),
        text=text,
        reply_to_message_id=None,
        campaign_id=None,
    )


def evidence_for(result: object, rule_id: str) -> list[object]:
    return [item for item in result.evidence if item.rule_id == rule_id]


def test_normalization_is_nfkc_casefolded_and_whitespace_collapsed_without_mutation() -> None:
    source = message("m1", "  ＨＥＬＬＯ\t Straße  ")
    original_text = source.text

    result = analyze_hygiene([source])

    assert normalize_text(source.text) == "hello strasse"
    assert result.normalized_text_by_message_id == {"m1": "hello strasse"}
    assert source.text == original_text


def test_duplicate_and_filler_evidence_retains_rules_metrics_and_denominators() -> None:
    messages = [
        message("m1", "Synthetic update"),
        message("m2", "ＳＹＮＴＨＥＴＩＣ   UPDATE"),
        message("m3", "synthetic update"),
        message("m4", "ok"),
    ]

    result = analyze_hygiene(messages)

    assert result.duplicate_ratio == pytest.approx(2 / 4)
    assert result.filler_ratio == pytest.approx(1 / 4)
    assert result.metadata["duplicate_ratio"].numerator_count == 2
    assert result.metadata["duplicate_ratio"].denominator_count == 4
    assert result.metadata["duplicate_ratio"].denominator == "all input messages"
    assert result.metadata["filler_ratio"].numerator_count == 1
    assert result.metadata["filler_ratio"].denominator_count == 4

    duplicate = evidence_for(result, "exact_duplicate.v1")
    assert len(duplicate) == 1
    assert duplicate[0].rule_version == "1.0.0"
    assert duplicate[0].threshold == 2
    assert duplicate[0].raw_metric == 3
    assert duplicate[0].window_seconds is None
    assert duplicate[0].supporting_message_ids == ("m1", "m2", "m3")

    filler = evidence_for(result, "filler_or_short.v1")
    assert len(filler) == 1
    assert filler[0].threshold == 3
    assert filler[0].raw_metric == 2
    assert filler[0].supporting_message_ids == ("m4",)


def test_duplicate_message_ids_fail_before_evidence_construction() -> None:
    messages = [
        message("same_id", "Repeated content", seconds=0),
        message("same_id", "Repeated content", seconds=1),
    ]

    with pytest.raises(ValueError, match="message_id values must be unique"):
        analyze_hygiene(messages)


def test_repeated_content_is_scoped_to_actor_and_community() -> None:
    messages = [
        message("m1", "same useful sentence", user_id_hash="usr_01"),
        message("m2", "same useful sentence", user_id_hash="usr_01", seconds=1),
        message("m3", "same useful sentence", user_id_hash="usr_01", seconds=2),
        message("m4", "same useful sentence", user_id_hash="usr_02", seconds=3),
        message(
            "m5",
            "same useful sentence",
            user_id_hash="usr_01",
            community_id="community_b",
            seconds=4,
        ),
    ]

    result = analyze_hygiene(messages, repeated_content_minimum=3)

    assert result.repetitive_content_ratio == pytest.approx(3 / 5)
    repeated = evidence_for(result, "repeated_content.v1")
    assert len(repeated) == 1
    assert repeated[0].threshold == 3
    assert repeated[0].raw_metric == 3
    assert repeated[0].supporting_message_ids == ("m1", "m2", "m3")


def test_burst_detection_uses_utc_rolling_window_and_stable_order() -> None:
    messages = [
        message("m3", "third", seconds=55),
        message("m1", "first", seconds=0),
        message("m4", "outside", seconds=121),
        message("m2", "second", seconds=30),
    ]

    events = detect_bursts(messages, minimum_messages=3, window_seconds=60)

    assert len(events) == 1
    event = events[0]
    assert event.community_id == "community_a"
    assert event.user_id_hash == "usr_01"
    assert event.message_ids == ("m1", "m2", "m3")
    assert event.started_at == BASE_TIME
    assert event.ended_at == BASE_TIME + timedelta(seconds=55)
    assert event.rule_id == "posting_burst.v1"
    assert event.rule_version == "1.0.0"
    assert event.threshold == 3
    assert event.raw_metric == 3
    assert event.window_seconds == 60


def test_bursts_do_not_merge_users_or_communities() -> None:
    messages = [
        message("a1", "one", seconds=0, user_id_hash="usr_01"),
        message("a2", "two", seconds=10, user_id_hash="usr_01"),
        message("b1", "one", seconds=20, user_id_hash="usr_02"),
        message("c1", "one", seconds=30, community_id="community_b"),
    ]

    assert detect_bursts(messages, minimum_messages=3, window_seconds=60) == ()


def test_overlapping_bursts_each_remain_within_the_reported_window() -> None:
    messages = [
        message("m1", "one", seconds=0),
        message("m2", "two", seconds=30),
        message("m3", "three", seconds=55),
        message("m4", "four", seconds=70),
    ]

    events = detect_bursts(messages, minimum_messages=3, window_seconds=60)

    assert [event.message_ids for event in events] == [
        ("m1", "m2", "m3"),
        ("m2", "m3", "m4"),
    ]
    assert all(
        (event.ended_at - event.started_at).total_seconds() <= event.window_seconds
        for event in events
    )
    assert all(event.raw_metric == len(event.message_ids) for event in events)


def test_empty_input_has_zero_ratios_explicit_denominators_and_no_evidence() -> None:
    result = analyze_hygiene([])

    assert result.duplicate_ratio == 0.0
    assert result.filler_ratio == 0.0
    assert result.repetitive_content_ratio == 0.0
    assert result.burst_events == ()
    assert result.evidence == ()
    assert all(definition.denominator_count == 0 for definition in result.metadata.values())


def test_hygiene_evidence_and_result_mappings_are_deeply_immutable() -> None:
    result = analyze_hygiene(
        [
            message("m1", "same", seconds=0),
            message("m2", "same", seconds=10),
            message("m3", "same", seconds=20),
        ]
    )

    assert isinstance(result.evidence, tuple)
    assert isinstance(result.evidence[0].supporting_message_ids, tuple)
    assert isinstance(result.burst_events, tuple)
    assert isinstance(result.burst_events[0].message_ids, tuple)
    with pytest.raises(TypeError):
        result.metadata["changed"] = result.metadata["duplicate_ratio"]
    with pytest.raises(TypeError):
        result.normalized_text_by_message_id["m1"] = "changed"
    with pytest.raises(FrozenInstanceError):
        result.evidence[0].rule_id = "changed"


@pytest.mark.parametrize(
    ("kwargs", "message_match"),
    [
        ({"short_message_max_chars": -1}, "short_message_max_chars"),
        ({"repeated_content_minimum": 1}, "repeated_content_minimum"),
        ({"burst_minimum_messages": 1}, "burst_minimum_messages"),
        ({"burst_window_seconds": 0}, "burst_window_seconds"),
    ],
)
def test_hygiene_rejects_invalid_thresholds(
    kwargs: dict[str, int], message_match: str
) -> None:
    with pytest.raises(ValueError, match=message_match):
        analyze_hygiene([], **kwargs)


@pytest.mark.parametrize(
    ("minimum_messages", "window_seconds", "message_match"),
    [(1, 60, "minimum_messages"), (3, 0, "window_seconds")],
)
def test_burst_detection_rejects_invalid_thresholds(
    minimum_messages: int, window_seconds: int, message_match: str
) -> None:
    with pytest.raises(ValueError, match=message_match):
        detect_bursts(
            [], minimum_messages=minimum_messages, window_seconds=window_seconds
        )

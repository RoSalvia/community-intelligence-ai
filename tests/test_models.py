from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from community_intelligence.models import MessageRecord, SyntheticDataset
from community_intelligence.synthetic import generate_dataset


def valid_message(**overrides: object) -> dict[str, object]:
    message: dict[str, object] = {
        "message_id": "msg_001",
        "community_id": "community_a",
        "language": "en",
        "user_id_hash": "usr_0a12ff",
        "user_role": "user",
        "timestamp": datetime(2026, 9, 1, tzinfo=UTC),
        "text": "Synthetic hello",
        "reply_to_message_id": None,
        "campaign_id": None,
    }
    message.update(overrides)
    return message


@pytest.mark.parametrize(
    "raw_identifier",
    ["Alice", "12345", "user_abc123", "usr_A12", "usr_"],
)
def test_message_rejects_raw_user_identifier(raw_identifier: str) -> None:
    with pytest.raises(ValidationError):
        MessageRecord(**valid_message(user_id_hash=raw_identifier))


@pytest.mark.parametrize("role", ["admin", "member", "system", ""])
def test_message_allows_only_declared_roles(role: str) -> None:
    with pytest.raises(ValidationError):
        MessageRecord(**valid_message(user_role=role))


def test_message_rejects_naive_and_non_utc_timestamps() -> None:
    with pytest.raises(ValidationError):
        MessageRecord(**valid_message(timestamp="2026-09-01T00:00:00"))

    with pytest.raises(ValidationError):
        MessageRecord(**valid_message(timestamp="2026-09-01T08:00:00+08:00"))


@pytest.mark.parametrize("language", ["en", "es", "zh", "ar", "pt-br", "zh-hans"])
def test_message_accepts_lowercase_bcp47_like_language_codes(language: str) -> None:
    message = MessageRecord(**valid_message(language=language))

    assert message.language == language


@pytest.mark.parametrize("language", ["english", "EN", "en_US", "e", "123", "en-"])
def test_message_rejects_uncontrolled_language_values(language: str) -> None:
    with pytest.raises(ValidationError, match="lowercase BCP-47-like"):
        MessageRecord(**valid_message(language=language))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("message_id", ""),
        ("community_id", "   "),
        ("language", ""),
        ("text", "   "),
        ("reply_to_message_id", ""),
        ("campaign_id", "   "),
    ],
)
def test_message_rejects_empty_required_or_present_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        MessageRecord(**valid_message(**{field: value}))


def test_message_accepts_a_valid_synthetic_record() -> None:
    message = MessageRecord(**valid_message())

    assert message.user_role == "user"
    assert message.timestamp.tzinfo is not None
    assert message.timestamp.utcoffset().total_seconds() == 0


def test_validated_records_are_frozen_against_privacy_mutation() -> None:
    message = MessageRecord(**valid_message())

    with pytest.raises(ValidationError, match="frozen"):
        message.user_id_hash = "Alice"


@pytest.mark.parametrize(
    ("collection", "identifier"),
    [("claims", "claim_id"), ("annotations", "annotation_id")],
)
def test_dataset_rejects_duplicate_record_identifiers(
    collection: str,
    identifier: str,
) -> None:
    data = generate_dataset(seed=101, message_count=120).model_dump(mode="python")
    data[collection][1][identifier] = data[collection][0][identifier]

    with pytest.raises(ValidationError, match=f"{identifier} values must be unique"):
        SyntheticDataset.model_validate(data)


def test_dataset_rejects_duplicate_outcome_pairs_and_unknown_communities() -> None:
    duplicate_data = generate_dataset(seed=103, message_count=120).model_dump(mode="python")
    duplicate_data["outcomes"][1]["community_id"] = duplicate_data["outcomes"][0][
        "community_id"
    ]
    duplicate_data["outcomes"][1]["campaign_id"] = duplicate_data["outcomes"][0]["campaign_id"]

    with pytest.raises(ValidationError, match="outcome community/campaign pairs must be unique"):
        SyntheticDataset.model_validate(duplicate_data)

    unknown_data = generate_dataset(seed=107, message_count=120).model_dump(mode="python")
    unknown_data["outcomes"][0]["community_id"] = "community_unknown"

    with pytest.raises(ValidationError, match="outcome community_id must reference"):
        SyntheticDataset.model_validate(unknown_data)


@pytest.mark.parametrize(
    ("manifest_field", "replacement", "message"),
    [
        ("community_ids", ["community_a"], "manifest community_ids"),
        ("languages", ["en"], "manifest languages"),
        ("campaign_ids", ["campaign_stake"], "manifest campaign_ids"),
        ("synthetic", False, "manifest synthetic must be true"),
    ],
)
def test_dataset_rejects_manifest_disagreement(
    manifest_field: str,
    replacement: object,
    message: str,
) -> None:
    data = generate_dataset(seed=109, message_count=120).model_dump(mode="python")
    data["manifest"][manifest_field] = replacement

    with pytest.raises(ValidationError, match=message):
        SyntheticDataset.model_validate(data)


def test_dataset_rejects_forward_and_cyclic_replies() -> None:
    forward_data = generate_dataset(seed=113, message_count=120).model_dump(mode="python")
    forward_data["messages"][0]["reply_to_message_id"] = forward_data["messages"][5]["message_id"]

    with pytest.raises(ValidationError, match="reply must reference an earlier message"):
        SyntheticDataset.model_validate(forward_data)

    cycle_data = generate_dataset(seed=127, message_count=120).model_dump(mode="python")
    cycle_data["messages"][0]["reply_to_message_id"] = cycle_data["messages"][1]["message_id"]
    cycle_data["messages"][1]["reply_to_message_id"] = cycle_data["messages"][0]["message_id"]

    with pytest.raises(ValidationError, match="reply graph must be acyclic"):
        SyntheticDataset.model_validate(cycle_data)


def test_dataset_rejects_non_chronological_and_cross_campaign_replies() -> None:
    chronological_data = generate_dataset(seed=131, message_count=120).model_dump(mode="python")
    child = next(
        message for message in chronological_data["messages"] if message["reply_to_message_id"]
    )
    parent = next(
        message
        for message in chronological_data["messages"]
        if message["message_id"] == child["reply_to_message_id"]
    )
    child["timestamp"] = parent["timestamp"]

    with pytest.raises(ValidationError, match="reply timestamp must be after parent"):
        SyntheticDataset.model_validate(chronological_data)

    campaign_data = generate_dataset(seed=137, message_count=120).model_dump(mode="python")
    child = next(message for message in campaign_data["messages"] if message["reply_to_message_id"])
    child["campaign_id"] = next(
        campaign_id
        for campaign_id in campaign_data["manifest"]["campaign_ids"]
        if campaign_id != child["campaign_id"]
    )

    with pytest.raises(ValidationError, match="replies must remain within a campaign"):
        SyntheticDataset.model_validate(campaign_data)


def test_dataset_rejects_cross_community_replies() -> None:
    data = generate_dataset(seed=139, message_count=120).model_dump(mode="python")
    child = next(message for message in data["messages"] if message["reply_to_message_id"])
    child["community_id"] = next(
        community_id
        for community_id in data["manifest"]["community_ids"]
        if community_id != child["community_id"]
    )

    with pytest.raises(ValidationError, match="replies must remain within a community"):
        SyntheticDataset.model_validate(data)

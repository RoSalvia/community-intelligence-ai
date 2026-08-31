from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from community_intelligence.models import MessageRecord


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

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from community_intelligence.importers.telegram_json_structural import (
    build_structural_projection,
    calculate_shared_period,
)


def _write_chat(path: Path) -> Path:
    value = {
        "name": "Private Test Community",
        "type": "private_supergroup",
        "id": 999,
        "messages": [
            {
                "id": 1,
                "type": "message",
                "date": "2030-01-01T00:00:00+00:00",
                "date_unixtime": "1715875200",
                "from": "Raw Alice",
                "from_id": "user101",
                "text": "Question?",
            },
            {
                "id": 2,
                "type": "message",
                "date_unixtime": "1715875210",
                "from": "Raw Bob",
                "from_id": "user202",
                "reply_to_message_id": 1,
                "text": ["answer ", {"type": "bold", "text": "here"}],
            },
            {
                "id": 3,
                "type": "message",
                "date_unixtime": "1715875220",
                "from": "Deleted Account",
                "photo": "photos/photo_1.jpg",
                "text": "",
            },
            {
                "id": 4,
                "type": "message",
                "date_unixtime": "1715875230",
                "from_id": "user202",
                "reply_to_message_id": 404,
                "text": "missing parent",
            },
            {
                "id": 5,
                "type": "message",
                "date_unixtime": "1715875240",
                "from_id": "user101",
                "forwarded_from": "Raw Forward Source",
                "edited_unixtime": "1715875250",
                "reactions": [{"type": "emoji", "count": 2, "emoji": "x"}],
                "text": [{"type": "link", "text": "https://example.test"}],
                "text_entities": [{"type": "link", "text": "https://example.test"}],
            },
            {
                "id": 6,
                "type": "service",
                "date_unixtime": "1715875260",
                "actor_id": "user101",
                "action": "invite_members",
                "text": "",
            },
        ],
    }
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def test_projection_reuses_canonical_contract_and_keeps_reply_identity_partitions(tmp_path: Path):
    source = _write_chat(tmp_path / "result.json")

    projection = build_structural_projection(
        source,
        community_id="blum-test",
        language="en",
        user_hash_salt="test-salt",
    )

    audit = projection.audit
    assert audit["coverage"]["ordinary_message_count"] == 5
    assert audit["coverage"]["service_event_count"] == 1
    assert audit["coverage"]["total_record_count"] == 6
    assert audit["identity"]["from_id_message_count"] == 4
    assert audit["identity"]["from_id_coverage"] == 0.8
    assert audit["identity"]["deleted_account_message_count"] == 1
    assert audit["identity"]["messages_without_usable_actor_identity"] == 1
    assert audit["reply"]["messages_with_reply_to_message_id"] == 2
    assert audit["reply"]["resolved_reply_edges"] == 1
    assert audit["reply"]["unresolved_reply_edges"] == 1
    assert audit["reply"]["cross_boundary_replies"] == 1
    assert audit["reply"]["reply_resolution_rate"] == 0.5
    assert audit["reply"]["response_latency_available_count"] == 1
    assert audit["content_structure"] == {
        "text_bearing_message_count": 4,
        "media_only_message_count": 1,
        "textless_without_media_metadata_count": 0,
        "forwarded_message_count": 1,
        "link_message_count": 1,
        "reaction_message_count": 1,
        "edited_metadata_message_count": 1,
        "webpage_preview_message_count": 0,
    }
    assert projection.dataset is not None
    assert len(projection.dataset.messages) == 4
    assert projection.dataset.messages[0].timestamp == datetime(2024, 5, 16, 16, 0, tzinfo=UTC)
    assert projection.messages[1]["text_original"] == "answer here"
    assert projection.identities[projection.messages[1]["message_id"]]["reply_state"] == (
        "resolved_reply"
    )
    assert projection.identities[projection.messages[3]["message_id"]]["reply_state"] == (
        "unresolved_reply"
    )

    serialized = json.dumps(
        {
            "messages": projection.messages,
            "identities": projection.identities,
            "edges": projection.edges,
            "audit": projection.audit,
            "dataset": projection.dataset.model_dump(mode="json"),
        },
        ensure_ascii=False,
        default=str,
    )
    for raw in ("user101", "user202", "Raw Alice", "Raw Bob", "Raw Forward Source"):
        assert raw not in serialized

    audit_only = build_structural_projection(
        source,
        community_id="blum-test",
        language="en",
        user_hash_salt="test-salt",
        build_canonical_dataset=False,
    )
    assert audit_only.dataset is None
    assert (
        audit_only.audit["canonical_dataset"]["source_sha256"]
        == (projection.audit["canonical_dataset"]["source_sha256"])
    )


def test_shared_period_is_derived_from_observed_absolute_timestamps() -> None:
    cn = {
        "coverage": {
            "first_ordinary_message_timestamp": "2024-03-19T01:11:45+00:00",
            "last_ordinary_message_timestamp": "2024-09-22T13:00:00+00:00",
        }
    }
    es = {
        "coverage": {
            "first_ordinary_message_timestamp": "2024-05-16T16:00:00+00:00",
            "last_ordinary_message_timestamp": "2026-09-11T10:00:00+00:00",
        }
    }

    assert calculate_shared_period(cn, es) == {
        "start": "2024-05-16T16:00:00+00:00",
        "end_inclusive": "2024-09-22T13:00:00+00:00",
        "derivation": "max(first ordinary timestamps) through min(last ordinary timestamps)",
    }

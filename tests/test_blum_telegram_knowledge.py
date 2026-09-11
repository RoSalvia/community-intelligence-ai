from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from community_intelligence.acquisition.telegram_announcement import (
    build_announcement_pack,
    freeze_official_channel,
    inspect_complete_channel,
)

CHANNEL = "Blum: All Crypto – One App"


def _live_export() -> bytes:
    channel = {
        "name": CHANNEL,
        "type": "public_channel",
        "id": 10629372799,
        "messages": [
            {
                "id": 101,
                "type": "message",
                "date": "2024-07-22T13:15:00+00:00",
                "date_unixtime": "1721654100",
                "text": ["Blum launched ", {"type": "bold", "text": "Tribes"}],
                "text_entities": [
                    {"type": "plain", "text": "Blum launched "},
                    {"type": "bold", "text": "Tribes"},
                ],
                "photo": "photos/photo_101.jpg",
                "forwarded_from": "Blum Product",
                "reactions": [{"type": "emoji", "count": 7, "emoji": "🔥"}],
            },
            {
                "id": 102,
                "type": "message",
                "date_unixtime": "1721654200",
                "text": "",
                "photo": "photos/photo_102.jpg",
            },
            {
                "id": 103,
                "type": "service",
                "date_unixtime": "1721654300",
                "action": "pin_message",
                "text": "",
            },
        ],
    }
    prefix = json.dumps(
        {"about": "Telegram export", "chats": {"list": [channel]}},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    assert prefix.endswith(b"]}}")
    return prefix[:-3] + b',{"name":"Blum Community [EN]","messages":[{"id":1'


def test_complete_channel_slice_is_stable_while_later_export_is_incomplete(
    tmp_path: Path,
) -> None:
    source = tmp_path / "result.json"
    source.write_bytes(_live_export())

    fingerprint = inspect_complete_channel(source, CHANNEL)
    frozen = freeze_official_channel(
        source,
        CHANNEL,
        tmp_path / "frozen",
        stability_checks=3,
        stability_interval_seconds=0,
    )

    assert fingerprint.channel_id == 10629372799
    assert fingerprint.source_range_sha256 == hashlib.sha256(fingerprint.raw_bytes).hexdigest()
    assert frozen["stability"]["checks"] == 3
    assert frozen["stability"]["stable"] is True
    assert frozen["source_byte_range_sha256"] == fingerprint.source_range_sha256
    assert json.loads((tmp_path / "frozen" / "result.json").read_text())["name"] == CHANNEL


def test_announcement_pack_preserves_message_metadata_and_maps_one_message_per_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "result.json"
    source.write_bytes(_live_export())
    freeze_official_channel(
        source,
        CHANNEL,
        tmp_path / "frozen",
        stability_checks=2,
        stability_interval_seconds=0,
    )

    pack = build_announcement_pack(
        tmp_path / "frozen" / "result.json",
        normalized_path=tmp_path / "normalized.jsonl",
        canonical_username="blumcrypto",
        authority_evidence=(
            "https://blum.io/post/official-blum-links",
            "https://t.me/blumcrypto",
        ),
        observed_at=datetime(2026, 9, 11, 10, 55, tzinfo=UTC),
    )

    assert pack.aggregate["ordinary_message_count"] == 2
    assert pack.aggregate["knowledge_message_count"] == 1
    assert pack.aggregate["textless_ordinary_message_count"] == 1
    assert pack.aggregate["service_event_count"] == 1
    assert pack.aggregate["precise_timestamp_count"] == 2
    assert pack.aggregate["precise_timestamp_coverage"] == 1.0
    assert len(pack.source_inputs) == 1
    source_input = pack.source_inputs[0]
    assert source_input.source_type == "telegram_announcement"
    assert source_input.source_channel == "telegram"
    assert source_input.platform_content_id == "101"
    assert source_input.published_at == datetime(2024, 7, 22, 13, 15, tzinfo=UTC)
    assert source_input.temporal_precision == "second"
    assert source_input.effective_from is None
    assert source_input.metadata_provenance["validity"] == "not-provided"
    assert source_input.canonical_url == "https://t.me/blumcrypto/101"
    assert "Blum launched Tribes" in source_input.content
    normalized = [
        json.loads(line)
        for line in (tmp_path / "normalized.jsonl").read_text().splitlines()
    ]
    assert normalized[0]["text_entities"][1]["type"] == "bold"
    assert normalized[0]["media_references"] == {"photo": "photos/photo_101.jpg"}
    assert normalized[0]["forwarded_metadata"] == {"forwarded_from": "Blum Product"}
    assert normalized[0]["reactions"][0]["count"] == 7

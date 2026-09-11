from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from community_intelligence.importers.telegram_live_json import (
    ChatFingerprint,
    SourceObservation,
    freeze_complete_chats,
    inspect_complete_chats,
    validate_stable_observations,
)

CN = "Blum 官方中文社区🇨🇳"
ES = "Blum Español 🇪🇸🇨🇱🇦🇷🇺🇾🇲🇽🇵🇦"


def _live_export_bytes(*, cn_text: str = "brace } in a string") -> bytes:
    cn = {
        "name": CN,
        "type": "private_supergroup",
        "id": 101,
        "messages": [
            {
                "id": 1,
                "type": "message",
                "date_unixtime": "1710839505",
                "from_id": "user1",
                "text": cn_text,
            }
        ],
    }
    es = {
        "name": ES,
        "type": "private_supergroup",
        "id": 202,
        "messages": [
            {
                "id": 2,
                "type": "message",
                "date_unixtime": "1715875200",
                "from_id": "user2",
                "text": "hola",
            }
        ],
    }
    prefix = json.dumps(
        {"about": "Telegram export", "chats": {"about": "Chats", "list": [cn, es]}},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    # Replace the valid suffix with a comma and an incomplete later EN object.
    marker = b"]}}"
    assert prefix.endswith(marker)
    return prefix[: -len(marker)] + b',{"name":"Blum Community [EN]","messages":[{"id":3'


def test_inspection_finds_complete_target_objects_in_incomplete_live_export(tmp_path: Path) -> None:
    source = tmp_path / "result.json"
    source.write_bytes(_live_export_bytes())

    observation = inspect_complete_chats(source, {"blum-cn": CN, "blum-es": ES})

    assert observation.source_size == source.stat().st_size
    assert set(observation.chats) == {"blum-cn", "blum-es"}
    assert observation.chats["blum-cn"].value["id"] == 101
    assert observation.chats["blum-es"].value["messages"][0]["text"] == "hola"
    for chat in observation.chats.values():
        assert chat.end_offset > chat.start_offset
        assert chat.source_range_sha256 == hashlib.sha256(chat.raw_bytes).hexdigest()


def test_stability_validation_rejects_changed_completed_object() -> None:
    first = SourceObservation(
        captured_at="2026-09-11T10:00:00+00:00",
        source_size=100,
        source_mtime_ns=1,
        chats={"blum-cn": ChatFingerprint("n", 1, 10, 20, "a" * 64, b"{}", {})},
    )
    second = SourceObservation(
        captured_at="2026-09-11T10:00:01+00:00",
        source_size=120,
        source_mtime_ns=2,
        chats={"blum-cn": ChatFingerprint("n", 1, 10, 21, "b" * 64, b"{ }", {})},
    )

    with pytest.raises(ValueError, match="changed between stability observations"):
        validate_stable_observations([first, second])


def test_freeze_writes_parser_ready_private_snapshots_and_provenance(tmp_path: Path) -> None:
    source = tmp_path / "result.json"
    source.write_bytes(_live_export_bytes())
    output = tmp_path / "frozen-v1"

    manifest = freeze_complete_chats(
        source,
        {"blum-cn": CN, "blum-es": ES},
        output,
        stability_checks=2,
        stability_interval_seconds=0,
    )

    assert manifest["stability"]["checks"] == 2
    assert manifest["stability"]["stable"] is True
    assert json.loads((output / "result.json").read_text())["chats"]["list"][0]["name"] == CN
    assert json.loads((output / "blum-cn" / "result.json").read_text())["messages"][0]["id"] == 1
    assert json.loads((output / "blum-es" / "result.json").read_text())["messages"][0]["id"] == 2
    provenance = json.loads((output / "provenance.json").read_text())
    assert provenance["source_path"] == str(source.resolve())
    assert provenance["extraction_method_version"]
    assert (
        provenance["snapshot_sha256"]
        == hashlib.sha256((output / "result.json").read_bytes()).hexdigest()
    )

    with pytest.raises(FileExistsError):
        freeze_complete_chats(
            source,
            {"blum-cn": CN, "blum-es": ES},
            output,
            stability_checks=2,
            stability_interval_seconds=0,
        )

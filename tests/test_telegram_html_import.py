from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from community_intelligence.cli import main
from community_intelligence.importers.telegram import import_telegram_export
from community_intelligence.importers.telegram_html import (
    PARSER_VERSION,
    canonicalize_telegram_html_exports,
)
from community_intelligence.io import read_dataset

FIXTURES = Path(__file__).parent / "fixtures" / "telegram_html"


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _canonicalize(tmp_path: Path, name: str = "canonical") -> Path:
    return canonicalize_telegram_html_exports(
        [FIXTURES / "partial", FIXTURES / "complete"],
        tmp_path / name,
        community_id="community-cn",
        language="zh",
        source_timezone="Asia/Shanghai",
        timezone_provenance="test_operator_assumption",
        identity_salt="synthetic-test-salt",
    )


def test_html_adapter_preserves_structure_privacy_and_raw_provenance(tmp_path: Path) -> None:
    output = _canonicalize(tmp_path)
    messages = _read_jsonl(output / "messages.jsonl")
    services = _read_jsonl(output / "service_events.jsonl")
    media = _read_jsonl(output / "media_manifest.jsonl")
    quarantine = _read_jsonl(output / "parse_quarantine.jsonl")
    manifest = json.loads((output / "dataset_manifest.json").read_text(encoding="utf-8"))

    assert {path.name for path in output.iterdir()} == {
        "dataset_manifest.json",
        "media_manifest.jsonl",
        "messages.jsonl",
        "parse_quarantine.jsonl",
        "service_events.jsonl",
        "m1_dataset",
    }
    assert [item["source_message_id"] for item in messages] == [
        "10",
        "11",
        "13",
        "14",
        "15",
        "16",
        "17",
        "18",
        "19",
    ]
    by_id = {item["source_message_id"]: item for item in messages}
    assert by_id["10"]["text_original"] == "Visit Example"
    assert by_id["10"]["links"] == [{"href": "https://example.invalid/a", "text": "Example"}]
    assert by_id["10"]["timestamp"] == "2024-01-01T02:00:00Z"
    assert by_id["10"]["timestamp_source"] == {
        "local_value": "2024-01-01T10:00:00",
        "raw_title": "1 January 2024, 10:00:00",
        "source_timezone": "Asia/Shanghai",
        "timezone_provenance": "test_operator_assumption",
    }
    assert by_id["11"]["text_original"] == ""
    assert by_id["11"]["author_identity"]["display_name"] == "Alice Example"
    assert by_id["11"]["author_identity"]["resolution"] == "joined_inheritance"
    assert len(by_id["11"]["source_occurrences"]) == 2
    assert by_id["13"]["author_identity"]["display_name"] == "Alice Example"
    assert by_id["13"]["reply_to_message_id"] == "10"
    assert by_id["13"]["reply_to_canonical_message_id"] == by_id["10"]["message_id"]
    assert by_id["13"]["forwarded_from"] == "Forwarded from Forward Source"
    assert by_id["14"]["author_identity"]["display_name"] == "Bob Example"
    assert by_id["16"]["author_identity"]["status"] == "deleted_account"
    assert by_id["17"]["author_identity"]["status"] == "missing"
    assert by_id["17"]["anonymized_author_id"].startswith("usr_")
    assert {item["kind"] for item in media} == {
        "photo",
        "gif",
        "sticker",
        "video_file",
        "embedded_video",
    }
    assert all(item["exists"] for item in media if item["local_path"] is not None)
    assert next(item for item in media if item["kind"] == "embedded_video")["exists"] is False
    assert len(services) == 2
    assert {item["source_message_id"] for item in services} == {None, "12"}
    date_divider = next(item for item in services if item["source_message_id"] is None)
    assert len(date_divider["source_occurrences"]) == 2
    assert {item["reason"] for item in quarantine} == {
        "conflicting_duplicate_source_message_id",
        "missing_author",
    }
    assert manifest["parser_version"] == PARSER_VERSION
    assert manifest["profile"]["ordinary_message_count"] == 9
    assert manifest["profile"]["service_event_count"] == 2
    assert manifest["profile"]["joined_message_count"] == 3
    assert manifest["profile"]["joined_author_inheritance_success_count"] == 3
    assert manifest["profile"]["reply_count"] == 2
    assert manifest["profile"]["resolved_reply_count"] == 2
    assert manifest["profile"]["parse_loss_count"] == 0
    assert manifest["profile"]["unique_author_display_name_count"] == 3
    assert manifest["profile"]["unique_source_message_ids"] == 10
    assert manifest["profile"]["duplicate_message_id_count"] == 2
    assert manifest["profile"]["conflicting_duplicate_message_id_count"] == 1
    assert manifest["m1_compatibility"]["contract"] == (
        "community_intelligence.models.MessageRecord@1.1"
    )
    assert manifest["m1_compatibility"]["compatible_message_count"] == 5
    assert manifest["m1_compatibility"]["incompatible_message_count"] == 4
    assert manifest["m1_compatibility"]["batch_mapping"] == {
        "content_hash": manifest["input_fingerprint"],
        "message_count": 5,
        "source_type": "telegram_desktop_html",
        "window_end": "2024-01-01T02:06:00Z",
        "window_start": "2024-01-01T02:00:00Z",
    }
    assert manifest["m1_compatibility"]["evidence_mapping"] == {
        "evidence_message_id_field": "message_id",
        "material_claim_traceable_to_source_occurrence": True,
        "provenance_sidecar": "messages.jsonl",
    }
    m1_dataset = read_dataset(output / "m1_dataset")
    assert len(m1_dataset.messages) == 5
    assert m1_dataset.manifest.source_format == "telegram_desktop_html_v1_m1_projection"
    assert {message.message_id for message in m1_dataset.messages} == {
        by_id[source_id]["message_id"] for source_id in ("10", "13", "14", "16", "17")
    }

    occurrence = by_id["10"]["source_occurrences"][0]
    source = FIXTURES / occurrence["source_html_file"]
    raw = source.read_text(encoding="utf-8")
    fragment = raw[occurrence["start_offset"] : occurrence["end_offset"]]
    assert hashlib.sha256(fragment.encode("utf-8")).hexdigest() == occurrence["raw_html_sha256"]
    assert 'id="message10"' in fragment


def test_html_adapter_is_create_only_and_byte_deterministic(tmp_path: Path) -> None:
    before = {
        path.relative_to(FIXTURES).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in FIXTURES.rglob("*")
        if path.is_file()
    }
    first = _canonicalize(tmp_path, "first")
    second = _canonicalize(tmp_path, "second")

    assert {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in sorted(first.rglob("*"))
        if path.is_file()
    } == {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in sorted(second.rglob("*"))
        if path.is_file()
    }
    with pytest.raises(FileExistsError, match="output path already exists"):
        _canonicalize(tmp_path, "first")
    after = {
        path.relative_to(FIXTURES).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in FIXTURES.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_html_message_ids_match_existing_telegram_message_contract(tmp_path: Path) -> None:
    output = _canonicalize(tmp_path)
    html_message = _read_jsonl(output / "messages.jsonl")[0]
    json_source = tmp_path / "result.json"
    json_source.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "id": 10,
                        "type": "message",
                        "date": "2024-01-01T02:00:00Z",
                        "from": "Alice Example",
                        "text": "Visit Example",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    json_dataset = import_telegram_export(json_source, community_id="community-cn")

    assert html_message["message_id"] == json_dataset.messages[0].message_id


def test_missing_structural_fields_are_retained_and_quarantined(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "messages.html").write_text(
        """<!DOCTYPE html><html><body><div class="history">
<div class="message default clearfix joined">
  <div class="body"><div class="reply_to details"><a href="#broken">reply</a></div>
  <div class="text">Retain me</div></div>
</div></div></body></html>""",
        encoding="utf-8",
    )

    output = canonicalize_telegram_html_exports(
        [source],
        tmp_path / "canonical",
        community_id="community-cn",
        language="zh",
        source_timezone="Asia/Shanghai",
        timezone_provenance="test_operator_assumption",
        identity_salt="synthetic-test-salt",
    )
    messages = _read_jsonl(output / "messages.jsonl")
    reasons = {item["reason"] for item in _read_jsonl(output / "parse_quarantine.jsonl")}

    assert len(messages) == 1
    assert messages[0]["source_message_id"] is None
    assert messages[0]["timestamp"] is None
    assert messages[0]["author_identity"]["resolution"] == "joined_inheritance_failed"
    assert messages[0]["text_original"] == "Retain me"
    assert reasons == {
        "joined_author_inheritance_failed",
        "malformed_reply_reference",
        "missing_or_malformed_timestamp",
        "missing_source_message_id",
    }


def test_html_cli_creates_private_salt_and_aggregate_only_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    salt = tmp_path / "private" / "identity-salt.txt"
    output = tmp_path / "canonical"

    result = main(
        [
            "import",
            "telegram-html",
            "--input",
            str(FIXTURES / "partial"),
            "--input",
            str(FIXTURES / "complete"),
            "--output",
            str(output),
            "--community-id",
            "community-cn",
            "--language",
            "zh",
            "--source-timezone",
            "Asia/Shanghai",
            "--timezone-provenance",
            "test_operator_assumption",
            "--identity-salt-file",
            str(salt),
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    assert result == 0
    assert salt.is_file()
    assert salt.stat().st_mode & 0o777 == 0o600
    assert summary == {
        "dataset_dir": str(output.resolve()),
        "ordinary_message_count": 9,
        "output_fingerprint": json.loads(
            (output / "dataset_manifest.json").read_text(encoding="utf-8")
        )["output_fingerprint"],
        "parse_quarantine_count": 2,
        "service_event_count": 2,
        "source_format": "telegram_desktop_html",
    }


def test_adapter_rejects_output_inside_read_only_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "messages.html").write_text(
        '<div class="message service"><div class="body details">date</div></div>',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside source export roots"):
        canonicalize_telegram_html_exports(
            [source],
            source / "canonical",
            community_id="community-cn",
            language="zh",
            source_timezone="Asia/Shanghai",
            timezone_provenance="test_operator_assumption",
            identity_salt="synthetic-test-salt",
        )


def test_unresolved_reply_is_profiled_without_becoming_parse_quarantine(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "messages.html").write_text(
        """<div class="message default clearfix" id="message1"><div class="body">
<div class="pull_right date details" title="1 January 2024, 10:00:00"></div>
<div class="from_name">Alice</div>
<div class="reply_to details"><a href="#go_to_message999">this message</a></div>
<div class="text">Retained reply</div></div></div>""",
        encoding="utf-8",
    )

    output = canonicalize_telegram_html_exports(
        [source],
        tmp_path / "canonical",
        community_id="community-cn",
        language="zh",
        source_timezone="Asia/Shanghai",
        timezone_provenance="test_operator_assumption",
        identity_salt="synthetic-test-salt",
    )
    manifest = json.loads((output / "dataset_manifest.json").read_text(encoding="utf-8"))

    assert _read_jsonl(output / "parse_quarantine.jsonl") == []
    assert manifest["profile"]["reply_count"] == 1
    assert manifest["profile"]["unresolved_reply_count"] == 1
    assert manifest["profile"]["reply_resolution_rate"] == 0


def test_conflicting_snapshot_media_variants_are_both_retained(tmp_path: Path) -> None:
    complete = tmp_path / "a-complete"
    older = tmp_path / "z-older"
    complete.mkdir()
    older.mkdir()
    (complete / "messages.html").write_text(
        """<div class="message default clearfix" id="message1"><div class="body">
<div class="pull_right date details" title="1 January 2024, 10:00:00"></div>
<div class="from_name">Alice</div><div class="media_wrap clearfix">
<div class="media clearfix pull_left media_video">
<div class="status details">Not included</div></div>
</div></div></div>""",
        encoding="utf-8",
    )
    (older / "video_files").mkdir()
    (older / "video_files" / "1.mp4").write_bytes(b"synthetic video")
    (older / "messages.html").write_text(
        """<div class="message default clearfix" id="message1"><div class="body">
<div class="pull_right date details" title="1 January 2024, 10:00:00"></div>
<div class="from_name">Alice</div>
<a class="video_file_wrap clearfix pull_left" href="video_files/1.mp4"></a>
</div></div>""",
        encoding="utf-8",
    )

    output = canonicalize_telegram_html_exports(
        [older, complete],
        tmp_path / "canonical",
        community_id="community-cn",
        language="zh",
        source_timezone="Asia/Shanghai",
        timezone_provenance="test_operator_assumption",
        identity_salt="synthetic-test-salt",
    )
    message = _read_jsonl(output / "messages.jsonl")[0]
    media = _read_jsonl(output / "media_manifest.jsonl")

    assert len(message["media_refs"]) == 2
    assert {item["kind"] for item in media} == {"embedded_video", "video_file"}
    assert next(item for item in media if item["kind"] == "video_file")["exists"] is True


def test_tracked_schema_covers_required_canonical_fields() -> None:
    schema_path = (
        Path(__file__).parents[1] / "docs" / "schemas" / "telegram_html_canonical_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    message = schema["$defs"]["CanonicalMessage"]

    assert set(schema["$defs"]) >= {
        "CanonicalMessage",
        "DatasetManifest",
        "MediaReference",
        "QuarantineRecord",
        "ServiceEvent",
    }

    assert set(message["required"]) >= {
        "source_message_id",
        "source_platform",
        "community_id",
        "timestamp",
        "author_identity",
        "anonymized_author_id",
        "text_original",
        "reply_to_message_id",
        "forwarded_from",
        "links",
        "media_refs",
        "source_html_file",
        "source_ordinal",
        "raw_content_hash",
        "content_hash",
        "parser_version",
    }

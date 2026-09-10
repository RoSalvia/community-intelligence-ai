from __future__ import annotations

import json
from pathlib import Path

import pytest

from community_intelligence.cli import main
from community_intelligence.importers.telegram import import_telegram_export
from community_intelligence.io import read_dataset


def _write_export(path: Path) -> Path:
    value = {
        "name": "Alpha Community",
        "type": "private_supergroup",
        "id": 987654321,
        "messages": [
            {
                "id": 10,
                "type": "message",
                "date": "2026-08-31T16:00:00+00:00",
                "date_unixtime": "1788192000",
                "from": "Alice Raw Name",
                "from_id": "user123456",
                "text": "Hello community",
            },
            {
                "id": 11,
                "type": "message",
                "date": "2026-08-31T16:00:00+00:00",
                "date_unixtime": "1788192000",
                "from": "Bob Raw Name",
                "from_id": "user999999",
                "reply_to_message_id": 10,
                "text": ["Helpful ", {"type": "bold", "text": "reply"}],
            },
            {
                "id": 12,
                "type": "service",
                "date_unixtime": "1788192001",
                "actor": "Alice Raw Name",
                "actor_id": "user123456",
                "action": "invite_members",
                "text": "",
            },
            {
                "id": 13,
                "type": "message",
                "date_unixtime": "1788192002",
                "from": "Bob Raw Name",
                "from_id": "user999999",
                "text": "",
            },
        ],
    }
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def test_telegram_export_normalizes_rich_text_replies_and_anonymizes_identifiers(
    tmp_path: Path,
) -> None:
    source = _write_export(tmp_path / "result.json")

    first = import_telegram_export(source)
    second = import_telegram_export(source)

    assert first == second
    assert first.manifest.synthetic is False
    assert first.manifest.source_format == "telegram_desktop_json_v0.1"
    assert first.manifest.seed is None
    assert first.campaigns == []
    assert first.claims == []
    assert first.outcomes == []
    assert first.annotations == []
    assert [message.text for message in first.messages] == [
        "Hello community",
        "Helpful reply",
    ]
    assert first.messages[1].reply_to_message_id == first.messages[0].message_id
    assert first.messages[0].timestamp == first.messages[1].timestamp
    assert {message.language for message in first.messages} == {"und"}
    assert {message.user_role for message in first.messages} == {"user"}
    serialized = json.dumps(first.model_dump(mode="json"), ensure_ascii=False)
    assert "user123456" not in serialized
    assert "user999999" not in serialized
    assert "987654321" not in serialized
    assert "Alice Raw Name" not in serialized
    assert "Bob Raw Name" not in serialized
    assert any("moderator roles" in item for item in first.manifest.limitations)


def test_telegram_cli_import_then_analyze_produces_community_only_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write_export(tmp_path / "result.json")
    dataset_dir = tmp_path / "dataset"
    report_dir = tmp_path / "report"

    assert (
        main(
            [
                "import",
                "telegram",
                "--input",
                str(source),
                "--output",
                str(dataset_dir),
                "--language",
                "en",
            ]
        )
        == 0
    )
    import_summary = json.loads(capsys.readouterr().out)
    assert import_summary["message_count"] == 2
    assert Path(import_summary["dataset_dir"]) == dataset_dir
    assert read_dataset(dataset_dir).manifest.languages == ["en"]
    published = "".join(path.read_text(encoding="utf-8") for path in sorted(dataset_dir.iterdir()))
    assert "user123456" not in published
    assert "user999999" not in published
    assert "987654321" not in published

    assert main(["analyze", "--input", str(dataset_dir), "--output", str(report_dir)]) == 0
    capsys.readouterr()
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["Overview"]["message_count"] == 2
    assert report["Overview"]["source"]["format"] == "telegram_desktop_json_v0.1"
    assert any("moderator roles" in item for item in report["Overview"]["source"]["limitations"])
    assert report["capabilities"]["community_analysis"]["status"] == "available"
    assert report["capabilities"]["campaign_intelligence"] == {
        "status": "not_available",
        "reason": "No campaign data provided",
    }


@pytest.mark.parametrize(
    "value",
    [
        [],
        {"name": "No messages"},
        {"name": "Wrong messages", "messages": {}},
        {"name": "Empty messages", "messages": []},
    ],
)
def test_invalid_telegram_export_has_concise_error_without_partial_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    value: object,
) -> None:
    source = tmp_path / "result.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    output = tmp_path / "dataset"

    result = main(["import", "telegram", "--input", str(source), "--output", str(output)])

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err.startswith("error: invalid Telegram Desktop export:")
    assert "Traceback" not in captured.err
    assert not output.exists()

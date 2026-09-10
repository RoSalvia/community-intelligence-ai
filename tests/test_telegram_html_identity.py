from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from community_intelligence.cli import main
from community_intelligence.importers.telegram_html import canonicalize_telegram_html_exports


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_source(root: Path) -> None:
    root.mkdir()
    (root / "messages.html").write_text(
        """<!DOCTYPE html><html><body><div class="history">
<div class="message default clearfix" id="message1">
  <div class="body"><div class="pull_right date details" title="1 January 2024, 10:00:00"></div>
  <div class="from_name">Alice Example</div><img class="userpic" src="photos/author_alpha.jpg">
  <div class="text">one</div></div>
</div>
<div class="message default clearfix joined" id="message2">
  <div class="body"><div class="pull_right date details" title="1 January 2024, 10:01:00"></div>
  <div class="reply_to details"><a href="#go_to_message1">reply</a></div>
  <div class="text">two</div></div>
</div>
<div class="message default clearfix" id="message3">
  <div class="body"><div class="pull_right date details" title="1 January 2024, 10:02:00"></div>
  <div class="from_name">Bob Example</div><img class="userpic" src="photos/author_beta.jpg">
  <div class="reply_to details"><a href="#go_to_message1">reply</a></div>
  <div class="text">three</div></div>
</div>
<div class="message default clearfix" id="message4">
  <div class="body"><div class="pull_right date details" title="1 January 2024, 10:03:00"></div>
  <div class="from_name">Carol Example</div>
  <div class="userpic"><div class="initials">CE</div></div>
  <div class="reply_to details"><a href="#go_to_message1">reply</a></div>
  <div class="text">four</div></div>
</div>
<div class="message default clearfix joined" id="message5">
  <div class="body"><div class="pull_right date details" title="1 January 2024, 10:04:00"></div>
  <div class="reply_to details"><a href="#go_to_message3">reply</a></div>
  <div class="text">five</div></div>
</div>
</div></body></html>""",
        encoding="utf-8",
    )
    (root / "messages2.html").write_text(
        """<!DOCTYPE html><html><body><div class="history">
<div class="message default clearfix" id="message6">
  <div class="body"><div class="pull_right date details" title="1 January 2024, 10:05:00"></div>
  <div class="from_name">Deleted Account</div>
  <div class="userpic"><div class="initials">DA</div></div>
  <div class="reply_to details"><a href="#go_to_message3">reply</a></div>
  <div class="text">six</div></div>
</div>
<div class="message default clearfix joined" id="message7">
  <div class="body"><div class="pull_right date details" title="1 January 2024, 10:06:00"></div>
  <div class="text">seven</div></div>
</div>
<div class="message default clearfix" id="message8">
  <div class="body"><div class="pull_right date details" title="1 January 2024, 10:07:00"></div>
  <div class="from_name">Carol Example</div>
  <div class="userpic"><div class="initials">CE</div></div>
  <div class="text">eight</div></div>
</div>
<div class="message default clearfix" id="message9">
  <div class="body"><div class="pull_right date details" title="1 January 2024, 10:08:00"></div>
  <div class="from_name">Bob Example</div><img class="userpic" src="photos/author_beta.jpg">
  <div class="reply_to details"><a href="#go_to_message999">reply</a></div>
  <div class="text">nine</div></div>
</div>
</div></body></html>""",
        encoding="utf-8",
    )


def _files_sha256(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_identity_projection_is_additive_private_and_deterministic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source"
    _write_source(source)
    canonical = canonicalize_telegram_html_exports(
        [source],
        tmp_path / "canonical-v1",
        community_id="community-cn",
        language="zh",
        source_timezone="Asia/Shanghai",
        timezone_provenance="human-confirmed by dataset owner",
        identity_salt="canonical-test-salt",
    )
    canonical_before = _files_sha256(canonical)
    salt = tmp_path / "private" / "identity-salt.txt"

    result = main(
        [
            "derive",
            "telegram-html-identity",
            "--canonical-input",
            str(canonical),
            "--input",
            str(source),
            "--output",
            str(tmp_path / "identity-first"),
            "--identity-salt-file",
            str(salt),
        ]
    )

    first_summary = json.loads(capsys.readouterr().out)
    first = tmp_path / "identity-first"
    identities = _read_jsonl(first / "message_identities.jsonl")
    edges = _read_jsonl(first / "reply_edges.jsonl")
    manifest = json.loads((first / "identity_manifest.json").read_text(encoding="utf-8"))
    metric_contract = json.loads(
        (first / "metric_identity_contract.json").read_text(encoding="utf-8")
    )

    assert result == 0
    assert set(path.name for path in first.iterdir()) == {
        "identity_manifest.json",
        "message_identities.jsonl",
        "metric_identity_contract.json",
        "reply_edges.jsonl",
    }
    assert _files_sha256(canonical) == canonical_before
    assert salt.stat().st_mode & 0o777 == 0o600
    assert first_summary == {
        "high_confidence_identity_message_count": 4,
        "identity_projection_dir": str(first.resolve()),
        "identity_strategy_version": "telegram-html-author-identity-v1.1",
        "lower_confidence_reply_edge_count": 3,
        "resolved_reply_edge_count": 5,
    }

    by_source_id = {row["source_message_id"]: row for row in identities}
    assert by_source_id["1"]["identity_signal"] == "avatar_token"
    assert by_source_id["1"]["identity_confidence"] == "high"
    assert by_source_id["2"]["identity_signal"] == "joined_avatar_token"
    assert by_source_id["2"]["resolved_identity_id"] == by_source_id["1"]["resolved_identity_id"]
    assert by_source_id["4"]["identity_signal"] == "conservative_anchor"
    assert by_source_id["4"]["identity_confidence"] == "medium"
    assert by_source_id["5"]["resolved_identity_id"] == by_source_id["4"]["resolved_identity_id"]
    assert by_source_id["8"]["resolved_identity_id"] != by_source_id["4"]["resolved_identity_id"]
    assert by_source_id["6"]["identity_signal"] == "deleted_account_anchor"
    assert by_source_id["6"]["identity_confidence"] == "low"
    assert by_source_id["7"]["resolved_identity_id"] == by_source_id["6"]["resolved_identity_id"]
    assert {row["identity_scope"] for row in identities} == {"export_local"}
    assert {row["reply_state"] for row in identities} == {
        "resolved_reply",
        "unresolved_reply",
        "non_reply",
    }
    assert sum(row["reply_state"] == "resolved_reply" for row in identities) == 5
    assert sum(row["reply_state"] == "unresolved_reply" for row in identities) == 1
    assert sum(row["reply_state"] == "non_reply" for row in identities) == 3

    assert len(edges) == 5
    assert sum(row["identity_edge_confidence"] == "high" for row in edges) == 2
    assert sum(row["identity_edge_confidence"] == "medium" for row in edges) == 2
    assert sum(row["identity_edge_confidence"] == "low" for row in edges) == 1
    assert sum(row["author_relation"] == "self" for row in edges) == 1
    assert sum(row["author_relation"] == "cross_author" for row in edges) == 1
    assert sum(row["author_relation"] == "uncertain" for row in edges) == 3

    assert manifest["identity_strategy_version"] == "telegram-html-author-identity-v1.1"
    assert manifest["canonical_contract"] == "telegram-html-canonical-v1.0.0"
    assert manifest["canonical_raw_facts_unchanged"] is True
    assert manifest["profile"]["identity_confidence_message_counts"] == {
        "high": 4,
        "low": 2,
        "medium": 3,
    }
    assert manifest["profile"]["reply_state_counts"] == {
        "non_reply": 3,
        "resolved_reply": 5,
        "unresolved_reply": 1,
    }
    assert manifest["profile"]["reply_edge_confidence_counts"] == {
        "high": 2,
        "low": 1,
        "medium": 2,
    }
    assert manifest["profile"]["self_cross_classification_counts"] == {
        "cross_author": 1,
        "self": 1,
        "uncertain": 3,
    }
    assert manifest["source_timezone"] == {
        "html_metadata_present": False,
        "source_timezone": "Asia/Shanghai",
        "timezone_not_declared_by_source_html": True,
        "timezone_provenance": "human-confirmed by dataset owner",
    }
    assert metric_contract["metric_classes"]["message_level"]["identity_required"] is False
    assert (
        metric_contract["metric_classes"]["high_confidence_identity"][
            "required_identity_confidence"
        ]
        == "high"
    )
    assert (
        metric_contract["metric_classes"]["broader_identity_dependent"][
            "must_report_identity_coverage"
        ]
        is True
    )
    assert metric_contract["additional_metric_dependencies"]["status"] == (
        "not_produced_by_identity_projection"
    )
    assert (
        metric_contract["coverage_reporting_requirements"][
            "single_unique_user_number_without_quality_context_allowed"
        ]
        is False
    )
    assert (
        metric_contract["prohibited_interpretations"]["conservative_anchor_equals_real_user"]
        is True
    )

    serialized = "\n".join(
        path.read_text(encoding="utf-8") for path in first.iterdir() if path.is_file()
    )
    assert "author_alpha" not in serialized
    assert "author_beta" not in serialized
    assert '"alpha"' not in serialized
    assert '"beta"' not in serialized

    second_result = main(
        [
            "derive",
            "telegram-html-identity",
            "--canonical-input",
            str(canonical),
            "--input",
            str(source),
            "--output",
            str(tmp_path / "identity-second"),
            "--identity-salt-file",
            str(salt),
        ]
    )
    capsys.readouterr()
    assert second_result == 0
    assert {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    } == {
        path.relative_to(tmp_path / "identity-second").as_posix(): path.read_bytes()
        for path in (tmp_path / "identity-second").rglob("*")
        if path.is_file()
    }

    assert (
        main(
            [
                "derive",
                "telegram-html-identity",
                "--canonical-input",
                str(canonical),
                "--input",
                str(source),
                "--output",
                str(first),
                "--identity-salt-file",
                str(salt),
            ]
        )
        == 1
    )
    assert "output path already exists" in capsys.readouterr().err


def test_identity_sidecar_schema_forbids_raw_token_and_covers_required_contract() -> None:
    schema_path = (
        Path(__file__).parents[1] / "docs" / "schemas" / "telegram_html_identity_v1_1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    message_identity = schema["$defs"]["MessageIdentity"]

    assert {
        "resolved_identity_id",
        "identity_strategy_version",
        "identity_signal",
        "identity_scope",
        "identity_confidence",
        "display_name_metadata",
        "reply_state",
    } <= set(message_identity["required"])
    assert "raw_avatar_token" not in message_identity["properties"]
    assert message_identity["properties"]["raw_avatar_token_persisted"] == {"const": False}
    assert set(schema["$defs"]) == {
        "DisplayNameMetadata",
        "IdentityManifest",
        "MessageIdentity",
        "MetricIdentityContract",
        "ReplyEdge",
    }

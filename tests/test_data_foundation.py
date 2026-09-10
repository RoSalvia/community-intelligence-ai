from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from community_intelligence.application.data_foundation import (
    DataFoundationService,
)
from community_intelligence.infrastructure.database import analysis_runs, messages

NOW = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)


def telegram_export(path: Path) -> Path:
    payload = {
        "name": "CN Community",
        "type": "private_supergroup",
        "id": 99,
        "messages": [
            {
                "id": 1,
                "type": "message",
                "date": "2026-09-10T06:00:00+00:00",
                "from": "Alice Real Name",
                "from_id": "user123",
                "from_username": "alice_wallet",
                "text": "钱包一直连不上，有人也是吗？",
            },
            {
                "id": 2,
                "type": "message",
                "date": "2026-09-10T06:05:00+00:00",
                "from": "CN Mod",
                "from_id": "user999",
                "reply_to_message_id": 1,
                "text": "请先等待，我们正在检查。",
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def service(tmp_path: Path) -> DataFoundationService:
    return DataFoundationService(
        database_path=tmp_path / "community-intelligence.sqlite3",
        artifact_root=tmp_path / "runs",
        clock=lambda: NOW,
    )


def test_workspace_communities_and_batch_import_are_persistent_and_idempotent(
    service: DataFoundationService,
    tmp_path: Path,
) -> None:
    workspace = service.create_workspace("Wallet Project")
    communities = [
        service.create_community(workspace["workspace_id"], "English", "en", "UTC"),
        service.create_community(workspace["workspace_id"], "中文", "zh", "Asia/Shanghai"),
        service.create_community(workspace["workspace_id"], "Español", "es", "Europe/Madrid"),
    ]

    source = telegram_export(tmp_path / "result.json")
    first = service.import_telegram(communities[1]["community_id"], source)
    second = service.import_telegram(communities[1]["community_id"], source)

    assert first["message_count"] == 2
    assert first["duplicate"] is False
    assert second == {**first, "duplicate": True}
    loaded = service.get_workspace(workspace["workspace_id"])
    assert [item["language"] for item in loaded["communities"]] == ["en", "zh", "es"]

    messages = service.list_messages(workspace["workspace_id"])
    assert len(messages) == 2
    assert all(item["user_id_hash"].startswith("usr_") for item in messages)
    assert "user123" not in json.dumps(messages)
    assert "Alice Real Name" not in json.dumps(messages)
    assert messages[1]["reply_to_message_id"] == messages[0]["message_id"]
    actors = service.list_actors(workspace["workspace_id"])
    assert actors[0]["display_name"] == "Alice Real Name"
    assert actors[0]["platform_handle"] == "@alice_wallet"
    assert actors[0]["operator_label"] == "Alice Real Name (@alice_wallet)"
    assert actors[1]["operator_label"] == "CN Mod"
    assert "user123" not in json.dumps(actors)

    renamed = service.update_workspace(workspace["workspace_id"], "Wallet Ops")
    assert renamed["project_name"] == "Wallet Ops"
    assert renamed["settings_version"] == 2


def test_imported_source_messages_are_immutable(
    service: DataFoundationService,
    tmp_path: Path,
) -> None:
    workspace = service.create_workspace("Wallet Project")
    community = service.create_community(workspace["workspace_id"], "中文", "zh", "Asia/Shanghai")
    service.import_telegram(community["community_id"], telegram_export(tmp_path / "result.json"))
    source_message = service.list_messages(workspace["workspace_id"])[0]

    with (
        pytest.raises(IntegrityError, match="source messages are immutable"),
        service.database.engine.begin() as connection,
    ):
        connection.execute(
            update(messages)
            .where(messages.c.message_id == source_message["message_id"])
            .values(original_text="rewritten")
        )


def test_actor_identity_falls_back_to_stable_local_pseudonym(
    service: DataFoundationService,
    tmp_path: Path,
) -> None:
    workspace = service.create_workspace("Wallet Project")
    community = service.create_community(workspace["workspace_id"], "中文", "zh", "UTC")
    source = tmp_path / "anonymous.json"
    source.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "id": 41,
                        "type": "message",
                        "date": "2026-09-10T06:00:00Z",
                        "from_id": "user-secret-41",
                        "text": "钱包无法连接",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    service.import_telegram(community["community_id"], source)
    actor = service.list_actors(workspace["workspace_id"])[0]

    assert actor["display_name"] is None
    assert actor["platform_handle"] is None
    assert actor["operator_label"].startswith("User ")
    assert "user-secret-41" not in json.dumps(actor)


@pytest.mark.parametrize("parent_first", [True, False])
def test_reply_parent_can_resolve_across_sync_batches_in_either_import_order(
    service: DataFoundationService,
    tmp_path: Path,
    parent_first: bool,
) -> None:
    workspace = service.create_workspace("Wallet Project")
    community = service.create_community(workspace["workspace_id"], "中文", "zh", "UTC")
    parent_source = tmp_path / "parent.json"
    parent_source.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "id": 70,
                        "type": "message",
                        "date": "2026-09-10T06:00:00Z",
                        "from": "Alice",
                        "from_id": "user-70",
                        "text": "钱包无法连接",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    child_source = tmp_path / "child.json"
    child_source.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "id": 71,
                        "type": "message",
                        "date": "2026-09-10T06:05:00Z",
                        "from": "Mod Chen",
                        "from_id": "user-71",
                        "reply_to_message_id": 70,
                        "text": "正在检查",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    sources = (parent_source, child_source) if parent_first else (child_source, parent_source)
    first_batch = service.import_telegram(community["community_id"], sources[0])
    if not parent_first:
        pending = service.list_messages(workspace["workspace_id"])
        assert pending[0]["reply_to_message_id"] is None
    second_batch = service.import_telegram(community["community_id"], sources[1])
    imported = service.list_messages(workspace["workspace_id"])

    assert first_batch["source_batch_id"] != second_batch["source_batch_id"]
    assert imported[1]["reply_to_message_id"] == imported[0]["message_id"]
    expected_child_batch = second_batch if parent_first else first_batch
    assert imported[1]["source_batch_id"] == expected_child_batch["source_batch_id"]


def test_community_contract_rejects_unsupported_or_duplicate_language(
    service: DataFoundationService,
) -> None:
    workspace = service.create_workspace("Wallet Project")
    service.create_community(workspace["workspace_id"], "中文", "zh", "Asia/Shanghai")

    with pytest.raises(ValueError, match="EN, CN, and ES"):
        service.create_community(workspace["workspace_id"], "Arabic", "ar", "UTC")
    with pytest.raises(ValueError, match="already configured"):
        service.create_community(workspace["workspace_id"], "CN 2", "zh", "UTC")


def test_role_assignment_is_effective_dated_and_does_not_modify_messages(
    service: DataFoundationService,
    tmp_path: Path,
) -> None:
    workspace = service.create_workspace("Wallet Project")
    community = service.create_community(workspace["workspace_id"], "中文", "zh", "Asia/Shanghai")
    service.import_telegram(community["community_id"], telegram_export(tmp_path / "result.json"))
    messages_before = service.list_messages(workspace["workspace_id"])
    moderator_hash = messages_before[1]["user_id_hash"]

    assignment = service.set_role_assignment(
        workspace["workspace_id"],
        moderator_hash,
        "moderator",
        valid_from=NOW - timedelta(days=1),
        valid_to=None,
    )

    messages_after = service.list_messages(workspace["workspace_id"])
    assert assignment["version"] == 1
    assert messages_before == messages_after
    resolved = service.list_messages(workspace["workspace_id"], resolve_roles=True)
    assert [item["user_role"] for item in resolved] == ["user", "moderator"]


def test_freshness_and_since_last_check_use_explicit_watermark(
    service: DataFoundationService,
    tmp_path: Path,
) -> None:
    workspace = service.create_workspace("Wallet Project")
    community = service.create_community(workspace["workspace_id"], "中文", "zh", "Asia/Shanghai")
    service.import_telegram(community["community_id"], telegram_export(tmp_path / "result.json"))

    freshness = service.get_freshness(workspace["workspace_id"])
    assert freshness[0]["latest_message_at"] == "2026-09-10T06:05:00Z"
    assert freshness[0]["status"] == "current"

    first_window = service.resolve_window(workspace["workspace_id"], "since_last_check")
    assert first_window["fallback_used"] is True
    assert first_window["start"] == "2026-09-09T08:00:00Z"
    assert first_window["end"] == "2026-09-10T08:00:00Z"
    assert first_window["baseline_start"] == "2026-09-08T08:00:00Z"
    assert first_window["baseline_end"] == "2026-09-09T08:00:00Z"

    service.mark_checked(workspace["workspace_id"], NOW - timedelta(hours=3))
    next_window = service.resolve_window(workspace["workspace_id"], "since_last_check")
    assert next_window["fallback_used"] is False
    assert next_window["start"] == "2026-09-10T05:00:00Z"


def test_analysis_run_executes_the_preserved_legacy_pipeline(
    service: DataFoundationService,
    tmp_path: Path,
) -> None:
    workspace = service.create_workspace("Wallet Project")
    community = service.create_community(workspace["workspace_id"], "中文", "zh", "Asia/Shanghai")
    service.import_telegram(community["community_id"], telegram_export(tmp_path / "result.json"))

    queued = service.create_analysis_run(workspace["workspace_id"], "24h")
    assert queued["status"] == "queued"
    finished = service.execute_analysis_run(queued["analysis_run_id"])

    assert finished["status"] == "succeeded"
    assert Path(finished["report_path"]).is_file()
    report = json.loads(Path(finished["report_path"]).read_text(encoding="utf-8"))
    assert report["Overview"]["message_count"] == 2
    assert report["Overview"]["language_counts"] == {"zh": 2}
    exported = "".join(
        path.read_text(encoding="utf-8")
        for path in Path(finished["report_path"]).parents[1].rglob("*")
        if path.is_file()
    )
    assert "Alice Real Name" not in exported
    assert "alice_wallet" not in exported
    assert "CN Mod" not in exported

    reused = service.create_analysis_run(workspace["workspace_id"], "24h")
    assert reused["analysis_run_id"] == finished["analysis_run_id"]
    assert reused["reused"] is True


def test_no_activity_and_interrupted_runs_have_explicit_terminal_states(tmp_path: Path) -> None:
    database_path = tmp_path / "community-intelligence.sqlite3"
    artifact_root = tmp_path / "runs"
    service = DataFoundationService(
        database_path=database_path,
        artifact_root=artifact_root,
        clock=lambda: NOW,
    )
    empty_workspace = service.create_workspace("Empty")
    service.create_community(empty_workspace["workspace_id"], "中文", "zh", "UTC")
    empty_run = service.create_analysis_run(empty_workspace["workspace_id"], "24h")
    assert empty_run["status"] == "succeeded"
    assert empty_run["activity_status"] == "no_new_activity"
    assert empty_run["progress"] == 100

    active_workspace = service.create_workspace("Active")
    community = service.create_community(active_workspace["workspace_id"], "中文", "zh", "UTC")
    service.import_telegram(community["community_id"], telegram_export(tmp_path / "result.json"))
    queued = service.create_analysis_run(active_workspace["workspace_id"], "24h")
    with service.database.engine.begin() as connection:
        connection.execute(
            update(analysis_runs)
            .where(analysis_runs.c.analysis_run_id == queued["analysis_run_id"])
            .values(status="running")
        )

    restarted = DataFoundationService(
        database_path=database_path,
        artifact_root=artifact_root,
        clock=lambda: NOW,
    )
    recovered = restarted.get_analysis_run(queued["analysis_run_id"])
    assert recovered["status"] == "failed"
    assert recovered["error"] == "Analysis was interrupted before completion"

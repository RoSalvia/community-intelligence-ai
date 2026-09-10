from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from community_intelligence.web.app import create_app


def telegram_bytes() -> bytes:
    return json.dumps(
        {
            "name": "CN Community",
            "type": "private_supergroup",
            "id": 99,
            "messages": [
                {
                    "id": 1,
                    "type": "message",
                    "date": "2026-09-10T06:00:00+00:00",
                    "from": "Alice",
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
        },
        ensure_ascii=False,
    ).encode()


def test_v1_api_runs_workspace_import_role_freshness_and_analysis_flow(tmp_path: Path) -> None:
    client = TestClient(create_app(data_root=tmp_path / "app-data"))

    workspace_response = client.post("/api/v1/workspaces", json={"project_name": "Wallet Project"})
    assert workspace_response.status_code == 201
    workspace = workspace_response.json()
    renamed = client.patch(
        f"/api/v1/workspaces/{workspace['workspace_id']}",
        json={"project_name": "Wallet Operations"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["project_name"] == "Wallet Operations"

    communities = {}
    for language, name, timezone in (
        ("en", "English", "UTC"),
        ("zh", "中文", "Asia/Shanghai"),
        ("es", "Español", "Europe/Madrid"),
    ):
        response = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/communities",
            json={
                "name": name,
                "language": language,
                "timezone": timezone,
                "platform": "telegram",
            },
        )
        assert response.status_code == 201
        communities[language] = response.json()

    imported = client.post(
        f"/api/v1/communities/{communities['zh']['community_id']}/imports/telegram",
        files={"file": ("result.json", telegram_bytes(), "application/json")},
    )
    assert imported.status_code == 201
    assert imported.json()["message_count"] == 2

    duplicate = client.post(
        f"/api/v1/communities/{communities['zh']['community_id']}/imports/telegram",
        files={"file": ("result.json", telegram_bytes(), "application/json")},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

    actors = client.get(f"/api/v1/workspaces/{workspace['workspace_id']}/actors").json()
    assert actors["count"] == 2
    assert actors["items"][0]["operator_label"] == "Alice (@alice_wallet)"
    assert actors["items"][1]["operator_label"] == "CN Mod"
    assert {item["identity_scope"] for item in actors["items"]} == {"local_only"}
    assert "user999" not in json.dumps(actors)
    moderator_hash = actors["items"][1]["user_id_hash"]
    role = client.put(
        f"/api/v1/workspaces/{workspace['workspace_id']}/role-assignments",
        json={
            "user_id_hash": moderator_hash,
            "role": "moderator",
            "valid_from": "2026-09-01T00:00:00Z",
            "valid_to": None,
        },
    )
    assert role.status_code == 200
    assert role.json()["role"] == "moderator"

    freshness = client.get(f"/api/v1/workspaces/{workspace['workspace_id']}/freshness")
    assert freshness.status_code == 200
    assert [item["language"] for item in freshness.json()["items"]] == ["en", "zh", "es"]
    assert freshness.json()["items"][1]["latest_message_at"] == "2026-09-10T06:05:00Z"

    queued = client.post(
        f"/api/v1/workspaces/{workspace['workspace_id']}/analysis-runs",
        json={
            "window": "custom",
            "start": "2026-09-10T00:00:00Z",
            "end": "2026-09-11T00:00:00Z",
        },
    )
    assert queued.status_code == 202
    run = client.get(f"/api/v1/analysis-runs/{queued.json()['analysis_run_id']}")
    assert run.status_code == 200
    assert run.json()["status"] == "succeeded"
    assert Path(run.json()["report_path"]).is_file()


def test_v1_api_reports_product_boundaries_without_partial_state(tmp_path: Path) -> None:
    client = TestClient(create_app(data_root=tmp_path / "app-data"))
    actor_schema = client.get("/api/openapi.json").json()["components"]["schemas"][
        "ActorIdentityResponse"
    ]
    assert {
        "user_id_hash",
        "display_name",
        "platform_handle",
        "pseudonym",
        "operator_label",
        "identity_scope",
    } <= actor_schema["properties"].keys()
    unknown_field = client.post(
        "/api/v1/workspaces",
        json={"project_name": "Wallet Project", "remote_upload": True},
    )
    assert unknown_field.status_code == 422
    workspace = client.post("/api/v1/workspaces", json={"project_name": "Wallet Project"}).json()

    unsupported = client.post(
        f"/api/v1/workspaces/{workspace['workspace_id']}/communities",
        json={"name": "Arabic", "language": "ar", "timezone": "UTC"},
    )
    assert unsupported.status_code == 422
    assert "EN, CN, and ES" in unsupported.json()["detail"]

    missing = client.get("/api/v1/analysis-runs/run_missing")
    assert missing.status_code == 404


def test_v1_failed_background_analysis_remains_pollable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(create_app(data_root=tmp_path / "app-data"))
    workspace = client.post("/api/v1/workspaces", json={"project_name": "Wallet Project"}).json()
    community = client.post(
        f"/api/v1/workspaces/{workspace['workspace_id']}/communities",
        json={"name": "中文", "language": "zh", "timezone": "UTC"},
    ).json()
    client.post(
        f"/api/v1/communities/{community['community_id']}/imports/telegram",
        files={"file": ("result.json", telegram_bytes(), "application/json")},
    )

    def fail_pipeline(*_args: object, **_kwargs: object) -> None:
        raise OSError("synthetic pipeline failure")

    monkeypatch.setattr(
        "community_intelligence.application.data_foundation.run_pipeline",
        fail_pipeline,
    )
    queued = client.post(
        f"/api/v1/workspaces/{workspace['workspace_id']}/analysis-runs",
        json={
            "window": "custom",
            "start": "2026-09-10T00:00:00Z",
            "end": "2026-09-11T00:00:00Z",
        },
    )
    assert queued.status_code == 202
    run = client.get(f"/api/v1/analysis-runs/{queued.json()['analysis_run_id']}")
    assert run.json()["status"] == "failed"
    assert run.json()["report_path"] is None
    assert run.json()["error"] == "synthetic pipeline failure"

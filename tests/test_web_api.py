from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from community_intelligence.web.app import create_app


def _telegram_export_bytes() -> bytes:
    export = {
        "name": "Imported Community",
        "type": "private_supergroup",
        "id": 987654321,
        "messages": [
            {
                "id": 10,
                "type": "message",
                "date": "2026-08-31T16:00:00+00:00",
                "from": "Alice Raw Name",
                "from_id": "user123456",
                "text": "Can someone help with the launch?",
            },
            {
                "id": 11,
                "type": "message",
                "date": "2026-08-31T16:03:00+00:00",
                "from": "Bob Raw Name",
                "from_id": "user999999",
                "reply_to_message_id": 10,
                "text": "Here is a helpful reply",
            },
        ],
    }
    return json.dumps(export).encode()


def test_health_and_built_frontend_are_available(tmp_path: Path) -> None:
    client = TestClient(create_app(data_root=tmp_path / "private-data"))

    health = client.get("/api/health")
    homepage = client.get("/")

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": "0.1.0a0"}
    assert homepage.status_code == 200
    assert "Community Intelligence" in homepage.text


def test_demo_creates_a_report_and_joinable_evidence(tmp_path: Path) -> None:
    data_root = tmp_path / "private-data"
    client = TestClient(create_app(data_root=data_root))

    response = client.post(
        "/api/analyses/demo",
        json={"seed": 20260901, "message_count": 120},
    )

    assert response.status_code == 201
    payload = response.json()
    assert len(payload["analysis_id"]) == 32
    assert payload["summary"]["message_count"] == 120
    assert payload["report"]["data_status"] == "synthetic"
    assert payload["report"]["Overview"]["community_count"] == 4
    assert data_root.stat().st_mode & 0o777 == 0o700

    report = client.get(f'/api/analyses/{payload["analysis_id"]}')
    evidence = client.get(f'/api/analyses/{payload["analysis_id"]}/evidence')
    assert report.status_code == 200
    assert report.json()["generation_id"] == payload["report"]["generation_id"]
    assert evidence.status_code == 200
    assert evidence.json()["count"] > 0
    assert evidence.json()["items"][0]["evidence_id"].startswith("evidence_")


def test_telegram_upload_runs_the_community_only_analysis(tmp_path: Path) -> None:
    client = TestClient(create_app(data_root=tmp_path / "private-data"))

    response = client.post(
        "/api/analyses/telegram",
        files={"file": ("result.json", _telegram_export_bytes(), "application/json")},
        data={"language": "en"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["summary"]["message_count"] == 2
    assert payload["report"]["data_status"] == "production"
    assert payload["report"]["Overview"]["source"]["format"] == (
        "telegram_desktop_json_v0.1"
    )
    assert payload["report"]["capabilities"]["campaign_intelligence"]["status"] == (
        "not_available"
    )

    published = "".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "private-data").rglob("*")
        if path.is_file()
    )
    assert "user123456" not in published
    assert "Alice Raw Name" not in published


def test_upload_boundary_and_unknown_analysis_are_concise(tmp_path: Path) -> None:
    client = TestClient(create_app(data_root=tmp_path / "private-data", max_upload_bytes=64))

    wrong_type = client.post(
        "/api/analyses/telegram",
        files={"file": ("messages.txt", b"{}", "text/plain")},
    )
    oversized = client.post(
        "/api/analyses/telegram",
        files={"file": ("result.json", b"{" + b"x" * 128, "application/json")},
    )
    missing = client.get("/api/analyses/00000000000000000000000000000000")

    assert wrong_type.status_code == 415
    assert wrong_type.json() == {"detail": "Upload a Telegram Desktop JSON export."}
    assert oversized.status_code == 413
    assert oversized.json() == {"detail": "Upload exceeds the 64-byte local limit."}
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Analysis not found."}

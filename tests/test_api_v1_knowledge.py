from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from community_intelligence.web.app import create_app


def valid_metadata(
    content: str = "# Wallet\n\nThe wallet supports offline recovery phrases.",
) -> dict[str, object]:
    return {
        "title": "Wallet Docs",
        "source_type": "product_docs",
        "source_channel": "docs",
        "content": content,
        "canonical_url": "https://example.org/docs/wallet",
        "language": "en",
        "project_scope": "wallet",
        "authority_level": "official",
        "official_status": "verified_official",
        "verification_method": "human-confirmed official domain",
        "published_at": "2026-01-01T09:00:00Z",
        "effective_from": "2026-01-01T09:00:00Z",
        "source_timezone": "UTC",
        "metadata_provenance": {
            "source_type": "human-confirmed",
            "authority_level": "human-confirmed",
            "official_status": "human-confirmed",
            "published_at": "source-provided",
            "validity": "human-confirmed",
        },
    }


def test_knowledge_api_adds_manual_and_file_sources_then_opens_citation(tmp_path: Path) -> None:
    client = TestClient(create_app(data_root=tmp_path / "app-data", internal_review=True))
    workspace = client.post("/api/v1/workspaces", json={"project_name": "Web3"}).json()
    workspace_id = workspace["workspace_id"]

    manual = client.post(
        f"/api/v1/workspaces/{workspace_id}/knowledge-sources/manual",
        json=valid_metadata(),
    )
    assert manual.status_code == 201, manual.text
    source_id = manual.json()["source_id"]
    revision_payload = valid_metadata("# Wallet\n\nRecovery stays offline in version two.")
    revised = client.post(
        f"/api/v1/knowledge-sources/{source_id}/revisions/manual",
        json=revision_payload,
    )
    assert revised.status_code == 201, revised.text
    assert revised.json()["version"] == 2

    file_metadata = valid_metadata("unused")
    file_metadata.pop("content")
    file_metadata["title"] = "Official FAQ"
    file_metadata["source_type"] = "faq"
    uploaded = client.post(
        f"/api/v1/workspaces/{workspace_id}/knowledge-sources/files",
        data={"metadata_json": json.dumps(file_metadata)},
        files={
            "file": (
                "faq.md",
                b"# FAQ\n\nQ: Is recovery offline?\n\nA: Yes, it is offline.",
                "text/markdown",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text

    listed = client.get(f"/api/v1/workspaces/{workspace_id}/knowledge-sources")
    assert listed.json()["count"] == 2
    detail = client.get(f"/api/v1/knowledge-sources/{source_id}")
    assert detail.status_code == 200
    assert detail.json()["metadata_provenance"]["authority_level"] == "human-confirmed"

    result = client.post(
        f"/api/v1/workspaces/{workspace_id}/knowledge-query",
        json={"query": "Is recovery offline?"},
    )
    assert result.status_code == 200
    assert result.json()["answer_status"] == "insufficient_evidence"
    assert result.json()["answerability"]["status"] == "unavailable"
    citation = result.json()["citations"][0]
    chunk = client.get(f"/api/v1/knowledge-chunks/{citation['chunk_id']}")
    assert chunk.status_code == 200
    assert chunk.json()["revision_id"] == citation["revision_id"]
    reindexed = client.post(f"/api/v1/knowledge-revisions/{citation['revision_id']}/reindex")
    assert reindexed.status_code == 200
    assert reindexed.json()["reindexed"] is False
    assert client.post("/api/v1/knowledge-revisions/missing/reindex").status_code == 404

    review = client.get("/internal/knowledge-review")
    assert review.status_code == 200


def test_knowledge_file_api_rejects_scanned_pdf_and_unknown_format(tmp_path: Path) -> None:
    client = TestClient(create_app(data_root=tmp_path / "app-data"))
    workspace_id = client.post("/api/v1/workspaces", json={"project_name": "Web3"}).json()[
        "workspace_id"
    ]
    fields = valid_metadata("unused")
    fields.pop("content")
    unsupported = client.post(
        f"/api/v1/workspaces/{workspace_id}/knowledge-sources/files",
        data={"metadata_json": json.dumps(fields)},
        files={"file": ("source.html", b"<p>data</p>", "text/html")},
    )
    assert unsupported.status_code == 415


def text_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Official bridge finality is eight blocks.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(output)
    return output.getvalue()


def test_text_pdf_is_ingested_but_scanned_pdf_is_explicitly_unavailable(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(data_root=tmp_path / "app-data"))
    workspace_id = client.post("/api/v1/workspaces", json={"project_name": "Web3"}).json()[
        "workspace_id"
    ]
    fields = valid_metadata("unused")
    fields.pop("content")
    extracted = client.post(
        f"/api/v1/workspaces/{workspace_id}/knowledge-sources/files",
        data={"metadata_json": json.dumps(fields)},
        files={"file": ("docs.pdf", text_pdf(), "application/pdf")},
    )
    assert extracted.status_code == 201, extracted.text
    assert extracted.json()["chunks"][0]["page"] == 1

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    blank = BytesIO()
    writer.write(blank)
    scanned = client.post(
        f"/api/v1/workspaces/{workspace_id}/knowledge-sources/files",
        data={"metadata_json": json.dumps({**fields, "title": "Scanned"})},
        files={"file": ("scan.pdf", blank.getvalue(), "application/pdf")},
    )
    assert scanned.status_code == 422
    assert "OCR is unavailable" in scanned.json()["detail"]
    listed = client.get(f"/api/v1/workspaces/{workspace_id}/knowledge-sources").json()
    assert listed["count"] == 1

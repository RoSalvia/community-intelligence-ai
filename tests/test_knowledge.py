from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import func, select

from community_intelligence.application.data_foundation import DataFoundationService
from community_intelligence.application.knowledge import KnowledgeService, SourceInput
from community_intelligence.infrastructure.database import knowledge_embeddings

NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)


@pytest.fixture
def knowledge(tmp_path: Path) -> tuple[KnowledgeService, str]:
    foundation = DataFoundationService(
        database_path=tmp_path / "app.sqlite3",
        artifact_root=tmp_path / "runs",
        clock=lambda: NOW,
    )
    workspace_id = foundation.create_workspace("Generic Web3 Project")["workspace_id"]
    return (
        KnowledgeService(
            database=foundation.database,
            artifact_root=tmp_path / "knowledge",
            clock=lambda: NOW,
        ),
        workspace_id,
    )


def source(**overrides: object) -> SourceInput:
    values = {
        "title": "Wallet FAQ",
        "source_type": "faq",
        "source_channel": "docs",
        "content": "# Wallet\n\nQ: How do I recover access?\nA: Use the recovery phrase offline.",
        "canonical_url": "https://example.org/faq/wallet",
        "language": "en",
        "project_scope": "wallet",
        "authority_level": "official",
        "official_status": "verified_official",
        "verification_method": "human-confirmed official domain",
        "published_at": datetime(2026, 1, 1, 9, tzinfo=UTC),
        "effective_from": datetime(2026, 1, 1, 9, tzinfo=UTC),
        "source_timezone": "UTC",
        "metadata_provenance": {
            "source_type": "human-confirmed",
            "authority_level": "human-confirmed",
            "official_status": "human-confirmed",
            "published_at": "source-provided",
            "validity": "human-confirmed",
        },
    }
    values.update(overrides)
    return SourceInput(**values)  # type: ignore[arg-type]


def test_manual_source_is_versioned_idempotent_and_chunk_provenance_is_openable(
    knowledge: tuple[KnowledgeService, str],
) -> None:
    service, workspace_id = knowledge
    first = service.add_source(workspace_id, source())
    duplicate = service.add_revision(first["source_id"], source())
    changed = service.add_revision(
        first["source_id"],
        source(content="# Wallet\n\nQ: Recovery?\nA: Use the recovery phrase offline."),
    )

    assert duplicate["revision_id"] == first["revision_id"]
    assert duplicate["duplicate"] is True
    assert changed["version"] == 2
    assert changed["revision_id"] != first["revision_id"]
    detail = service.get_source(first["source_id"])
    assert len(detail["revisions"]) == 2
    assert detail["revisions"][1]["status"] == "superseded"
    assert detail["revisions"][1]["superseded_by_revision_id"] == changed["revision_id"]
    assert detail["metadata_provenance"]["authority_level"] == "human-confirmed"
    chunk = service.get_chunk(changed["chunks"][0]["chunk_id"])
    assert chunk["source_id"] == first["source_id"]
    assert chunk["revision_id"] == changed["revision_id"]
    assert chunk["section"] == "Wallet"


def test_as_of_time_returns_historical_then_current_and_outdated_only(
    knowledge: tuple[KnowledgeService, str],
) -> None:
    service, workspace_id = knowledge
    old = service.add_source(
        workspace_id,
        source(
            title="Old limits",
            content="# Withdrawal limit\n\nThe daily withdrawal limit is 10 tokens.",
            effective_from=datetime(2025, 1, 1, tzinfo=UTC),
            effective_until=datetime(2026, 6, 1, tzinfo=UTC),
            published_at=datetime(2025, 1, 1, tzinfo=UTC),
            status="historical",
        ),
    )
    current = service.add_source(
        workspace_id,
        source(
            title="Current limits",
            content="# Withdrawal limit\n\nThe daily withdrawal limit is 20 tokens.",
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            published_at=datetime(2026, 6, 1, tzinfo=UTC),
        ),
    )

    historical = service.query(
        workspace_id,
        "daily withdrawal limit tokens",
        as_of_time=datetime(2026, 3, 1, tzinfo=UTC),
    )
    present = service.query(workspace_id, "daily withdrawal limit tokens")
    before_any = service.query(
        workspace_id,
        "daily withdrawal limit tokens",
        as_of_time=datetime(2024, 1, 1, tzinfo=UTC),
    )

    assert historical["answer_status"] == "insufficient_evidence"
    assert historical["answerability"]["status"] == "unavailable"
    assert historical["citations"][0]["source_id"] == old["source_id"]
    assert present["answer_status"] == "insufficient_evidence"
    assert present["citations"][0]["source_id"] == current["source_id"]
    assert before_any["answer_status"] == "no_authoritative_source"


def test_conflict_insufficient_and_no_source_are_distinct(
    knowledge: tuple[KnowledgeService, str],
) -> None:
    service, workspace_id = knowledge
    service.add_source(
        workspace_id,
        source(
            title="Announcement A",
            source_type="official_announcement",
            source_channel="telegram_announcement",
            content="# Maintenance\n\nMaintenance starts at 10:00 UTC.",
            semantic_tags={"fact_key": "maintenance_start", "fact_value": "10:00 UTC"},
        ),
    )
    service.add_source(
        workspace_id,
        source(
            title="Announcement B",
            source_type="maintenance_notice",
            source_channel="website",
            content="# Maintenance\n\nMaintenance starts at 11:00 UTC.",
            semantic_tags={"fact_key": "maintenance_start", "fact_value": "11:00 UTC"},
        ),
    )
    service.add_source(
        workspace_id,
        source(
            title="Staking overview",
            content="# Staking\n\nStaking is available in the application.",
        ),
    )

    conflict = service.query(workspace_id, "When does maintenance start?")
    insufficient = service.query(workspace_id, "What is the staking reward percentage?")
    absent = service.query(workspace_id, "Who painted the Mona Lisa?")

    # Semantic tags are not an independent fact judge; explicit LLM assessment is required.
    assert conflict["answer_status"] == "insufficient_evidence"
    assert conflict["answerability"]["status"] == "unavailable"
    assert len(conflict["citations"]) == 2
    assert insufficient["answer_status"] == "insufficient_evidence"
    assert absent["answer_status"] == "no_authoritative_source"


def test_naive_metadata_time_and_ai_inferred_authority_are_rejected(
    knowledge: tuple[KnowledgeService, str],
) -> None:
    service, workspace_id = knowledge
    with pytest.raises(ValueError, match="timezone-aware"):
        service.add_source(
            workspace_id,
            source(published_at=datetime(2026, 1, 1)),
        )
    with pytest.raises(ValueError, match="AI-inferred"):
        service.add_source(
            workspace_id,
            source(
                metadata_provenance={
                    "source_type": "human-confirmed",
                    "authority_level": "ai-inferred",
                    "official_status": "human-confirmed",
                    "published_at": "source-provided",
                    "validity": "human-confirmed",
                }
            ),
        )
    with pytest.raises(ValueError, match="http or https"):
        service.add_source(
            workspace_id,
            source(canonical_url="javascript:alert(1)"),
        )


def test_incremental_embedding_indexes_only_new_content(tmp_path: Path) -> None:
    class Embedder:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def embed(self, texts: list[str]) -> np.ndarray:
            self.calls.append(texts)
            return np.asarray([[1.0, 0.0] for _ in texts])

    foundation = DataFoundationService(
        database_path=tmp_path / "app.sqlite3",
        artifact_root=tmp_path / "runs",
        clock=lambda: NOW,
    )
    workspace_id = foundation.create_workspace("Web3")["workspace_id"]
    embedder = Embedder()
    service = KnowledgeService(
        database=foundation.database,
        artifact_root=tmp_path / "knowledge",
        clock=lambda: NOW,
        embedder=embedder,
    )
    first = service.add_source(workspace_id, source())
    service.add_revision(first["source_id"], source())
    service.add_source(workspace_id, source(title="Same content, another channel"))
    service.add_revision(
        first["source_id"],
        source(content="# Wallet\n\nA genuinely new official recovery procedure."),
    )

    assert len(embedder.calls) == 3
    with foundation.database.engine.connect() as connection:
        count = connection.scalar(select(func.count()).select_from(knowledge_embeddings))
    assert count == 3

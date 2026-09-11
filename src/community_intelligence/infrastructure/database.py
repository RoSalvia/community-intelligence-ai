"""Versioned SQLite schema for the local-first v2.1 data foundation."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    insert,
    select,
    text,
)

SCHEMA_VERSION = 3
metadata = MetaData()

schema_migrations = Table(
    "schema_migrations",
    metadata,
    Column("version", Integer, primary_key=True),
    Column("applied_at", String, nullable=False),
)

workspaces = Table(
    "workspaces",
    metadata,
    Column("workspace_id", String, primary_key=True),
    Column("project_name", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("settings_version", Integer, nullable=False, default=1),
    Column("hash_salt", String, nullable=False),
)

communities = Table(
    "communities",
    metadata,
    Column("community_id", String, primary_key=True),
    Column("workspace_id", ForeignKey("workspaces.workspace_id"), nullable=False),
    Column("name", String, nullable=False),
    Column("language", String, nullable=False),
    Column("platform", String, nullable=False, default="telegram"),
    Column("timezone", String, nullable=False),
    Column("active", Integer, nullable=False, default=1),
    UniqueConstraint("workspace_id", "language", name="uq_community_workspace_language"),
    CheckConstraint("language IN ('en', 'zh', 'es')", name="ck_community_mvp_language"),
)

sync_batches = Table(
    "sync_batches",
    metadata,
    Column("source_batch_id", String, primary_key=True),
    Column("community_id", ForeignKey("communities.community_id"), nullable=False),
    Column("source_type", String, nullable=False),
    Column("window_start", String, nullable=False),
    Column("window_end", String, nullable=False),
    Column("imported_at", String, nullable=False),
    Column("content_hash", String, nullable=False),
    Column("status", String, nullable=False),
    Column("error", Text),
    Column("message_count", Integer, nullable=False),
    UniqueConstraint("community_id", "content_hash", name="uq_batch_community_content"),
)

messages = Table(
    "messages",
    metadata,
    Column("message_id", String, primary_key=True),
    Column("community_id", ForeignKey("communities.community_id"), nullable=False),
    Column("language", String, nullable=False),
    Column("user_id_hash", String, nullable=False),
    Column("user_role", String, nullable=False, default="user"),
    Column("timestamp", String, nullable=False),
    Column("original_text", Text, nullable=False),
    Column("reply_to_message_id", ForeignKey("messages.message_id")),
    Column("reply_to_source_key", String),
    Column("source_batch_id", ForeignKey("sync_batches.source_batch_id"), nullable=False),
    CheckConstraint("user_role IN ('moderator', 'user', 'bot')", name="ck_message_role"),
)

actor_identities = Table(
    "actor_identities",
    metadata,
    Column("user_id_hash", String, primary_key=True),
    Column("workspace_id", ForeignKey("workspaces.workspace_id"), nullable=False),
    Column("community_id", ForeignKey("communities.community_id"), nullable=False),
    Column("display_name", Text),
    Column("platform_handle", Text),
    Column("pseudonym", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

role_assignments = Table(
    "role_assignments",
    metadata,
    Column("role_assignment_id", String, primary_key=True),
    Column("workspace_id", ForeignKey("workspaces.workspace_id"), nullable=False),
    Column("user_id_hash", String, nullable=False),
    Column("role", String, nullable=False),
    Column("valid_from", String, nullable=False),
    Column("valid_to", String),
    Column("source", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", String, nullable=False),
    UniqueConstraint("workspace_id", "user_id_hash", "version", name="uq_role_assignment_version"),
    CheckConstraint("role IN ('moderator', 'user', 'bot')", name="ck_assignment_role"),
)

analysis_runs = Table(
    "analysis_runs",
    metadata,
    Column("analysis_run_id", String, primary_key=True),
    Column("workspace_id", ForeignKey("workspaces.workspace_id"), nullable=False),
    Column("window_kind", String, nullable=False),
    Column("window_start", String, nullable=False),
    Column("window_end", String, nullable=False),
    Column("baseline_start", String, nullable=False),
    Column("baseline_end", String, nullable=False),
    Column("fallback_used", Integer, nullable=False),
    Column("activity_status", String, nullable=False),
    Column("status", String, nullable=False),
    Column("progress", Integer, nullable=False),
    Column("input_fingerprint", String, nullable=False),
    Column("methods_json", Text, nullable=False),
    Column("created_at", String, nullable=False),
    Column("started_at", String),
    Column("finished_at", String),
    Column("report_path", Text),
    Column("error", Text),
    CheckConstraint(
        "status IN ('queued', 'running', 'succeeded', 'failed')",
        name="ck_analysis_run_status",
    ),
    CheckConstraint(
        "activity_status IN ('new_activity', 'no_new_activity')",
        name="ck_analysis_run_activity",
    ),
    CheckConstraint("progress BETWEEN 0 AND 100", name="ck_analysis_run_progress"),
)

user_check_watermarks = Table(
    "user_check_watermarks",
    metadata,
    Column("workspace_id", ForeignKey("workspaces.workspace_id"), primary_key=True),
    Column("checked_through", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

knowledge_sources = Table(
    "knowledge_sources",
    metadata,
    Column("source_id", String, primary_key=True),
    Column("workspace_id", ForeignKey("workspaces.workspace_id"), nullable=False),
    Column("title", Text, nullable=False),
    Column("source_type", String, nullable=False),
    Column("source_channel", String, nullable=False),
    Column("canonical_url", Text),
    Column("platform", String),
    Column("platform_content_id", String),
    Column("author", Text),
    Column("language", String, nullable=False),
    Column("project_scope", Text, nullable=False),
    Column("authority_level", String, nullable=False),
    Column("official_status", String, nullable=False),
    Column("source_owner", Text),
    Column("verification_method", Text, nullable=False),
    Column("metadata_provenance_json", Text, nullable=False),
    Column("semantic_tags_json", Text, nullable=False, default="{}"),
    Column("created_at", String, nullable=False),
)

knowledge_revisions = Table(
    "knowledge_revisions",
    metadata,
    Column("revision_id", String, primary_key=True),
    Column("source_id", ForeignKey("knowledge_sources.source_id"), nullable=False),
    Column("version", Integer, nullable=False),
    Column("content_hash", String, nullable=False),
    Column("artifact_path", Text, nullable=False),
    Column("status", String, nullable=False),
    Column("published_on", String),
    Column("published_at", String),
    Column("temporal_precision", String, nullable=False),
    Column("updated_at", String),
    Column("effective_from", String),
    Column("effective_until", String),
    Column("ingested_at", String, nullable=False),
    Column("observed_at", String, nullable=False),
    Column("superseded_at", String),
    Column("source_timezone", String, nullable=False),
    Column("revision_metadata_provenance_json", Text, nullable=False),
    Column("revision_semantic_tags_json", Text, nullable=False, default="{}"),
    Column("supersedes_source_id", String),
    Column("supersedes_revision_id", String),
    Column("superseded_by_source_id", String),
    Column("superseded_by_revision_id", String),
    Column("parser_version", String, nullable=False),
    Column("chunk_strategy", String, nullable=False),
    Column("chunk_strategy_version", String, nullable=False),
    Column("embedding_model", String),
    Column("embedding_revision", String),
    Column("index_version", String, nullable=False),
    Column("parse_status", String, nullable=False),
    Column("index_status", String, nullable=False),
    Column("error", Text),
    UniqueConstraint("source_id", "version", name="uq_knowledge_source_version"),
    UniqueConstraint("source_id", "content_hash", name="uq_knowledge_source_content"),
)

knowledge_chunks = Table(
    "knowledge_chunks",
    metadata,
    Column("chunk_id", String, primary_key=True),
    Column("source_id", ForeignKey("knowledge_sources.source_id"), nullable=False),
    Column("revision_id", ForeignKey("knowledge_revisions.revision_id"), nullable=False),
    Column("section", Text),
    Column("parent_heading", Text),
    Column("page", Integer),
    Column("ordinal", Integer, nullable=False),
    Column("language", String, nullable=False),
    Column("token_count", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("validity", String, nullable=False),
    Column("authority", String, nullable=False),
    UniqueConstraint("revision_id", "ordinal", name="uq_knowledge_revision_ordinal"),
)

knowledge_embeddings = Table(
    "knowledge_embeddings",
    metadata,
    Column("content_hash", String, primary_key=True),
    Column("model", String, primary_key=True),
    Column("revision", String, primary_key=True),
    Column("vector_json", Text, nullable=False),
)


class Database:
    """Own a bounded SQLite database and apply the packaged schema version."""

    def __init__(self, path: str | Path) -> None:
        lexical_path = Path(os.path.abspath(Path(path).expanduser()))
        lexical_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.path.lexists(lexical_path) and lexical_path.is_symlink():
            raise ValueError("database path must not be a symbolic link")
        self.path = lexical_path
        self.engine = create_engine(
            f"sqlite:///{lexical_path}",
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", self._configure_sqlite)

    @staticmethod
    def _configure_sqlite(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    def migrate(self, *, applied_at: str) -> None:
        metadata.create_all(self.engine)
        with self.engine.connect() as connection:
            current = connection.scalar(select(schema_migrations.c.version).limit(1))
        if current in {1, 2}:
            self._migrate_temporal_precision_from_v2(applied_at=applied_at)
            current = SCHEMA_VERSION
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts
                    USING fts5(chunk_id UNINDEXED, text, tokenize='unicode61')
                    """
                )
            )
            connection.execute(text("DROP TRIGGER IF EXISTS messages_immutable_before_update"))
            connection.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS messages_immutable_before_update
                    BEFORE UPDATE OF community_id, language, user_id_hash, user_role,
                        timestamp, original_text, source_batch_id ON messages
                    BEGIN
                        SELECT RAISE(ABORT, 'source messages are immutable');
                    END
                    """
                )
            )
            if current is None:
                connection.execute(
                    insert(schema_migrations).values(
                        version=SCHEMA_VERSION,
                        applied_at=applied_at,
                    )
                )
            elif current != SCHEMA_VERSION:
                raise RuntimeError(
                    f"database schema {current} is incompatible with {SCHEMA_VERSION}"
                )

    def _migrate_temporal_precision_from_v2(self, *, applied_at: str) -> None:
        """Rebuild the revision table so date-only publication and null validity stay honest."""

        raw_connection = self.engine.raw_connection()
        cursor = raw_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                """
                CREATE TABLE knowledge_revisions_v3 (
                    revision_id VARCHAR NOT NULL PRIMARY KEY,
                    source_id VARCHAR NOT NULL REFERENCES knowledge_sources (source_id),
                    version INTEGER NOT NULL,
                    content_hash VARCHAR NOT NULL,
                    artifact_path TEXT NOT NULL,
                    status VARCHAR NOT NULL,
                    published_on VARCHAR,
                    published_at VARCHAR,
                    temporal_precision VARCHAR NOT NULL,
                    updated_at VARCHAR,
                    effective_from VARCHAR,
                    effective_until VARCHAR,
                    ingested_at VARCHAR NOT NULL,
                    observed_at VARCHAR NOT NULL,
                    superseded_at VARCHAR,
                    source_timezone VARCHAR NOT NULL,
                    revision_metadata_provenance_json TEXT NOT NULL,
                    revision_semantic_tags_json TEXT NOT NULL DEFAULT '{}',
                    supersedes_source_id VARCHAR,
                    supersedes_revision_id VARCHAR,
                    superseded_by_source_id VARCHAR,
                    superseded_by_revision_id VARCHAR,
                    parser_version VARCHAR NOT NULL,
                    chunk_strategy VARCHAR NOT NULL,
                    chunk_strategy_version VARCHAR NOT NULL,
                    embedding_model VARCHAR,
                    embedding_revision VARCHAR,
                    index_version VARCHAR NOT NULL,
                    parse_status VARCHAR NOT NULL,
                    index_status VARCHAR NOT NULL,
                    error TEXT,
                    CONSTRAINT uq_knowledge_source_version UNIQUE (source_id, version),
                    CONSTRAINT uq_knowledge_source_content UNIQUE (source_id, content_hash)
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO knowledge_revisions_v3 (
                    revision_id, source_id, version, content_hash, artifact_path, status,
                    published_on, published_at, temporal_precision, updated_at,
                    effective_from, effective_until, ingested_at, observed_at, superseded_at,
                    source_timezone, revision_metadata_provenance_json,
                    revision_semantic_tags_json, supersedes_source_id, supersedes_revision_id,
                    superseded_by_source_id, superseded_by_revision_id, parser_version,
                    chunk_strategy, chunk_strategy_version, embedding_model, embedding_revision,
                    index_version, parse_status, index_status, error
                )
                SELECT
                    revision_id, source_id, version, content_hash, artifact_path, status,
                    NULL, published_at, 'second', updated_at,
                    effective_from, effective_until, ingested_at, observed_at, superseded_at,
                    source_timezone, revision_metadata_provenance_json,
                    revision_semantic_tags_json, supersedes_source_id, supersedes_revision_id,
                    superseded_by_source_id, superseded_by_revision_id, parser_version,
                    chunk_strategy, chunk_strategy_version, embedding_model, embedding_revision,
                    index_version, parse_status, index_status, error
                FROM knowledge_revisions
                """
            )
            cursor.execute("DROP TABLE knowledge_revisions")
            cursor.execute("ALTER TABLE knowledge_revisions_v3 RENAME TO knowledge_revisions")
            cursor.execute(
                "UPDATE schema_migrations SET version=?, applied_at=?",
                (SCHEMA_VERSION, applied_at),
            )
            raw_connection.commit()
        except BaseException:
            raw_connection.rollback()
            raise
        finally:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
            raw_connection.close()

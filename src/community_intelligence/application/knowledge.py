"""M2 Project Knowledge ingestion, versioning, retrieval, and citation service."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
from sqlalchemy import delete, func, insert, select, text, update

from community_intelligence.application.knowledge_answer import (
    MAX_EVIDENCE_CHARS,
    JsonAnswerProvider,
    assess_answer,
)
from community_intelligence.infrastructure.database import (
    Database,
    knowledge_chunks,
    knowledge_embeddings,
    knowledge_revisions,
    knowledge_sources,
    workspaces,
)
from community_intelligence.semantic import (
    MODEL_ID,
    MODEL_REVISION,
    SentenceTransformerProvider,
)

SOURCE_TYPES = {
    "whitepaper",
    "product_docs",
    "faq",
    "official_announcement",
    "official_blog",
    "release_notes",
    "changelog",
    "governance_proposal",
    "maintenance_notice",
    "campaign_rules",
    "community_rules",
    "manual_official_note",
}
SOURCE_CHANNELS = {
    "docs",
    "website",
    "medium",
    "x",
    "telegram_announcement",
    "github",
    "governance",
    "manual",
}
SOURCE_STATUSES = {"current", "superseded", "expired", "historical", "draft", "unknown"}
PROVENANCE_VALUES = {
    "source-provided",
    "human-confirmed",
    "system-derived",
    "ai-inferred",
}
CRITICAL_METADATA = {
    "source_type",
    "authority_level",
    "official_status",
    "published_at",
    "validity",
}
PARSER_VERSION = "plain-text-and-pdf-v1"
CHUNK_STRATEGY = "structure-aware"
CHUNK_STRATEGY_VERSION = "structure-v1"
INDEX_VERSION = "sqlite-fts5-rrf-structure-v2"
AUTHORITY_POLICY_VERSION = "authority-validity-rrf-v4"
CANDIDATE_SELECTION_VERSION = "majority-one-slot-v1"
REPRESENTATION_VERSION = "title-heading-body-v1"
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_QUESTION = re.compile(
    r"^(?:Q(?:uestion)?|P(?:regunta)?)\s*[:：]|^[^.!?。！？]{2,120}[?？]",
    re.I,
)
_WORD = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)
_STOP = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "do",
    "does",
    "for",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "cuál",
    "cómo",
    "de",
    "el",
    "en",
    "es",
    "la",
    "los",
    "que",
    "qué",
    "un",
    "una",
}


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("all knowledge timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _terms(value: str) -> list[str]:
    words = [word.casefold() for word in _WORD.findall(value)]
    result = [
        word[:-1] if word.isascii() and len(word) > 4 and word.endswith("s") else word
        for word in words
        if len(word) > 1 and word not in _STOP
    ]
    for run in re.findall(r"[\u3400-\u9fff]{2,}", value):
        result.extend(run[index : index + 2] for index in range(len(run) - 1))
    return list(dict.fromkeys(result))


@dataclass(frozen=True)
class ChunkConfig:
    max_tokens: int = 180
    overlap_tokens: int = 30


@dataclass(frozen=True)
class SourceInput:
    title: str
    source_type: str
    source_channel: str
    content: str | bytes
    published_at: datetime
    effective_from: datetime
    source_timezone: str
    canonical_url: str | None = None
    platform: str | None = None
    platform_content_id: str | None = None
    author: str | None = None
    language: str = "en"
    project_scope: str = "project"
    authority_level: str = "official"
    official_status: str = "verified_official"
    source_owner: str | None = None
    verification_method: str = "human-confirmed"
    updated_at: datetime | None = None
    effective_until: datetime | None = None
    observed_at: datetime | None = None
    superseded_at: datetime | None = None
    status: str = "current"
    supersedes_source_id: str | None = None
    supersedes_revision_id: str | None = None
    metadata_provenance: dict[str, str] = field(default_factory=dict)
    semantic_tags: dict[str, str] = field(default_factory=dict)
    filename: str | None = None


class KnowledgeService:
    """A local, framework-agnostic knowledge application service."""

    def __init__(
        self,
        *,
        database: Database,
        artifact_root: str | Path,
        clock: Callable[[], datetime] = _now,
        embedder: Any | None = None,
        chunk_config: ChunkConfig | None = None,
        answerer: Any | None = None,
    ) -> None:
        self.database = database
        self.clock = clock
        self.chunk_config = chunk_config or ChunkConfig()
        self.artifact_root = Path(artifact_root).expanduser().resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.artifact_root.chmod(0o700)
        self.embedder = embedder if embedder is not None else self._configured_embedder()
        self.answerer = answerer if answerer is not None else JsonAnswerProvider.configured()

    @staticmethod
    def _configured_embedder() -> Any | None:
        model_dir = os.environ.get("COMMUNITY_INTELLIGENCE_SEMANTIC_MODEL_DIR")
        return SentenceTransformerProvider(model_dir) if model_dir else None

    def _validate(self, source: SourceInput) -> None:
        if source.source_type not in SOURCE_TYPES:
            raise ValueError("unsupported source_type")
        if source.source_channel not in SOURCE_CHANNELS:
            raise ValueError("unsupported source_channel")
        if source.status not in SOURCE_STATUSES:
            raise ValueError("unsupported knowledge status")
        if not source.title.strip() or not source.content.strip():
            raise ValueError("title and content must not be empty")
        if source.source_channel != "manual" and not source.canonical_url:
            raise ValueError("canonical_url is required for a published source channel")
        if source.canonical_url and urlparse(source.canonical_url).scheme not in {"http", "https"}:
            raise ValueError("canonical_url must use http or https")
        for value in (
            source.published_at,
            source.updated_at,
            source.effective_from,
            source.effective_until,
            source.observed_at,
            source.superseded_at,
        ):
            _iso(value)
        if source.effective_until and source.effective_until <= source.effective_from:
            raise ValueError("effective_until must be after effective_from")
        missing = CRITICAL_METADATA - source.metadata_provenance.keys()
        if missing:
            raise ValueError(f"metadata provenance missing: {', '.join(sorted(missing))}")
        if any(value not in PROVENANCE_VALUES for value in source.metadata_provenance.values()):
            raise ValueError("unsupported metadata provenance")
        protected = {
            "authority_level",
            "official_status",
            "validity",
            "published_at",
            "source_type",
        }
        if any(source.metadata_provenance.get(key) == "ai-inferred" for key in protected):
            raise ValueError("AI-inferred critical metadata requires human confirmation")

    def add_source(self, workspace_id: str, source: SourceInput) -> dict[str, Any]:
        self._validate(source)
        with self.database.engine.connect() as connection:
            if not connection.scalar(
                select(func.count())
                .select_from(workspaces)
                .where(workspaces.c.workspace_id == workspace_id)
            ):
                raise KeyError(workspace_id)
        source_id = _id("ks")
        created_at = _iso(self.clock())
        with self.database.engine.begin() as connection:
            connection.execute(
                insert(knowledge_sources).values(
                    source_id=source_id,
                    workspace_id=workspace_id,
                    title=source.title.strip(),
                    source_type=source.source_type,
                    source_channel=source.source_channel,
                    canonical_url=source.canonical_url,
                    platform=source.platform,
                    platform_content_id=source.platform_content_id,
                    author=source.author,
                    language=source.language,
                    project_scope=source.project_scope,
                    authority_level=source.authority_level,
                    official_status=source.official_status,
                    source_owner=source.source_owner,
                    verification_method=source.verification_method,
                    metadata_provenance_json=json.dumps(source.metadata_provenance, sort_keys=True),
                    semantic_tags_json=json.dumps(source.semantic_tags, sort_keys=True),
                    created_at=created_at,
                )
            )
        try:
            return self.add_revision(source_id, source)
        except BaseException:
            with self.database.engine.begin() as connection:
                connection.execute(
                    delete(knowledge_sources).where(knowledge_sources.c.source_id == source_id)
                )
            raise

    def add_revision(self, source_id: str, source: SourceInput) -> dict[str, Any]:
        self._validate(source)
        content = self._extract_content(source)
        raw_content = (
            source.content.encode("utf-8") if isinstance(source.content, str) else source.content
        )
        content_hash = hashlib.sha256(raw_content).hexdigest()
        with self.database.engine.connect() as connection:
            parent = (
                connection.execute(
                    select(knowledge_sources).where(knowledge_sources.c.source_id == source_id)
                )
                .mappings()
                .one_or_none()
            )
            if parent is None:
                raise KeyError(source_id)
            existing = (
                connection.execute(
                    select(knowledge_revisions).where(
                        knowledge_revisions.c.source_id == source_id,
                        knowledge_revisions.c.content_hash == content_hash,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing:
                return {
                    **self._revision_record(existing),
                    "duplicate": True,
                    "chunks": self._chunks(existing["revision_id"]),
                }
            previous = (
                connection.execute(
                    select(knowledge_revisions)
                    .where(knowledge_revisions.c.source_id == source_id)
                    .order_by(knowledge_revisions.c.version.desc())
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            version = (
                int(
                    connection.scalar(
                        select(func.max(knowledge_revisions.c.version)).where(
                            knowledge_revisions.c.source_id == source_id
                        )
                    )
                    or 0
                )
                + 1
            )

        revision_id = _id("kr")
        revision_dir = self.artifact_root / parent["workspace_id"] / source_id
        revision_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        suffix = Path(source.filename).suffix.casefold() if source.filename else ".txt"
        artifact_path = revision_dir / f"{revision_id}{suffix}"
        artifact_path.write_bytes(raw_content)
        artifact_path.chmod(0o600)
        chunks = self._chunk(content, parent["source_type"], parent["language"])
        observed_at = source.observed_at or self.clock()
        record = {
            "revision_id": revision_id,
            "source_id": source_id,
            "version": version,
            "content_hash": content_hash,
            "artifact_path": str(artifact_path),
            "status": source.status,
            "published_at": _iso(source.published_at),
            "updated_at": _iso(source.updated_at),
            "effective_from": _iso(source.effective_from),
            "effective_until": _iso(source.effective_until),
            "ingested_at": _iso(self.clock()),
            "observed_at": _iso(observed_at),
            "superseded_at": _iso(source.superseded_at),
            "source_timezone": source.source_timezone,
            "revision_metadata_provenance_json": json.dumps(
                source.metadata_provenance, sort_keys=True
            ),
            "revision_semantic_tags_json": json.dumps(source.semantic_tags, sort_keys=True),
            "supersedes_source_id": source.supersedes_source_id,
            "supersedes_revision_id": (
                source.supersedes_revision_id
                or (previous["revision_id"] if previous is not None else None)
            ),
            "superseded_by_source_id": None,
            "superseded_by_revision_id": None,
            "parser_version": PARSER_VERSION,
            "chunk_strategy": CHUNK_STRATEGY,
            "chunk_strategy_version": CHUNK_STRATEGY_VERSION,
            "embedding_model": MODEL_ID if self.embedder else None,
            "embedding_revision": MODEL_REVISION if self.embedder else None,
            "index_version": INDEX_VERSION,
            "parse_status": "succeeded",
            "index_status": "succeeded",
            "error": None,
        }
        try:
            with self.database.engine.begin() as connection:
                connection.execute(insert(knowledge_revisions).values(**record))
                if previous is not None:
                    connection.execute(
                        update(knowledge_revisions)
                        .where(knowledge_revisions.c.revision_id == previous["revision_id"])
                        .values(
                            status="superseded",
                            superseded_at=record["effective_from"],
                            superseded_by_source_id=source_id,
                            superseded_by_revision_id=revision_id,
                        )
                    )
                for item in chunks:
                    chunk_id = _id("kc")
                    connection.execute(
                        insert(knowledge_chunks).values(
                            chunk_id=chunk_id,
                            source_id=source_id,
                            revision_id=revision_id,
                            authority=parent["authority_level"],
                            validity=source.status,
                            **item,
                        )
                    )
                    connection.execute(
                        text(
                            "INSERT INTO knowledge_chunks_fts(chunk_id, text) VALUES (:id, :text)"
                        ),
                        {
                            "id": chunk_id,
                            "text": self._search_text(self._retrieval_text(item, parent["title"])),
                        },
                    )
                self._index_embeddings(connection, chunks, parent["title"])
        except Exception:
            artifact_path.unlink(missing_ok=True)
            raise
        return {**self.get_revision(revision_id), "duplicate": False}

    def reindex_revision(self, revision_id: str) -> dict[str, Any]:
        """Explicit derived-index upgrade; no new source revision or raw-text mutation."""
        revision = self.get_revision(revision_id)
        parent = self.get_source(revision["source_id"])
        if revision["index_version"] == INDEX_VERSION and (
            not self.embedder or revision["embedding_revision"] == MODEL_REVISION
        ):
            return {"revision_id": revision_id, "reindexed": False}
        path = Path(revision["artifact_path"])
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != revision["content_hash"]:
            raise ValueError("Source artifact hash mismatch; reindex refused")
        content = self._extract_content(
            SourceInput(
                title=parent["title"],
                source_type=parent["source_type"],
                source_channel=parent["source_channel"],
                content=raw,
                filename=path.name,
                published_at=_dt(revision["published_at"]),
                effective_from=_dt(revision["effective_from"]),
                source_timezone=revision["source_timezone"],
            )
        )
        chunks = self._chunk(content, parent["source_type"], parent["language"])
        if len(chunks) != len(revision["chunks"]) or any(
            (new["ordinal"], new["text"], new["section"])
            != (old["ordinal"], old["text"], old["section"])
            for new, old in zip(chunks, revision["chunks"], strict=True)
        ):
            raise ValueError("Chunk contract changed; representation-only reindex refused")
        with self.database.engine.begin() as connection:
            for chunk, old in zip(chunks, revision["chunks"], strict=True):
                connection.execute(
                    update(knowledge_chunks)
                    .where(knowledge_chunks.c.chunk_id == old["chunk_id"])
                    .values(parent_heading=chunk["parent_heading"])
                )
                connection.execute(
                    text("UPDATE knowledge_chunks_fts SET text=:text WHERE chunk_id=:id"),
                    {
                        "id": old["chunk_id"],
                        "text": self._search_text(self._retrieval_text(chunk, parent["title"])),
                    },
                )
            self._index_embeddings(connection, chunks, parent["title"])
            connection.execute(
                update(knowledge_revisions)
                .where(knowledge_revisions.c.revision_id == revision_id)
                .values(
                    index_version=INDEX_VERSION,
                    embedding_model=MODEL_ID if self.embedder else None,
                    embedding_revision=MODEL_REVISION if self.embedder else None,
                )
            )
        return {"revision_id": revision_id, "reindexed": True, "index_version": INDEX_VERSION}

    @staticmethod
    def _extract_content(source: SourceInput) -> str:
        if not source.filename or Path(source.filename).suffix.casefold() in {".md", ".txt"}:
            try:
                value = (
                    source.content.decode("utf-8")
                    if isinstance(source.content, bytes)
                    else source.content
                )
            except UnicodeDecodeError as error:
                raise ValueError("text knowledge files must be UTF-8") from error
            return value.replace("\r\n", "\n").strip()
        if Path(source.filename).suffix.casefold() != ".pdf":
            raise ValueError("P0 supports .md, .txt, and text-based .pdf")
        from io import BytesIO

        from pypdf import PdfReader

        raw = (
            source.content if isinstance(source.content, bytes) else source.content.encode("latin1")
        )
        try:
            reader = PdfReader(BytesIO(raw))
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as error:
            raise ValueError("PDF could not be parsed as a text-based document") from error
        content = "\n\n".join(f"[Page {index}]\n{text}" for index, text in enumerate(pages, 1))
        if len(content.strip()) < 20:
            raise ValueError("scanned PDF / OCR is unavailable in M2")
        return content.strip()

    def _chunk(self, content: str, source_type: str, language: str) -> list[dict[str, Any]]:
        sections: list[tuple[str | None, str | None, list[str]]] = []
        heading: str | None = None
        hierarchy: list[tuple[int, str]] = []
        blocks: list[str] = []
        for block in re.split(r"\n\s*\n", content):
            value = block.strip()
            if not value:
                continue
            match = _HEADING.match(value)
            if match:
                if blocks:
                    sections.append((heading, " > ".join(h for _, h in hierarchy) or None, blocks))
                    blocks = []
                heading = match.group(2).strip()
                level = len(match.group(1))
                hierarchy = [(n, h) for n, h in hierarchy if n < level]
                hierarchy.append((level, heading))
            else:
                blocks.append(value)
        if blocks or not sections:
            sections.append(
                (heading, " > ".join(h for _, h in hierarchy) or None, blocks or [content.strip()])
            )

        units: list[tuple[str | None, str | None, str]] = []
        for section, parent_heading, section_blocks in sections:
            if source_type == "faq":
                index = 0
                while index < len(section_blocks):
                    block = section_blocks[index]
                    if _QUESTION.match(block) and index + 1 < len(section_blocks):
                        units.append(
                            (section, parent_heading, f"{block}\n\n{section_blocks[index + 1]}")
                        )
                        index += 2
                    else:
                        units.append((section, parent_heading, block))
                        index += 1
            else:
                units.extend((section, parent_heading, block) for block in section_blocks)

        result: list[dict[str, Any]] = []
        for section, parent_heading, unit in units:
            tokens = unit.split()
            if len(tokens) <= self.chunk_config.max_tokens:
                pieces = [unit]
            else:
                step = max(1, self.chunk_config.max_tokens - self.chunk_config.overlap_tokens)
                pieces = [
                    " ".join(tokens[start : start + self.chunk_config.max_tokens])
                    for start in range(0, len(tokens), step)
                ]
            for piece in pieces:
                page_match = re.search(r"\[Page (\d+)\]", piece)
                result.append(
                    {
                        "section": section,
                        "parent_heading": parent_heading,
                        "page": int(page_match.group(1)) if page_match else None,
                        "ordinal": len(result),
                        "language": language,
                        "token_count": len(piece.split()),
                        "text": piece,
                    }
                )
        return result

    @staticmethod
    def _search_text(value: str) -> str:
        return f"{value}\n{' '.join(_terms(value))}"

    @staticmethod
    def _retrieval_text(item: Any, title: str) -> str:
        """Derived index input, never a replacement for original citation text."""
        heading = item["parent_heading"] or item["section"]
        prefix = f"Title: {title}\n" + (f"Heading: {heading}\n" if heading else "")
        return prefix + "\n" + item["text"]

    def _index_embeddings(self, connection: Any, chunks: list[dict[str, Any]], title: str) -> None:
        if self.embedder is None:
            return
        pending: dict[str, str] = {}
        for item in chunks:
            representation = self._retrieval_text(item, title)
            content_hash = _sha(REPRESENTATION_VERSION + "\n" + representation)
            exists = connection.scalar(
                select(func.count())
                .select_from(knowledge_embeddings)
                .where(
                    knowledge_embeddings.c.content_hash == content_hash,
                    knowledge_embeddings.c.model == MODEL_ID,
                    knowledge_embeddings.c.revision == MODEL_REVISION,
                )
            )
            if not exists:
                pending[content_hash] = representation
        if not pending:
            return
        vectors = self.embedder.embed(list(pending.values()))
        for content_hash, vector in zip(pending, vectors, strict=True):
            connection.execute(
                insert(knowledge_embeddings).values(
                    content_hash=content_hash,
                    model=MODEL_ID,
                    revision=MODEL_REVISION,
                    vector_json=json.dumps(np.asarray(vector, dtype=float).tolist()),
                )
            )

    def list_sources(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(
                select(knowledge_sources)
                .where(knowledge_sources.c.workspace_id == workspace_id)
                .order_by(knowledge_sources.c.created_at, knowledge_sources.c.source_id)
            ).mappings()
            return [self._source_record(row) for row in rows]

    def get_source(self, source_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = (
                connection.execute(
                    select(knowledge_sources).where(knowledge_sources.c.source_id == source_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(source_id)
            revisions = connection.execute(
                select(knowledge_revisions)
                .where(knowledge_revisions.c.source_id == source_id)
                .order_by(knowledge_revisions.c.version.desc())
            ).mappings()
            result = self._source_record(row)
            result["revisions"] = [self._revision_record(item) for item in revisions]
            return result

    def get_revision(self, revision_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = (
                connection.execute(
                    select(knowledge_revisions).where(
                        knowledge_revisions.c.revision_id == revision_id
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise KeyError(revision_id)
        return {**self._revision_record(row), "chunks": self._chunks(revision_id)}

    def get_chunk(self, chunk_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = (
                connection.execute(
                    select(knowledge_chunks).where(knowledge_chunks.c.chunk_id == chunk_id)
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise KeyError(chunk_id)
        return dict(row)

    def _chunks(self, revision_id: str) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    select(knowledge_chunks)
                    .where(knowledge_chunks.c.revision_id == revision_id)
                    .order_by(knowledge_chunks.c.ordinal)
                ).mappings()
            ]

    @staticmethod
    def _source_record(row: Any) -> dict[str, Any]:
        result = dict(row)
        result["metadata_provenance"] = json.loads(result.pop("metadata_provenance_json"))
        result["semantic_tags"] = json.loads(result.pop("semantic_tags_json"))
        return result

    @staticmethod
    def _revision_record(row: Any) -> dict[str, Any]:
        result = dict(row)
        result["metadata_provenance"] = json.loads(result.pop("revision_metadata_provenance_json"))
        result["semantic_tags"] = json.loads(result.pop("revision_semantic_tags_json"))
        return result

    def query(
        self,
        workspace_id: str,
        query: str,
        *,
        as_of_time: datetime | None = None,
        top_k: int = 5,
        neighbor_count: int = 1,
        max_context_chars: int = 4000,
    ) -> dict[str, Any]:
        if not query.strip() or len(query) > 8000:
            raise ValueError("query must not be empty")
        if not 1 <= top_k <= 20 or not 0 <= neighbor_count <= 2:
            raise ValueError("invalid retrieval bounds")
        if max_context_chars < 1:
            raise ValueError("invalid context bound")
        max_context_chars = min(max_context_chars, 4000, MAX_EVIDENCE_CHARS // top_k)
        now = self.clock()
        when = as_of_time or now
        current_fact_time = as_of_time is None or when >= now
        _iso(when)
        with self.database.engine.connect() as connection:
            stale = list(
                connection.scalars(
                    select(knowledge_revisions.c.revision_id)
                    .select_from(knowledge_revisions.join(knowledge_sources))
                    .where(
                        knowledge_sources.c.workspace_id == workspace_id,
                        knowledge_revisions.c.index_version != INDEX_VERSION,
                    )
                )
            )
        if stale:
            result = self._empty_result("insufficient_evidence", query, when)
            result["retrieval"].update(status="reindex_required", stale_revision_ids=stale)
            result["limitations"] = [
                "Existing sources need an explicit representation-only reindex; "
                "original documents are preserved."
            ]
            return result
        query_terms = _terms(query)
        lexical = self._lexical(query_terms, 40, workspace_id)
        semantic_scores = self._semantic(query, workspace_id, 40)
        fused = self._rrf(lexical[:20], list(semantic_scores)[:20])
        deeper_fused = self._rrf(lexical, list(semantic_scores))
        candidates = self._load_candidates(workspace_id, deeper_fused)
        if not candidates:
            return self._empty_result("no_authoritative_source", query, when)

        for item in candidates:
            item["temporal_state"] = self._temporal_state(item, when)
            if (
                current_fact_time
                and item["temporal_state"] == "active"
                and self._confirmed_historical(item)
            ):
                item["temporal_state"] = "inactive"
            matched = set(query_terms) & set(_terms(item["text"]))
            item["term_coverage"] = len(matched) / max(1, len(query_terms))
            item["semantic_score"] = semantic_scores.get(item["chunk_id"], 0.0)
            item["retrieval_channels"] = int(item["chunk_id"] in lexical) + int(
                item["chunk_id"] in semantic_scores
            )
        # Relevance is diagnostic, not permission to delete an RRF candidate or prove a fact.
        current_pool = self._select_candidates(
            [item for item in candidates if item["chunk_id"] in fused], fused, 20
        )
        deeper_pool = self._select_candidates(candidates, deeper_fused, len(candidates))
        pool = self._source_diverse_candidates(current_pool, deeper_pool, 20)
        if not pool:
            return self._empty_result("no_authoritative_source", query, when)
        selected = pool[:top_k]
        reranker = {
            "status": "not_configured" if self.answerer is None else "not_supported",
            "fallback": True,
            "candidate_count": len(pool),
            "evidence_chars": sum(len(item["text"]) for item in pool),
        }
        rerank = getattr(self.answerer, "rerank", None)
        if callable(rerank):
            payload = [
                {
                    key: item.get(key)
                    for key in (
                        "chunk_id",
                        "title",
                        "source_type",
                        "section",
                        "parent_heading",
                        "text",
                        "temporal_state",
                    )
                }
                for item in pool
            ]
            started = time.perf_counter()
            try:
                ranking, receipt = rerank(query, payload)
            except (RuntimeError, ValueError, TypeError):
                reranker.update(
                    status="provider_error",
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            else:
                valid = self._validated_ranking(ranking, [item["chunk_id"] for item in pool])
                reranker.update(
                    {
                        key: receipt[key]
                        for key in (
                            "configured_model",
                            "returned_model",
                            "usage",
                            "latency_ms",
                            "evidence_chars",
                            "request_chars",
                            "reranker_version",
                        )
                        if key in receipt
                    }
                )
                if valid is None:
                    reranker.update(status="invalid_response")
                else:
                    by_id = {item["chunk_id"]: item for item in pool}
                    selected = [by_id[chunk_id] for chunk_id in valid[:top_k]]
                    reranker.update(status="applied", fallback=False)
        citations = [self._citation(item, neighbor_count, max_context_chars) for item in selected]
        assessment = assess_answer(self.answerer, query, citations, as_of_time=_iso(when))
        status = assessment.pop("status")
        claims = assessment["claims"]
        answer = self._answer_text(status, citations)
        if claims and status in {"grounded", "conflict"}:
            answer = "\n".join(
                c["text"] + " [" + ", ".join(e["chunk_id"] for e in c["evidence"]) + "]"
                for c in claims
            )
        return {
            "query": query,
            "as_of_time": _iso(when),
            "answer_status": status,
            "answer": answer,
            **assessment,
            "citations": citations,
            "retrieval": {
                "methods": ["fts5_bm25"] + (["multilingual_embedding"] if self.embedder else []),
                "fusion": "rrf",
                "ranking": "multilingual_reranker"
                if reranker["status"] == "applied"
                else "rrf",
                "reranker": reranker,
                "policy_version": AUTHORITY_POLICY_VERSION,
                "candidate_selection_version": CANDIDATE_SELECTION_VERSION,
                "source_diversity_applied": [item["chunk_id"] for item in pool]
                != [item["chunk_id"] for item in current_pool],
                "index_version": INDEX_VERSION,
                "representation_version": REPRESENTATION_VERSION,
                "embedding_status": "available" if self.embedder else "unavailable",
            },
            "limitations": (
                [
                    "Answer assessment model is not configured; "
                    "evidence is not automatically treated as proof."
                ]
                if self.answerer is None
                else []
            )
            + (
                []
                if self.embedder
                else [
                    "Multilingual embedding is not configured; lexical retrieval remains available."
                ]
            ),
        }

    @staticmethod
    def _select_candidates(
        candidates: list[dict[str, Any]], fused: dict[str, float], top_k: int
    ) -> list[dict[str, Any]]:
        eligible = [
            item
            for item in candidates
            if item["official_status"] == "verified_official"
            and item["status"] not in {"draft", "unknown"}
            and item["temporal_state"] != "future"
        ]
        def rank_key(item: dict[str, Any]) -> tuple[float, str]:
            return -fused[item["chunk_id"]], item["chunk_id"]
        active = sorted(
            (item for item in eligible if item["temporal_state"] == "active"),
            key=rank_key,
        )
        inactive = sorted(
            (item for item in eligible if item["temporal_state"] == "inactive"),
            key=rank_key,
        )
        selected = (active + inactive)[:top_k]
        cross_channel_inactive = next(
            (item for item in inactive if item.get("retrieval_channels", 0) == 2), None
        )
        if (
            cross_channel_inactive
            and active
            and fused[cross_channel_inactive["chunk_id"]] > fused[active[0]["chunk_id"]]
        ):
            selected = [cross_channel_inactive] + [
                item for item in selected if item is not cross_channel_inactive
            ]
        return selected[:top_k]

    @staticmethod
    def _validated_ranking(ranking: object, candidate_ids: list[str]) -> list[str] | None:
        if not isinstance(ranking, list) or len(ranking) != len(candidate_ids):
            return None
        if any(not isinstance(item, str) for item in ranking):
            return None
        if len(set(ranking)) != len(ranking) or set(ranking) != set(candidate_ids):
            return None
        return ranking

    @staticmethod
    def _source_diverse_candidates(
        current: list[dict[str, Any]], deeper: list[dict[str, Any]], limit: int
    ) -> list[dict[str, Any]]:
        current = current[:limit]
        counts = Counter(item["source_id"] for item in current)
        if len(current) < limit or max(counts.values(), default=0) <= limit // 2:
            return current
        dominant = max(counts, key=counts.get)
        represented = set(counts)
        replacement = next(
            (item for item in deeper if item["source_id"] not in represented), None
        )
        if replacement is None:
            return current
        selected = list(current)
        drop_index = next(
            index for index in range(len(selected) - 1, -1, -1)
            if selected[index]["source_id"] == dominant
        )
        selected[drop_index] = replacement
        return selected

    def _lexical(self, terms: list[str], limit: int, workspace_id: str | None = None) -> list[str]:
        if not terms:
            return []
        expression = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)
        with self.database.engine.connect() as connection:
            return [
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT f.chunk_id FROM knowledge_chunks_fts f "
                        "JOIN knowledge_chunks c ON c.chunk_id=f.chunk_id "
                        "JOIN knowledge_sources s ON s.source_id=c.source_id "
                        "WHERE knowledge_chunks_fts MATCH :query "
                        "AND (:workspace IS NULL OR s.workspace_id=:workspace) "
                        "ORDER BY bm25(knowledge_chunks_fts) LIMIT :limit"
                    ),
                    {"query": expression, "limit": limit, "workspace": workspace_id},
                )
            ]

    def _semantic(self, query: str, workspace_id: str, limit: int) -> dict[str, float]:
        if self.embedder is None:
            return {}
        with self.database.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(knowledge_chunks, knowledge_sources.c.title)
                    .select_from(knowledge_chunks.join(knowledge_sources))
                    .where(knowledge_sources.c.workspace_id == workspace_id)
                )
                .mappings()
                .all()
            )
            cached = {
                row.content_hash: np.asarray(json.loads(row.vector_json), dtype=float)
                for row in connection.execute(
                    select(knowledge_embeddings).where(
                        knowledge_embeddings.c.model == MODEL_ID,
                        knowledge_embeddings.c.revision == MODEL_REVISION,
                    )
                )
            }
        query_vector = np.asarray(self.embedder.embed([query])[0], dtype=float)
        scored = [
            (
                row["chunk_id"],
                float(
                    cached[
                        _sha(
                            REPRESENTATION_VERSION + "\n" + self._retrieval_text(row, row["title"])
                        )
                    ]
                    @ query_vector
                ),
            )
            for row in rows
            if _sha(REPRESENTATION_VERSION + "\n" + self._retrieval_text(row, row["title"]))
            in cached
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return dict(scored[:limit])

    @staticmethod
    def _rrf(*rankings: list[str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for ranking in rankings:
            for rank, chunk_id in enumerate(ranking, 1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (60 + rank)
        return scores

    def _load_candidates(self, workspace_id: str, fused: dict[str, float]) -> list[dict[str, Any]]:
        if not fused:
            return []
        with self.database.engine.connect() as connection:
            rows = connection.execute(
                select(knowledge_chunks, knowledge_revisions, knowledge_sources)
                .select_from(knowledge_chunks.join(knowledge_revisions).join(knowledge_sources))
                .where(
                    knowledge_sources.c.workspace_id == workspace_id,
                    knowledge_chunks.c.chunk_id.in_(fused),
                )
            ).mappings()
            result = []
            for row in rows:
                item = dict(row)
                item["rrf_score"] = fused[item["chunk_id"]]
                result.append(item)
            return result

    @staticmethod
    def _temporal_state(item: dict[str, Any], when: datetime) -> str:
        start = _dt(item["effective_from"])
        end = _dt(item["effective_until"])
        published = _dt(item["published_at"])
        superseded = _dt(item["superseded_at"])
        if (start and when < start) or (published and when < published):
            return "future"
        if (end and when >= end) or (superseded and when >= superseded):
            return "inactive"
        return "active"

    @staticmethod
    def _confirmed_historical(item: dict[str, Any]) -> bool:
        if item["status"] != "historical":
            return False
        provenance = item.get("metadata_provenance_json", {})
        if isinstance(provenance, str):
            try:
                provenance = json.loads(provenance)
            except json.JSONDecodeError:
                return False
        return provenance.get("validity") in {"source-provided", "human-confirmed"}

    def _citation(self, item: dict[str, Any], neighbors: int, max_chars: int) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            context_rows = connection.execute(
                select(
                    knowledge_chunks.c.chunk_id,
                    knowledge_chunks.c.ordinal,
                    knowledge_chunks.c.text,
                    knowledge_chunks.c.section,
                    knowledge_chunks.c.parent_heading,
                    knowledge_chunks.c.page,
                )
                .where(
                    knowledge_chunks.c.revision_id == item["revision_id"],
                    knowledge_chunks.c.ordinal.between(
                        max(0, item["ordinal"] - neighbors), item["ordinal"] + neighbors
                    ),
                )
                .order_by(knowledge_chunks.c.ordinal)
            ).mappings()
            context = [dict(row) for row in context_rows]
        # Selected hit gets budget first; long previous text cannot crowd it out.
        context.sort(key=lambda row: (row["chunk_id"] != item["chunk_id"], row["ordinal"]))
        used = 0
        bounded = []
        for row in context:
            remaining = max_chars - used
            if remaining <= 0:
                break
            row["text"] = row["text"][:remaining]
            used += len(row["text"])
            bounded.append(row)
        bounded.sort(key=lambda row: row["ordinal"])
        return {
            "source_id": item["source_id"],
            "revision_id": item["revision_id"],
            "chunk_id": item["chunk_id"],
            "title": item["title"],
            "source_type": item["source_type"],
            "source_channel": item["source_channel"],
            "authority_level": item["authority_level"],
            "official_status": item["official_status"],
            "canonical_url": item["canonical_url"],
            "section": item["section"],
            "page": item["page"],
            "published_at": item["published_at"],
            "effective_from": item["effective_from"],
            "effective_until": item["effective_until"],
            "superseded_at": item["superseded_at"],
            "temporal_state": item["temporal_state"],
            "retrieval_scores": {
                "rrf": item["rrf_score"],
                "term_coverage": item["term_coverage"],
                "semantic_similarity": item["semantic_score"],
            },
            "text": item["text"],
            "context": bounded,
        }

    @staticmethod
    def _answer_text(status: str, citations: list[dict[str, Any]]) -> str | None:
        if status == "no_authoritative_source":
            return None
        if status == "conflict":
            return "Current official sources conflict; review the cited sources side by side."
        if status == "outdated_only":
            return "Only temporally inactive official material was found."
        if status == "insufficient_evidence":
            return (
                "Related official material was found, but it does not support the specific claim."
            )
        return None

    def _empty_result(self, status: str, query: str, when: datetime) -> dict[str, Any]:
        return {
            "query": query,
            "as_of_time": _iso(when),
            "answer_status": status,
            "answer": None,
            "citations": [],
            "claims": [],
            "answerability": {
                "status": "no_eligible_evidence",
                "requirements": [],
                "missing_facts": [],
            },
            "grounding": {"status": "not_assessed", "citation_valid": None},
            "retrieval": {
                "methods": ["fts5_bm25"] + (["multilingual_embedding"] if self.embedder else []),
                "fusion": "rrf",
                "ranking": "rrf",
                "reranker": {
                    "status": "not_run",
                    "fallback": False,
                    "candidate_count": 0,
                    "evidence_chars": 0,
                },
                "policy_version": AUTHORITY_POLICY_VERSION,
                "candidate_selection_version": CANDIDATE_SELECTION_VERSION,
                "source_diversity_applied": False,
                "index_version": INDEX_VERSION,
                "embedding_status": "available" if self.embedder else "unavailable",
            },
            "limitations": [],
        }

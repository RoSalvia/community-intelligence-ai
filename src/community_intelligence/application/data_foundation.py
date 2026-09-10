"""Persistent M1 data-foundation service for the v2.1 product path."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from community_intelligence.importers.telegram import import_telegram_export_with_identities
from community_intelligence.infrastructure.database import (
    Database,
    actor_identities,
    analysis_runs,
    communities,
    messages,
    role_assignments,
    sync_batches,
    user_check_watermarks,
    workspaces,
)
from community_intelligence.io import data_artifact_contents, publication_metadata, write_dataset
from community_intelligence.models import CommunityDataset, DatasetManifest, MessageRecord
from community_intelligence.pipeline import run_pipeline

MVP_LANGUAGES = ("en", "zh", "es")
WINDOW_DURATIONS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
_HASHED_USER_ID = re.compile(r"usr_[0-9a-f]+\Z")


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _require_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


class DataFoundationService:
    """Workspace, import, role, freshness, window, and analysis-run use cases."""

    def __init__(
        self,
        *,
        database_path: str | Path,
        artifact_root: str | Path,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.clock = clock
        self.database = Database(database_path)
        self.database.migrate(applied_at=_iso(self._now()))
        with self.database.engine.begin() as connection:
            connection.execute(
                update(analysis_runs)
                .where(analysis_runs.c.status.in_(("queued", "running")))
                .values(
                    status="failed",
                    finished_at=_iso(self._now()),
                    error="Analysis was interrupted before completion",
                )
            )
        self.artifact_root = Path(artifact_root).expanduser().resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.artifact_root.chmod(0o700)

    def _now(self) -> datetime:
        return self.clock().astimezone(UTC)

    def create_workspace(self, project_name: str) -> dict[str, Any]:
        record = {
            "workspace_id": _identifier("ws"),
            "project_name": _require_text(project_name, "project_name"),
            "created_at": _iso(self._now()),
            "settings_version": 1,
            "hash_salt": secrets.token_hex(32),
        }
        with self.database.engine.begin() as connection:
            connection.execute(insert(workspaces).values(**record))
        return {key: value for key, value in record.items() if key != "hash_salt"}

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(
                select(
                    workspaces.c.workspace_id,
                    workspaces.c.project_name,
                    workspaces.c.created_at,
                    workspaces.c.settings_version,
                ).order_by(workspaces.c.created_at, workspaces.c.workspace_id)
            ).mappings()
            return [dict(row) for row in rows]

    def get_workspace(self, workspace_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            workspace = (
                connection.execute(
                    select(
                        workspaces.c.workspace_id,
                        workspaces.c.project_name,
                        workspaces.c.created_at,
                        workspaces.c.settings_version,
                    ).where(workspaces.c.workspace_id == workspace_id)
                )
                .mappings()
                .one_or_none()
            )
            if workspace is None:
                raise KeyError(workspace_id)
            community_rows = [
                dict(row)
                for row in connection.execute(
                    select(communities).where(communities.c.workspace_id == workspace_id)
                ).mappings()
            ]
        order = {language: index for index, language in enumerate(MVP_LANGUAGES)}
        community_rows.sort(key=lambda item: (order[item["language"]], item["community_id"]))
        result = dict(workspace)
        result["communities"] = [
            {**item, "active": bool(item["active"])} for item in community_rows
        ]
        return result

    def update_workspace(self, workspace_id: str, project_name: str) -> dict[str, Any]:
        normalized_name = _require_text(project_name, "project_name")
        with self.database.engine.begin() as connection:
            changed = connection.execute(
                update(workspaces)
                .where(workspaces.c.workspace_id == workspace_id)
                .values(
                    project_name=normalized_name,
                    settings_version=workspaces.c.settings_version + 1,
                )
            ).rowcount
        if not changed:
            raise KeyError(workspace_id)
        return self.get_workspace(workspace_id)

    def create_community(
        self,
        workspace_id: str,
        name: str,
        language: str,
        timezone: str,
        *,
        platform: str = "telegram",
    ) -> dict[str, Any]:
        if language not in MVP_LANGUAGES:
            raise ValueError("MVP supports EN, CN, and ES communities only")
        if platform != "telegram":
            raise ValueError("MVP supports Telegram communities only")
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        record = {
            "community_id": _identifier("community"),
            "workspace_id": workspace_id,
            "name": _require_text(name, "name"),
            "language": language,
            "platform": platform,
            "timezone": timezone,
            "active": 1,
        }
        with self.database.engine.begin() as connection:
            exists = connection.scalar(
                select(func.count())
                .select_from(workspaces)
                .where(workspaces.c.workspace_id == workspace_id)
            )
            if not exists:
                raise KeyError(workspace_id)
            duplicate = connection.scalar(
                select(func.count())
                .select_from(communities)
                .where(
                    communities.c.workspace_id == workspace_id,
                    communities.c.language == language,
                )
            )
            if duplicate:
                raise ValueError(f"language {language!r} is already configured")
            connection.execute(insert(communities).values(**record))
        return {**record, "active": True}

    def import_telegram(self, community_id: str, source: str | Path) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            community = (
                connection.execute(
                    select(
                        communities.c.community_id,
                        communities.c.workspace_id,
                        communities.c.language,
                        workspaces.c.hash_salt,
                    )
                    .select_from(
                        communities.join(
                            workspaces,
                            communities.c.workspace_id == workspaces.c.workspace_id,
                        )
                    )
                    .where(communities.c.community_id == community_id)
                )
                .mappings()
                .one_or_none()
            )
        if community is None:
            raise KeyError(community_id)
        dataset, imported_identities, reply_targets = import_telegram_export_with_identities(
            source,
            language=community["language"],
            community_id=community_id,
            user_hash_salt=community["hash_salt"],
        )
        content_hash = dataset.manifest.source_sha256
        if content_hash is None:
            raise ValueError("Telegram source hash is unavailable")
        with self.database.engine.connect() as connection:
            existing = (
                connection.execute(
                    select(sync_batches).where(
                        sync_batches.c.community_id == community_id,
                        sync_batches.c.content_hash == content_hash,
                    )
                )
                .mappings()
                .one_or_none()
            )
        if existing is not None:
            return {**self._batch_record(existing), "duplicate": True}

        batch = {
            "source_batch_id": _identifier("batch"),
            "community_id": community_id,
            "source_type": "telegram_desktop_json",
            "window_start": _iso(min(item.timestamp for item in dataset.messages)),
            "window_end": _iso(max(item.timestamp for item in dataset.messages)),
            "imported_at": _iso(self._now()),
            "content_hash": content_hash,
            "status": "succeeded",
            "error": None,
            "message_count": len(dataset.messages),
        }
        try:
            with self.database.engine.begin() as connection:
                connection.execute(insert(sync_batches).values(**batch))
                for item in dataset.messages:
                    connection.execute(
                        insert(messages)
                        .prefix_with("OR IGNORE")
                        .values(
                            message_id=item.message_id,
                            community_id=community_id,
                            language=item.language,
                            user_id_hash=item.user_id_hash,
                            user_role=item.user_role,
                            timestamp=_iso(item.timestamp),
                            original_text=item.text,
                            reply_to_message_id=item.reply_to_message_id,
                            reply_to_source_key=reply_targets.get(item.message_id),
                            source_batch_id=batch["source_batch_id"],
                        )
                    )
                for identity in imported_identities:
                    existing_identity = (
                        connection.execute(
                            select(actor_identities).where(
                                actor_identities.c.user_id_hash == identity["user_id_hash"]
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if existing_identity is None:
                        connection.execute(
                            insert(actor_identities).values(
                                workspace_id=community["workspace_id"],
                                community_id=community_id,
                                **identity,
                                updated_at=batch["imported_at"],
                            )
                        )
                    else:
                        connection.execute(
                            update(actor_identities)
                            .where(actor_identities.c.user_id_hash == identity["user_id_hash"])
                            .values(
                                display_name=(
                                    identity["display_name"] or existing_identity["display_name"]
                                ),
                                platform_handle=(
                                    identity["platform_handle"]
                                    or existing_identity["platform_handle"]
                                ),
                                updated_at=batch["imported_at"],
                            )
                        )
                unresolved = connection.execute(
                    select(messages.c.message_id, messages.c.reply_to_source_key).where(
                        messages.c.reply_to_message_id.is_(None),
                        messages.c.reply_to_source_key.is_not(None),
                    )
                ).all()
                for child_id, parent_id in unresolved:
                    parent_exists = connection.scalar(
                        select(func.count())
                        .select_from(messages)
                        .where(messages.c.message_id == parent_id)
                    )
                    if parent_exists:
                        connection.execute(
                            update(messages)
                            .where(messages.c.message_id == child_id)
                            .values(reply_to_message_id=parent_id)
                        )
        except IntegrityError:
            with self.database.engine.connect() as connection:
                existing = (
                    connection.execute(
                        select(sync_batches).where(
                            sync_batches.c.community_id == community_id,
                            sync_batches.c.content_hash == content_hash,
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
            if existing is not None:
                return {**self._batch_record(existing), "duplicate": True}
            raise
        return {**self._batch_record(batch), "duplicate": False}

    @staticmethod
    def _batch_record(record: Any) -> dict[str, Any]:
        fields = (
            "source_batch_id",
            "community_id",
            "source_type",
            "window_start",
            "window_end",
            "imported_at",
            "content_hash",
            "status",
            "message_count",
        )
        return {field: record[field] for field in fields}

    def list_messages(
        self,
        workspace_id: str,
        *,
        resolve_roles: bool = False,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        conditions = [communities.c.workspace_id == workspace_id]
        if start is not None:
            conditions.append(messages.c.timestamp >= _iso(start))
        if end is not None:
            conditions.append(messages.c.timestamp < _iso(end))
        with self.database.engine.connect() as connection:
            rows = [
                dict(row)
                for row in connection.execute(
                    select(
                        messages.c.message_id,
                        messages.c.community_id,
                        messages.c.language,
                        messages.c.user_id_hash,
                        messages.c.user_role,
                        messages.c.timestamp,
                        messages.c.original_text,
                        messages.c.reply_to_message_id,
                        messages.c.source_batch_id,
                    )
                    .select_from(
                        messages.join(
                            communities,
                            messages.c.community_id == communities.c.community_id,
                        )
                    )
                    .where(*conditions)
                    .order_by(messages.c.timestamp, messages.c.message_id)
                ).mappings()
            ]
            assignments = (
                [
                    dict(row)
                    for row in connection.execute(
                        select(role_assignments)
                        .where(role_assignments.c.workspace_id == workspace_id)
                        .order_by(
                            role_assignments.c.user_id_hash,
                            role_assignments.c.version.desc(),
                        )
                    ).mappings()
                ]
                if resolve_roles
                else []
            )
        for row in rows:
            timestamp = _parse(row["timestamp"])
            matching = [
                item
                for item in assignments
                if item["user_id_hash"] == row["user_id_hash"]
                and _parse(item["valid_from"]) <= timestamp
                and (item["valid_to"] is None or timestamp < _parse(item["valid_to"]))
            ]
            if matching:
                row["user_role"] = matching[0]["role"]
        return rows

    def list_actors(self, workspace_id: str) -> list[dict[str, Any]]:
        self.get_workspace(workspace_id)
        with self.database.engine.connect() as connection:
            rows = connection.execute(
                select(
                    messages.c.community_id,
                    messages.c.user_id_hash,
                    actor_identities.c.display_name,
                    actor_identities.c.platform_handle,
                    actor_identities.c.pseudonym,
                    func.count().label("message_count"),
                    func.min(messages.c.timestamp).label("first_seen_at"),
                    func.max(messages.c.timestamp).label("last_seen_at"),
                )
                .select_from(
                    messages.join(
                        communities,
                        messages.c.community_id == communities.c.community_id,
                    ).outerjoin(
                        actor_identities,
                        actor_identities.c.user_id_hash == messages.c.user_id_hash,
                    )
                )
                .where(communities.c.workspace_id == workspace_id)
                .group_by(
                    messages.c.community_id,
                    messages.c.user_id_hash,
                    actor_identities.c.display_name,
                    actor_identities.c.platform_handle,
                    actor_identities.c.pseudonym,
                )
                .order_by(func.min(messages.c.timestamp), messages.c.user_id_hash)
            ).mappings()
            result = []
            for row in rows:
                actor = dict(row)
                pseudonym = actor["pseudonym"] or (
                    f"User {actor['user_id_hash'].removeprefix('usr_')[:4].upper()}"
                )
                actor["pseudonym"] = pseudonym
                actor["identity_scope"] = "local_only"
                if actor["display_name"] and actor["platform_handle"]:
                    actor["operator_label"] = (
                        f"{actor['display_name']} ({actor['platform_handle']})"
                    )
                else:
                    actor["operator_label"] = (
                        actor["display_name"] or actor["platform_handle"] or pseudonym
                    )
                result.append(actor)
            return result

    def set_role_assignment(
        self,
        workspace_id: str,
        user_id_hash: str,
        role: str,
        *,
        valid_from: datetime,
        valid_to: datetime | None,
    ) -> dict[str, Any]:
        if _HASHED_USER_ID.fullmatch(user_id_hash) is None:
            raise ValueError("user_id_hash must be anonymized")
        if role not in {"moderator", "user", "bot"}:
            raise ValueError("role must be moderator, user, or bot")
        if valid_to is not None and valid_to <= valid_from:
            raise ValueError("valid_to must be after valid_from")
        with self.database.engine.begin() as connection:
            exists = connection.scalar(
                select(func.count())
                .select_from(workspaces)
                .where(workspaces.c.workspace_id == workspace_id)
            )
            if not exists:
                raise KeyError(workspace_id)
            actor_exists = connection.scalar(
                select(func.count())
                .select_from(
                    messages.join(
                        communities,
                        messages.c.community_id == communities.c.community_id,
                    )
                )
                .where(
                    communities.c.workspace_id == workspace_id,
                    messages.c.user_id_hash == user_id_hash,
                )
            )
            if not actor_exists:
                raise ValueError("user_id_hash is not present in this workspace")
            version = (
                connection.scalar(
                    select(func.max(role_assignments.c.version)).where(
                        role_assignments.c.workspace_id == workspace_id,
                        role_assignments.c.user_id_hash == user_id_hash,
                    )
                )
                or 0
            ) + 1
            record = {
                "role_assignment_id": _identifier("role"),
                "workspace_id": workspace_id,
                "user_id_hash": user_id_hash,
                "role": role,
                "valid_from": _iso(valid_from),
                "valid_to": _iso(valid_to) if valid_to is not None else None,
                "source": "manual",
                "version": version,
                "created_at": _iso(self._now()),
            }
            connection.execute(insert(role_assignments).values(**record))
        return record

    def get_freshness(self, workspace_id: str) -> list[dict[str, Any]]:
        workspace = self.get_workspace(workspace_id)
        now = self._now()
        result: list[dict[str, Any]] = []
        with self.database.engine.connect() as connection:
            for community in workspace["communities"]:
                latest_message = connection.scalar(
                    select(func.max(messages.c.timestamp)).where(
                        messages.c.community_id == community["community_id"]
                    )
                )
                latest_import = connection.scalar(
                    select(func.max(sync_batches.c.imported_at)).where(
                        sync_batches.c.community_id == community["community_id"],
                        sync_batches.c.status == "succeeded",
                    )
                )
                age_seconds = (
                    max(0.0, (now - _parse(latest_message)).total_seconds())
                    if latest_message is not None
                    else None
                )
                result.append(
                    {
                        "community_id": community["community_id"],
                        "language": community["language"],
                        "latest_message_at": latest_message,
                        "last_imported_at": latest_import,
                        "age_seconds": age_seconds,
                        "status": (
                            "no_data"
                            if age_seconds is None
                            else "current"
                            if age_seconds <= 86400
                            else "stale"
                        ),
                    }
                )
        return result

    def resolve_window(
        self,
        workspace_id: str,
        window_kind: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, Any]:
        self.get_workspace(workspace_id)
        resolved_end = (end or self._now()).astimezone(UTC)
        fallback_used = False
        if window_kind in WINDOW_DURATIONS:
            resolved_start = resolved_end - WINDOW_DURATIONS[window_kind]
        elif window_kind == "since_last_check":
            with self.database.engine.connect() as connection:
                watermark = connection.scalar(
                    select(user_check_watermarks.c.checked_through).where(
                        user_check_watermarks.c.workspace_id == workspace_id
                    )
                )
            if watermark is None:
                resolved_start = resolved_end - timedelta(hours=24)
                fallback_used = True
            else:
                resolved_start = _parse(watermark)
        elif window_kind == "custom" and start is not None and end is not None:
            resolved_start = start.astimezone(UTC)
        else:
            raise ValueError("window must be since_last_check, 24h, 7d, 30d, or custom")
        if resolved_start >= resolved_end:
            raise ValueError("window start must be before end")
        duration = resolved_end - resolved_start
        return {
            "kind": window_kind,
            "start": _iso(resolved_start),
            "end": _iso(resolved_end),
            "baseline_start": _iso(resolved_start - duration),
            "baseline_end": _iso(resolved_start),
            "fallback_used": fallback_used,
        }

    def mark_checked(self, workspace_id: str, checked_through: datetime) -> dict[str, str]:
        self.get_workspace(workspace_id)
        if checked_through > self._now():
            raise ValueError("checked_through must not be in the future")
        record = {
            "workspace_id": workspace_id,
            "checked_through": _iso(checked_through),
            "updated_at": _iso(self._now()),
        }
        with self.database.engine.begin() as connection:
            connection.execute(
                delete(user_check_watermarks).where(
                    user_check_watermarks.c.workspace_id == workspace_id
                )
            )
            connection.execute(insert(user_check_watermarks).values(**record))
        return record

    def create_analysis_run(
        self,
        workspace_id: str,
        window_kind: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, Any]:
        window = self.resolve_window(workspace_id, window_kind, start=start, end=end)
        with self.database.engine.connect() as connection:
            batch_hashes = list(
                connection.execute(
                    select(sync_batches.c.content_hash)
                    .select_from(
                        sync_batches.join(
                            communities,
                            sync_batches.c.community_id == communities.c.community_id,
                        )
                    )
                    .where(
                        communities.c.workspace_id == workspace_id,
                        sync_batches.c.status == "succeeded",
                    )
                    .order_by(sync_batches.c.content_hash)
                ).scalars()
            )
        fingerprint = hashlib.sha256(
            json.dumps(
                {"workspace_id": workspace_id, "window": window, "batch_hashes": batch_hashes},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        with self.database.engine.connect() as connection:
            existing = (
                connection.execute(
                    select(analysis_runs)
                    .where(
                        analysis_runs.c.input_fingerprint == fingerprint,
                        analysis_runs.c.status == "succeeded",
                    )
                    .order_by(analysis_runs.c.finished_at.desc())
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            message_count = connection.scalar(
                select(func.count())
                .select_from(
                    messages.join(
                        communities,
                        messages.c.community_id == communities.c.community_id,
                    )
                )
                .where(
                    communities.c.workspace_id == workspace_id,
                    messages.c.timestamp >= window["start"],
                    messages.c.timestamp < window["end"],
                )
            )
        if existing is not None:
            result = self._analysis_record(existing)
            result["reused"] = True
            return result
        has_activity = bool(message_count)
        now = _iso(self._now())
        record = {
            "analysis_run_id": _identifier("run"),
            "workspace_id": workspace_id,
            "window_kind": window_kind,
            "window_start": window["start"],
            "window_end": window["end"],
            "baseline_start": window["baseline_start"],
            "baseline_end": window["baseline_end"],
            "fallback_used": int(window["fallback_used"]),
            "activity_status": "new_activity" if has_activity else "no_new_activity",
            "status": "queued" if has_activity else "succeeded",
            "progress": 0 if has_activity else 100,
            "input_fingerprint": fingerprint,
            "methods_json": json.dumps(
                {"profile": "deterministic", "legacy_pipeline": "v0.1"}, sort_keys=True
            ),
            "created_at": now,
            "started_at": None,
            "finished_at": None if has_activity else now,
            "report_path": None,
            "error": None,
        }
        with self.database.engine.begin() as connection:
            connection.execute(insert(analysis_runs).values(**record))
        return self._analysis_record(record)

    def get_analysis_run(self, analysis_run_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            record = (
                connection.execute(
                    select(analysis_runs).where(analysis_runs.c.analysis_run_id == analysis_run_id)
                )
                .mappings()
                .one_or_none()
            )
        if record is None:
            raise KeyError(analysis_run_id)
        return self._analysis_record(record)

    @staticmethod
    def _analysis_record(record: Any) -> dict[str, Any]:
        result = dict(record)
        result["fallback_used"] = bool(result["fallback_used"])
        result["methods"] = json.loads(result.pop("methods_json"))
        result["reused"] = False
        return result

    def execute_analysis_run(self, analysis_run_id: str) -> dict[str, Any]:
        run = self.get_analysis_run(analysis_run_id)
        if run["status"] == "succeeded":
            return run
        with self.database.engine.begin() as connection:
            connection.execute(
                update(analysis_runs)
                .where(analysis_runs.c.analysis_run_id == analysis_run_id)
                .values(status="running", progress=10, started_at=_iso(self._now()), error=None)
            )
        try:
            records = self.list_messages(
                run["workspace_id"],
                resolve_roles=True,
                start=_parse(run["window_start"]),
                end=_parse(run["window_end"]),
            )
            if not records:
                raise ValueError("No messages are available in this analysis window")
            selected_ids = {item["message_id"] for item in records}
            message_models = [
                MessageRecord(
                    message_id=item["message_id"],
                    community_id=item["community_id"],
                    language=item["language"],
                    user_id_hash=item["user_id_hash"],
                    user_role=item["user_role"],
                    timestamp=_parse(item["timestamp"]),
                    text=item["original_text"],
                    reply_to_message_id=(
                        item["reply_to_message_id"]
                        if item["reply_to_message_id"] in selected_ids
                        else None
                    ),
                    campaign_id=None,
                )
                for item in records
            ]
            dataset_id = f"workspace-{run['workspace_id']}-{analysis_run_id}"
            contents = data_artifact_contents(message_models, [], [], [], [])
            generation_id, checksums = publication_metadata(dataset_id, contents)
            dataset = CommunityDataset(
                messages=message_models,
                campaigns=[],
                claims=[],
                outcomes=[],
                annotations=[],
                manifest=DatasetManifest(
                    dataset_id=dataset_id,
                    schema_version="2.1-m1",
                    synthetic=False,
                    seed=None,
                    message_count=len(message_models),
                    community_ids=sorted({item.community_id for item in message_models}),
                    languages=sorted({item.language for item in message_models}),
                    campaign_ids=[],
                    scenarios={},
                    generated_at=self._now(),
                    generation_id=generation_id,
                    artifact_checksums=checksums,
                    source_format="workspace_batches_v2.1",
                    source_sha256=None,
                    limitations=[
                        "M1 runs the preserved deterministic v0.1 analysis only; "
                        "Topic, Signal, Brief, and Copilot are not implemented yet."
                    ],
                ),
            )
            attempt_root = self.artifact_root / f"{analysis_run_id}-{uuid.uuid4().hex}"
            dataset_dir = write_dataset(dataset, attempt_root / "dataset")
            report_path = run_pipeline(dataset_dir, attempt_root / "report") / "report.json"
            with self.database.engine.begin() as connection:
                connection.execute(
                    update(analysis_runs)
                    .where(analysis_runs.c.analysis_run_id == analysis_run_id)
                    .values(
                        status="succeeded",
                        progress=100,
                        finished_at=_iso(self._now()),
                        report_path=str(report_path),
                        error=None,
                    )
                )
        except Exception as error:
            with self.database.engine.begin() as connection:
                connection.execute(
                    update(analysis_runs)
                    .where(analysis_runs.c.analysis_run_id == analysis_run_id)
                    .values(
                        status="failed",
                        progress=0,
                        finished_at=_iso(self._now()),
                        error=str(error).splitlines()[0],
                    )
                )
            raise
        return self.get_analysis_run(analysis_run_id)

"""Telegram Desktop JSON v0.1 import into the message-first dataset contract."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from community_intelligence.io import data_artifact_contents, publication_metadata
from community_intelligence.models import CommunityDataset, DatasetManifest, MessageRecord

SOURCE_FORMAT = "telegram_desktop_json_v0.1"


def _invalid(reason: str) -> ValueError:
    return ValueError(f"invalid Telegram Desktop export: {reason}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _invalid(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _flatten_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    fragments: list[str] = []
    for item in value:
        if isinstance(item, str):
            fragments.append(item)
        elif isinstance(item, dict):
            fragments.append(_flatten_text(item.get("text", "")))
    return "".join(fragments)


def _timestamp(record: dict[str, Any]) -> datetime:
    unix_value = record.get("date_unixtime")
    if unix_value is not None:
        try:
            return datetime.fromtimestamp(int(unix_value), tz=UTC)
        except (OSError, OverflowError, TypeError, ValueError) as error:
            raise _invalid("message date_unixtime must be a valid Unix timestamp") from error
    date_value = record.get("date")
    if not isinstance(date_value, str):
        raise _invalid("each imported message requires date_unixtime or date")
    try:
        parsed = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
    except ValueError as error:
        raise _invalid("message date must be valid ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _invalid("message date must include a timezone")
    return parsed.astimezone(UTC)


def _digest(prefix: str, value: object, *, length: int | None = None) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{prefix}{digest if length is None else digest[:length]}"


def import_telegram_export_with_identities(
    input_path: str | Path,
    *,
    language: str = "und",
    community_id: str | None = None,
    user_hash_salt: str | None = None,
) -> tuple[CommunityDataset, list[dict[str, str | None]], dict[str, str]]:
    """Parse messages plus local-only operator identities and stable reply targets."""

    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise _invalid("input must be a readable result.json file")
    try:
        raw = source.read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except UnicodeDecodeError as error:
        raise _invalid("input must be UTF-8") from error
    except json.JSONDecodeError as error:
        raise _invalid("input must contain valid JSON") from error
    if not isinstance(value, dict):
        raise _invalid("top level must be an object")
    records = value.get("messages")
    if not isinstance(records, list) or not records:
        raise _invalid("messages must be a non-empty array")

    source_sha256 = hashlib.sha256(raw).hexdigest()
    community_identity = {
        "id": value.get("id"),
        "name": value.get("name"),
        "type": value.get("type"),
        "source_sha256": source_sha256,
    }
    community_id = community_id or _digest("community_tg_", community_identity, length=16)
    candidates: list[dict[str, Any]] = []
    identities: dict[str, dict[str, str | None]] = {}
    reply_targets: dict[str, str] = {}
    skipped_service = 0
    skipped_textless = 0
    for position, raw_record in enumerate(records):
        if not isinstance(raw_record, dict):
            raise _invalid(f"message at index {position} must be an object")
        if raw_record.get("type") != "message":
            skipped_service += 1
            continue
        text = _flatten_text(raw_record.get("text", ""))
        if not text.strip():
            skipped_textless += 1
            continue
        raw_message_id = raw_record.get("id")
        if raw_message_id is None:
            raise _invalid(f"message at index {position} has no id")
        sender = (
            raw_record.get("from_id")
            or raw_record.get("actor_id")
            or raw_record.get("from")
            or f"unknown-sender:{raw_message_id}"
        )
        user_id_hash = _digest(
            "usr_",
            {
                "community": community_id,
                "sender": str(sender),
                **({"salt": user_hash_salt} if user_hash_salt is not None else {}),
            },
        )
        display_value = raw_record.get("from")
        display_name = (
            display_value.strip()[:200]
            if isinstance(display_value, str) and display_value.strip()
            else None
        )
        handle_value = raw_record.get("from_username") or raw_record.get("username")
        platform_handle = (
            f"@{handle_value.strip().lstrip('@')[:64]}"
            if isinstance(handle_value, str) and handle_value.strip().lstrip("@")
            else None
        )
        previous_identity = identities.get(user_id_hash, {})
        identities[user_id_hash] = {
            "user_id_hash": user_id_hash,
            "display_name": display_name or previous_identity.get("display_name"),
            "platform_handle": platform_handle or previous_identity.get("platform_handle"),
            "pseudonym": f"User {user_id_hash.removeprefix('usr_')[:4].upper()}",
        }
        message_id = _digest(
            "tg_", {"community": community_id, "message": raw_message_id}, length=24
        )
        raw_reply_value = raw_record.get("reply_to_message_id")
        raw_reply_id = str(raw_reply_value) if raw_reply_value is not None else None
        if raw_reply_id is not None:
            reply_targets[message_id] = _digest(
                "tg_",
                {"community": community_id, "message": raw_reply_value},
                length=24,
            )
        candidates.append(
            {
                "raw_id": str(raw_message_id),
                "raw_reply_id": raw_reply_id,
                "message_id": message_id,
                "user_id_hash": user_id_hash,
                "timestamp": _timestamp(raw_record),
                "text": text,
            }
        )
    if not candidates:
        raise _invalid("messages array contains no supported text messages")

    seen: dict[str, MessageRecord] = {}
    messages: list[MessageRecord] = []
    dropped_replies = 0
    for candidate in candidates:
        parent = seen.get(candidate["raw_reply_id"])
        reply_to = None
        if candidate["raw_reply_id"] is not None:
            if parent is not None and parent.timestamp <= candidate["timestamp"]:
                reply_to = parent.message_id
            else:
                dropped_replies += 1
        message = MessageRecord(
            message_id=candidate["message_id"],
            community_id=community_id,
            language=language,
            user_id_hash=candidate["user_id_hash"],
            user_role="user",
            timestamp=candidate["timestamp"],
            text=candidate["text"],
            reply_to_message_id=reply_to,
            campaign_id=None,
        )
        if candidate["raw_id"] in seen:
            raise _invalid(f"duplicate message id {candidate['raw_id']!r}")
        seen[candidate["raw_id"]] = message
        messages.append(message)

    limitations = [
        (
            "Telegram export does not reliably identify moderator roles; "
            "imported roles default to user."
        ),
        "Message text is retained for analysis and is not automatically redacted.",
    ]
    if skipped_service:
        limitations.append(f"Skipped {skipped_service} service message(s).")
    if skipped_textless:
        limitations.append(f"Skipped {skipped_textless} textless message(s).")
    if dropped_replies:
        limitations.append(
            f"Dropped {dropped_replies} reply link(s) whose parent was unavailable or later."
        )

    dataset_id = f"telegram-{source_sha256[:16]}"
    contents = data_artifact_contents(messages, [], [], [], [])
    generation_id, checksums = publication_metadata(dataset_id, contents)
    manifest = DatasetManifest(
        dataset_id=dataset_id,
        schema_version="1.1",
        synthetic=False,
        seed=None,
        message_count=len(messages),
        community_ids=[community_id],
        languages=sorted({message.language for message in messages}),
        campaign_ids=[],
        scenarios={},
        generated_at=max(message.timestamp for message in messages),
        generation_id=generation_id,
        artifact_checksums=checksums,
        source_format=SOURCE_FORMAT,
        source_sha256=source_sha256,
        limitations=limitations,
    )
    return (
        CommunityDataset(
            messages=messages,
            campaigns=[],
            claims=[],
            outcomes=[],
            annotations=[],
            manifest=manifest,
        ),
        list(identities.values()),
        reply_targets,
    )


def import_telegram_export(
    input_path: str | Path,
    *,
    language: str = "und",
    community_id: str | None = None,
    user_hash_salt: str | None = None,
) -> CommunityDataset:
    """Compatibility API that excludes local-only operator identity metadata."""

    dataset, _, _ = import_telegram_export_with_identities(
        input_path,
        language=language,
        community_id=community_id,
        user_hash_salt=user_hash_salt,
    )
    return dataset

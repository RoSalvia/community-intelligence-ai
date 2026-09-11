"""Stable extraction and Project Knowledge ingestion for a public Telegram channel."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from community_intelligence.application.knowledge import SourceInput
from community_intelligence.importers.telegram import _flatten_text, _timestamp

EXTRACTION_METHOD_VERSION = "telegram-live-json-channel-slice-v1.0.0"
NORMALIZER_VERSION = "telegram-official-announcement-v1.0.0"
_MEDIA_KEYS = frozenset(
    {
        "animation",
        "audio_file",
        "contact_information",
        "file",
        "location_information",
        "media_type",
        "photo",
        "place_name",
        "poll",
        "sticker_emoji",
        "thumbnail",
        "video_file",
        "video_message",
        "voice_message",
    }
)
_FORWARD_KEYS = frozenset(
    {
        "forwarded_from",
        "forwarded_from_id",
        "forwarded_from_name",
        "forwarded_from_message_id",
        "forwarded_from_chat_id",
    }
)
_LINK_TYPES = frozenset({"email", "link", "text_link"})


class _IncompleteJSON(ValueError):
    pass


@dataclass(frozen=True)
class ChannelFingerprint:
    name: str
    channel_id: object
    channel_type: object
    start_offset: int
    end_offset: int
    source_range_sha256: str
    raw_bytes: bytes
    value: dict[str, Any]
    source_size: int
    source_mtime_ns: int
    captured_at: str


@dataclass(frozen=True)
class AnnouncementPack:
    aggregate: dict[str, Any]
    normalized_messages: tuple[dict[str, Any], ...]
    source_inputs: tuple[SourceInput, ...]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _skip_space(data: bytes, index: int) -> int:
    while index < len(data) and data[index] in b" \t\r\n":
        index += 1
    return index


def _string_end(data: bytes, start: int) -> int:
    if start >= len(data) or data[start] != ord('"'):
        raise ValueError("expected JSON string")
    escaped = False
    for index in range(start + 1, len(data)):
        value = data[index]
        if escaped:
            escaped = False
        elif value == ord("\\"):
            escaped = True
        elif value == ord('"'):
            return index + 1
    raise _IncompleteJSON("incomplete JSON string")


def _decode_string(data: bytes, start: int) -> tuple[str, int]:
    end = _string_end(data, start)
    return json.loads(data[start:end].decode("utf-8")), end


def _value_end(data: bytes, start: int) -> int:
    start = _skip_space(data, start)
    if start >= len(data):
        raise _IncompleteJSON("incomplete JSON value")
    first = data[start]
    if first == ord('"'):
        return _string_end(data, start)
    if first in (ord("{"), ord("[")):
        expected = [ord("}") if first == ord("{") else ord("]")]
        in_string = False
        escaped = False
        for index in range(start + 1, len(data)):
            value = data[index]
            if in_string:
                if escaped:
                    escaped = False
                elif value == ord("\\"):
                    escaped = True
                elif value == ord('"'):
                    in_string = False
                continue
            if value == ord('"'):
                in_string = True
            elif value == ord("{"):
                expected.append(ord("}"))
            elif value == ord("["):
                expected.append(ord("]"))
            elif value in (ord("}"), ord("]")):
                if not expected or value != expected[-1]:
                    raise ValueError("mismatched JSON delimiter")
                expected.pop()
                if not expected:
                    return index + 1
        raise _IncompleteJSON("incomplete JSON container")
    index = start
    while index < len(data) and data[index] not in b",]} \t\r\n":
        index += 1
    json.loads(data[start:index].decode("ascii"))
    return index


def _object_value_start(data: bytes, object_start: int, wanted_key: str) -> int:
    index = _skip_space(data, object_start)
    if index >= len(data) or data[index] != ord("{"):
        raise ValueError("expected JSON object")
    index += 1
    while True:
        index = _skip_space(data, index)
        if index >= len(data):
            raise _IncompleteJSON(f"object ended before key {wanted_key!r}")
        if data[index] == ord("}"):
            raise ValueError(f"JSON object has no key {wanted_key!r}")
        key, index = _decode_string(data, index)
        index = _skip_space(data, index)
        if index >= len(data) or data[index] != ord(":"):
            raise _IncompleteJSON("object key has no complete value")
        value_start = _skip_space(data, index + 1)
        if key == wanted_key:
            return value_start
        index = _skip_space(data, _value_end(data, value_start))
        if index >= len(data):
            raise _IncompleteJSON(f"object ended before key {wanted_key!r}")
        if data[index] == ord(","):
            index += 1
            continue
        if data[index] == ord("}"):
            raise ValueError(f"JSON object has no key {wanted_key!r}")
        raise ValueError("invalid JSON object separator")


def _array_objects(data: bytes, array_start: int) -> list[tuple[int, int, dict[str, Any]]]:
    index = _skip_space(data, array_start)
    if index >= len(data) or data[index] != ord("["):
        raise ValueError("chats.list must be a JSON array")
    index += 1
    output: list[tuple[int, int, dict[str, Any]]] = []
    while True:
        index = _skip_space(data, index)
        if index >= len(data) or data[index] == ord("]"):
            return output
        start = index
        try:
            end = _value_end(data, start)
        except _IncompleteJSON:
            return output
        value = json.loads(
            data[start:end].decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
        if not isinstance(value, dict):
            raise ValueError("every chats.list item must be an object")
        output.append((start, end, value))
        index = _skip_space(data, end)
        if index >= len(data) or data[index] == ord("]"):
            return output
        if data[index] != ord(","):
            raise ValueError("invalid chats.list separator")
        index += 1


def _read_stable_prefix(path: Path) -> tuple[bytes, os.stat_result]:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        before = os.fstat(descriptor)
        remaining = before.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("live export shrank while its prefix was being inspected")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError("live export was replaced while being inspected")
        if after.st_size < before.st_size:
            raise ValueError("live export shrank while being inspected")
        return b"".join(chunks), before
    finally:
        os.close(descriptor)


def inspect_complete_channel(source_path: str | Path, channel_name: str) -> ChannelFingerprint:
    """Fingerprint one complete channel object in a possibly incomplete live export."""

    source = Path(source_path).expanduser().resolve(strict=True)
    data, status = _read_stable_prefix(source)
    chats_start = _object_value_start(data, 0, "chats")
    list_start = _object_value_start(data, chats_start, "list")
    matches = [
        item
        for item in _array_objects(data, list_start)
        if item[2].get("name") == channel_name
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one complete target channel, found {len(matches)}")
    start, end, value = matches[0]
    if not isinstance(value.get("messages"), list):
        raise ValueError("target channel has no messages array")
    raw = data[start:end]
    return ChannelFingerprint(
        name=channel_name,
        channel_id=value.get("id"),
        channel_type=value.get("type"),
        start_offset=start,
        end_offset=end,
        source_range_sha256=hashlib.sha256(raw).hexdigest(),
        raw_bytes=raw,
        value=value,
        source_size=status.st_size,
        source_mtime_ns=status.st_mtime_ns,
        captured_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def _fingerprint_identity(item: ChannelFingerprint) -> tuple[object, ...]:
    return (
        item.name,
        item.channel_id,
        item.channel_type,
        item.start_offset,
        item.end_offset,
        item.source_range_sha256,
    )


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def freeze_official_channel(
    source_path: str | Path,
    channel_name: str,
    output_dir: str | Path,
    *,
    stability_checks: int = 3,
    stability_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    """Publish an immutable private channel snapshot after repeated stable range hashes."""

    if stability_checks < 2:
        raise ValueError("at least two stability checks are required")
    if stability_interval_seconds < 0:
        raise ValueError("stability interval must not be negative")
    source = Path(source_path).expanduser().resolve(strict=True)
    destination = Path(output_dir).expanduser().absolute()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.path.lexists(destination):
        raise FileExistsError(f"output path already exists: {destination}")
    observations: list[ChannelFingerprint] = []
    for index in range(stability_checks):
        observations.append(inspect_complete_channel(source, channel_name))
        if index + 1 < stability_checks and stability_interval_seconds:
            time.sleep(stability_interval_seconds)
    if any(
        _fingerprint_identity(item) != _fingerprint_identity(observations[0])
        for item in observations[1:]
    ):
        raise ValueError("target channel changed between stability observations")
    selected = observations[-1]
    snapshot = _json_bytes(selected.value)
    provenance = {
        "source_path": str(source),
        "channel_name": selected.name,
        "channel_id": selected.channel_id,
        "channel_type": selected.channel_type,
        "source_byte_range": [selected.start_offset, selected.end_offset],
        "source_byte_range_sha256": selected.source_range_sha256,
        "snapshot_sha256": hashlib.sha256(snapshot).hexdigest(),
        "extraction_time": datetime.now(UTC).isoformat(timespec="seconds"),
        "extraction_method_version": EXTRACTION_METHOD_VERSION,
        "stability": {
            "checks": len(observations),
            "stable": True,
            "observed_source_growth": any(
                later.source_size > earlier.source_size
                for earlier, later in zip(observations, observations[1:], strict=False)
            ),
            "observations": [
                {
                    "captured_at": item.captured_at,
                    "source_size": item.source_size,
                    "source_mtime_ns": item.source_mtime_ns,
                    "source_range_sha256": item.source_range_sha256,
                }
                for item in observations
            ],
        },
    }
    staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix=f".{destination.name}.staging-"))
    try:
        (staging / "result.json").write_bytes(snapshot)
        (staging / "provenance.json").write_bytes(_json_bytes(provenance))
        for child in staging.iterdir():
            child.chmod(0o600)
        os.rename(staging, destination)
    except BaseException:
        for child in staging.iterdir():
            child.unlink(missing_ok=True)
        staging.rmdir()
        raise
    return provenance


def _language(text: str) -> tuple[str, str]:
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return "und", "no-alphabetic-signal"
    cyrillic = sum("\u0400" <= character <= "\u04ff" for character in letters)
    latin = sum("LATIN" in unicodedata.name(character, "") for character in letters)
    if cyrillic / len(letters) >= 0.25:
        return "ru", "system-derived-script-audit"
    if latin / len(letters) >= 0.75:
        return "en", "system-derived-script-audit"
    return "und", "mixed-or-unknown-script"


def _select_metadata(record: dict[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    return {key: record[key] for key in sorted(keys) if record.get(key) not in (None, "", [], {})}


def _links(entities: object) -> list[dict[str, Any]]:
    if not isinstance(entities, list):
        return []
    return [
        entity
        for entity in entities
        if isinstance(entity, dict) and entity.get("type") in _LINK_TYPES
    ]


def build_announcement_pack(
    snapshot_path: str | Path,
    *,
    normalized_path: str | Path,
    canonical_username: str,
    authority_evidence: tuple[str, ...],
    observed_at: datetime,
) -> AnnouncementPack:
    """Normalize all text-bearing ordinary messages and map each to one Knowledge source."""

    if not canonical_username.strip().lstrip("@"):
        raise ValueError("canonical Telegram username is required")
    if len(authority_evidence) < 2 or any(
        not item.startswith("https://") for item in authority_evidence
    ):
        raise ValueError("at least two HTTPS first-party authority evidence records are required")
    source = Path(snapshot_path).expanduser().resolve(strict=True)
    raw_snapshot = source.read_bytes()
    value = json.loads(raw_snapshot.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(value, dict) or not isinstance(value.get("messages"), list):
        raise ValueError("frozen channel snapshot must contain a messages array")
    if value.get("type") != "public_channel":
        raise ValueError("official announcement source must be a public_channel")
    username = canonical_username.strip().lstrip("@")
    ordinary_count = 0
    service_count = 0
    textless_count = 0
    precise_count = 0
    normalized: list[dict[str, Any]] = []
    source_inputs: list[SourceInput] = []
    all_timestamps: list[datetime] = []
    all_ids: list[int | str] = []
    for position, record in enumerate(value["messages"]):
        if not isinstance(record, dict):
            raise ValueError(f"message at index {position} must be an object")
        if record.get("type") != "message":
            service_count += 1
            continue
        ordinary_count += 1
        message_id = record.get("id")
        if message_id is None:
            raise ValueError(f"ordinary message at index {position} has no id")
        all_ids.append(message_id)
        if record.get("date_unixtime") is None:
            raise ValueError(f"ordinary message {message_id} has no date_unixtime")
        published = _timestamp(record)
        precise_count += 1
        all_timestamps.append(published)
        content = _flatten_text(record.get("text", "")).replace("\r\n", "\n").strip()
        if not content:
            textless_count += 1
            continue
        raw_record = json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        raw_hash = hashlib.sha256(raw_record).hexdigest()
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        language, language_basis = _language(content)
        entities = (
            record.get("text_entities")
            if isinstance(record.get("text_entities"), list)
            else []
        )
        media = _select_metadata(record, _MEDIA_KEYS)
        forwarded = _select_metadata(record, _FORWARD_KEYS)
        reactions = record.get("reactions") if isinstance(record.get("reactions"), list) else []
        canonical_url = f"https://t.me/{username}/{message_id}"
        item = {
            "channel_identity": {
                "name": value.get("name"),
                "id": value.get("id"),
                "type": value.get("type"),
                "username": username,
                "authority": "official",
                "authority_evidence": list(authority_evidence),
            },
            "message_id": message_id,
            "published_at": published.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "temporal_precision": "second",
            "text": content,
            "text_entities": entities,
            "links": _links(entities),
            "media_references": media,
            "forwarded_metadata": forwarded,
            "reactions": reactions,
            "source_language": language,
            "source_language_basis": language_basis,
            "canonical_telegram_message_link": canonical_url,
            "raw_hash": raw_hash,
            "normalized_content_hash": content_hash,
            "normalizer_version": NORMALIZER_VERSION,
        }
        normalized.append(item)
        source_inputs.append(
            SourceInput(
                title=(
                    "Official Telegram · "
                    f"{published.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')} · #{message_id}"
                ),
                source_type="telegram_announcement",
                source_channel="telegram",
                content=content,
                canonical_url=canonical_url,
                platform="telegram",
                platform_content_id=str(message_id),
                author=str(value.get("name") or "Blum Official Telegram"),
                language=language,
                project_scope="blum",
                authority_level="official",
                official_status="verified_official",
                verification_method="first-party Blum link plus matching public Telegram channel",
                published_at=published,
                temporal_precision="second",
                effective_from=None,
                observed_at=observed_at,
                source_timezone="UTC",
                status="current",
                metadata_provenance={
                    "source_type": "human-confirmed",
                    "authority_level": "human-confirmed",
                    "official_status": "human-confirmed",
                    "published_at": "source-provided",
                    "validity": "not-provided",
                },
                semantic_tags={
                    "channel_id": str(value.get("id")),
                    "channel_username": username,
                    "message_id": str(message_id),
                    "raw_message_hash": raw_hash,
                    "normalized_content_hash": content_hash,
                    "text_entities": json.dumps(entities, ensure_ascii=False, sort_keys=True),
                    "links": json.dumps(_links(entities), ensure_ascii=False, sort_keys=True),
                    "media_references": json.dumps(media, ensure_ascii=False, sort_keys=True),
                    "forwarded_metadata": json.dumps(forwarded, ensure_ascii=False, sort_keys=True),
                    "reactions": json.dumps(reactions, ensure_ascii=False, sort_keys=True),
                    "authority_evidence": json.dumps(authority_evidence, sort_keys=True),
                    "normalizer_version": NORMALIZER_VERSION,
                },
            )
        )
    destination = Path(normalized_path).expanduser().absolute()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in normalized),
        encoding="utf-8",
    )
    destination.chmod(0o600)
    ordered_ids = sorted(
        all_ids,
        key=lambda item: (0, int(item)) if str(item).isdigit() else (1, str(item)),
    )
    aggregate = {
        "version": "blum-official-telegram-knowledge-v1",
        "normalizer_version": NORMALIZER_VERSION,
        "channel_name": value.get("name"),
        "channel_id": value.get("id"),
        "channel_type": value.get("type"),
        "canonical_username": username,
        "authority": "official",
        "authority_evidence": list(authority_evidence),
        "snapshot_sha256": hashlib.sha256(raw_snapshot).hexdigest(),
        "ordinary_message_count": ordinary_count,
        "knowledge_message_count": len(normalized),
        "textless_ordinary_message_count": textless_count,
        "service_event_count": service_count,
        "precise_timestamp_count": precise_count,
        "precise_timestamp_coverage": precise_count / ordinary_count if ordinary_count else 0.0,
        "first_ordinary_timestamp": (
            min(all_timestamps).isoformat().replace("+00:00", "Z")
            if all_timestamps
            else None
        ),
        "last_ordinary_timestamp": (
            max(all_timestamps).isoformat().replace("+00:00", "Z")
            if all_timestamps
            else None
        ),
        "source_message_id_range": {
            "minimum": ordered_ids[0] if ordered_ids else None,
            "maximum": ordered_ids[-1] if ordered_ids else None,
        },
        "language_counts": {
            language: sum(item["source_language"] == language for item in normalized)
            for language in sorted({item["source_language"] for item in normalized})
        },
        "message_hash_ledger": [
            {
                "message_id": item["message_id"],
                "raw_hash": item["raw_hash"],
                "normalized_content_hash": item["normalized_content_hash"],
            }
            for item in normalized
        ],
    }
    return AnnouncementPack(
        aggregate=aggregate,
        normalized_messages=tuple(normalized),
        source_inputs=tuple(source_inputs),
    )

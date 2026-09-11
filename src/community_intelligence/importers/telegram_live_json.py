"""Freeze complete chat objects from an incomplete Telegram Desktop JSON export.

The global Telegram export may still be appended after earlier chat objects are
fully closed. This module lexically follows the ``chats.list`` JSON structure,
captures only complete direct children, and never writes to the source file.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from community_intelligence.io import (
    cleanup_private_directory,
    publish_directory_no_replace,
    seal_staging_directory,
)

EXTRACTION_METHOD_VERSION = "telegram-live-json-chat-slice-v1.0.0"


class _IncompleteJSON(ValueError):
    pass


@dataclass(frozen=True)
class ChatFingerprint:
    name: str
    chat_id: object
    start_offset: int
    end_offset: int
    source_range_sha256: str
    raw_bytes: bytes
    value: dict[str, Any]


@dataclass(frozen=True)
class SourceObservation:
    captured_at: str
    source_size: int
    source_mtime_ns: int
    chats: dict[str, ChatFingerprint]


def _skip_space(data: bytes, index: int) -> int:
    while index < len(data) and data[index] in b" \t\r\n":
        index += 1
    return index


def _string_end(data: bytes, start: int) -> int:
    if start >= len(data) or data[start] != ord('"'):
        raise ValueError("expected JSON string")
    escaped = False
    index = start + 1
    while index < len(data):
        value = data[index]
        if escaped:
            escaped = False
        elif value == ord("\\"):
            escaped = True
        elif value == ord('"'):
            return index + 1
        index += 1
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
        index = start + 1
        in_string = False
        escaped = False
        while index < len(data):
            value = data[index]
            if in_string:
                if escaped:
                    escaped = False
                elif value == ord("\\"):
                    escaped = True
                elif value == ord('"'):
                    in_string = False
                index += 1
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
            index += 1
        raise _IncompleteJSON("incomplete JSON container")

    index = start
    while index < len(data) and data[index] not in b",]} \t\r\n":
        index += 1
    if index == start:
        raise ValueError("invalid JSON scalar")
    json.loads(data[start:index].decode("ascii"))
    return index


def _object_key_value_start(data: bytes, object_start: int, wanted_key: str) -> int:
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
        index = _value_end(data, value_start)
        index = _skip_space(data, index)
        if index >= len(data):
            raise _IncompleteJSON(f"object ended before key {wanted_key!r}")
        if data[index] == ord(","):
            index += 1
            continue
        if data[index] == ord("}"):
            raise ValueError(f"JSON object has no key {wanted_key!r}")
        raise ValueError("invalid JSON object separator")


def _complete_array_objects(data: bytes, array_start: int) -> list[tuple[int, int, dict[str, Any]]]:
    index = _skip_space(data, array_start)
    if index >= len(data) or data[index] != ord("["):
        raise ValueError("chats.list must be a JSON array")
    index += 1
    output: list[tuple[int, int, dict[str, Any]]] = []
    while True:
        index = _skip_space(data, index)
        if index >= len(data):
            return output
        if data[index] == ord("]"):
            return output
        start = index
        try:
            end = _value_end(data, start)
        except _IncompleteJSON:
            return output
        raw = data[start:end]
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
        if not isinstance(value, dict):
            raise ValueError("every chats.list item must be an object")
        output.append((start, end, value))
        index = _skip_space(data, end)
        if index >= len(data):
            return output
        if data[index] == ord(","):
            index += 1
            continue
        if data[index] == ord("]"):
            return output
        raise ValueError("invalid chats.list separator")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _read_stable_prefix(path: Path) -> tuple[bytes, os.stat_result]:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        remaining = before.st_size
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


def inspect_complete_chats(
    source_path: str | Path, target_names: dict[str, str]
) -> SourceObservation:
    """Read one bounded prefix and fingerprint complete requested chat objects."""

    source = Path(source_path).expanduser().resolve(strict=True)
    data, status = _read_stable_prefix(source)
    chats_start = _object_key_value_start(data, 0, "chats")
    list_start = _object_key_value_start(data, chats_start, "list")
    requested_by_name = {name: key for key, name in target_names.items()}
    if len(requested_by_name) != len(target_names):
        raise ValueError("target chat names must be unique")
    found: dict[str, ChatFingerprint] = {}
    for start, end, value in _complete_array_objects(data, list_start):
        name = value.get("name")
        if name not in requested_by_name:
            continue
        key = requested_by_name[str(name)]
        if key in found:
            raise ValueError(f"target chat {name!r} appeared more than once")
        messages = value.get("messages")
        if not isinstance(messages, list):
            raise ValueError(f"target chat {name!r} has no messages array")
        raw = data[start:end]
        found[key] = ChatFingerprint(
            name=str(name),
            chat_id=value.get("id"),
            start_offset=start,
            end_offset=end,
            source_range_sha256=hashlib.sha256(raw).hexdigest(),
            raw_bytes=raw,
            value=value,
        )
    missing = sorted(set(target_names) - set(found))
    if missing:
        raise ValueError(f"complete target chat object(s) not found: {', '.join(missing)}")
    return SourceObservation(
        captured_at=datetime.now(UTC).isoformat(timespec="seconds"),
        source_size=status.st_size,
        source_mtime_ns=status.st_mtime_ns,
        chats=found,
    )


def validate_stable_observations(observations: list[SourceObservation]) -> None:
    if len(observations) < 2:
        raise ValueError("at least two stability observations are required")
    first = observations[0]
    for observed in observations[1:]:
        if set(observed.chats) != set(first.chats):
            raise ValueError("target chat set changed between stability observations")
        for key, initial in first.chats.items():
            current = observed.chats[key]
            comparable = (
                initial.name,
                initial.chat_id,
                initial.start_offset,
                initial.end_offset,
                initial.source_range_sha256,
            )
            if comparable != (
                current.name,
                current.chat_id,
                current.start_offset,
                current.end_offset,
                current.source_range_sha256,
            ):
                raise ValueError(f"target chat {key!r} changed between stability observations")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def freeze_complete_chats(
    source_path: str | Path,
    target_names: dict[str, str],
    output_dir: str | Path,
    *,
    stability_checks: int = 2,
    stability_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    """Validate stable source slices and atomically publish parser-ready snapshots."""

    if stability_checks < 2:
        raise ValueError("stability_checks must be at least 2")
    if stability_interval_seconds < 0:
        raise ValueError("stability_interval_seconds must not be negative")
    source = Path(source_path).expanduser().resolve(strict=True)
    destination = Path(output_dir).expanduser().absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(destination):
        raise FileExistsError(f"output path already exists: {destination}")

    observations: list[SourceObservation] = []
    for index in range(stability_checks):
        observations.append(inspect_complete_chats(source, target_names))
        if index + 1 < stability_checks and stability_interval_seconds:
            time.sleep(stability_interval_seconds)
    validate_stable_observations(observations)
    selected = observations[-1]

    ordered_values = [selected.chats[key].value for key in target_names]
    combined = {"about": "Frozen Telegram Desktop chat subset", "chats": {"list": ordered_values}}
    combined_bytes = _json_bytes(combined)
    per_chat_bytes = {key: _json_bytes(selected.chats[key].value) for key in target_names}
    manifest: dict[str, Any] = {
        "source_path": str(source),
        "extraction_timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "extraction_method_version": EXTRACTION_METHOD_VERSION,
        "source_file_size_at_extraction": selected.source_size,
        "source_file_mtime_ns_at_extraction": selected.source_mtime_ns,
        "included_chats": [
            {
                "snapshot_key": key,
                "name": selected.chats[key].name,
                "id": selected.chats[key].chat_id,
                "source_byte_range": [
                    selected.chats[key].start_offset,
                    selected.chats[key].end_offset,
                ],
                "source_byte_range_sha256": selected.chats[key].source_range_sha256,
                "snapshot_sha256": hashlib.sha256(per_chat_bytes[key]).hexdigest(),
            }
            for key in target_names
        ],
        "snapshot_sha256": hashlib.sha256(combined_bytes).hexdigest(),
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
                    "chat_range_sha256": {
                        key: item.chats[key].source_range_sha256 for key in target_names
                    },
                }
                for item in observations
            ],
        },
    }

    staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix=f".{destination.name}.staging-"))
    identity = None
    try:
        (staging / "result.json").write_bytes(combined_bytes)
        for key, content in per_chat_bytes.items():
            child = staging / key
            child.mkdir()
            (child / "result.json").write_bytes(content)
        (staging / "provenance.json").write_bytes(_json_bytes(manifest))
        identity = seal_staging_directory(staging)
        publish_directory_no_replace(staging, destination, expected_identity=identity)
    except Exception:
        if identity is None:
            status = staging.stat()
            cleanup_private_directory(
                staging,
                expected_inode=status.st_ino,
                expected_device=status.st_dev,
            )
        else:
            cleanup_private_directory(staging, expected_identity=identity)
        raise
    return manifest

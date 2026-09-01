"""Validated local serialization for synthetic datasets."""

from __future__ import annotations

import csv
import ctypes
import errno
import hashlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from community_intelligence.models import (
    AnnotationRecord,
    CampaignRecord,
    ClaimRecord,
    DatasetManifest,
    MessageRecord,
    OutcomeRecord,
    SyntheticDataset,
)

DATA_ARTIFACT_NAMES = (
    "messages.jsonl",
    "campaigns.json",
    "claims.json",
    "outcomes.csv",
    "annotations.jsonl",
)
PUBLISHED_ARTIFACT_NAMES = frozenset((*DATA_ARTIFACT_NAMES, "manifest.json"))
_PUBLICATION_ERROR = (
    "complete dataset publication must contain exactly six artifacts; "
    "all must be regular non-symlink artifacts"
)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
_DIRECTORY_FLAGS = _READ_FLAGS | getattr(os, "O_DIRECTORY", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_RENAME_EXCL = 0x00000004
_RENAME_NOFOLLOW_ANY = 0x00000010
_RENAME_NOREPLACE = 0x00000001


@dataclass(frozen=True)
class _CapturedArtifact:
    content: bytes
    device: int
    inode: int
    size: int


def _json(value: Any, *, indent: int | None = None) -> str:
    return json.dumps(value, ensure_ascii=False, indent=indent, sort_keys=True)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _jsonl(records: list[Any]) -> str:
    return "".join(f"{_json(record.model_dump(mode='json'))}\n" for record in records)


def _outcomes_csv(outcomes: list[OutcomeRecord]) -> str:
    outcome_buffer = io.StringIO(newline="")
    fieldnames = list(OutcomeRecord.model_fields)
    writer = csv.DictWriter(outcome_buffer, fieldnames=fieldnames)
    writer.writeheader()
    for outcome in outcomes:
        writer.writerow(outcome.model_dump(mode="json"))
    return outcome_buffer.getvalue()


def data_artifact_contents(
    messages: list[MessageRecord],
    campaigns: list[CampaignRecord],
    claims: list[ClaimRecord],
    outcomes: list[OutcomeRecord],
    annotations: list[AnnotationRecord],
) -> dict[str, str]:
    """Serialize the five payload artifacts deterministically."""

    return {
        "messages.jsonl": _jsonl(messages),
        "campaigns.json": (
            _json([record.model_dump(mode="json") for record in campaigns], indent=2) + "\n"
        ),
        "claims.json": (
            _json([record.model_dump(mode="json") for record in claims], indent=2) + "\n"
        ),
        "outcomes.csv": _outcomes_csv(outcomes),
        "annotations.jsonl": _jsonl(annotations),
    }


def publication_metadata(dataset_id: str, contents: dict[str, str]) -> tuple[str, dict[str, str]]:
    """Return deterministic completion metadata for serialized payload artifacts."""

    checksums = {
        name: hashlib.sha256(contents[name].encode("utf-8")).hexdigest()
        for name in DATA_ARTIFACT_NAMES
    }
    return _generation_id(dataset_id, checksums), checksums


def _generation_id(dataset_id: str, checksums: dict[str, str]) -> str:
    generation_source = _json({"artifact_checksums": checksums, "dataset_id": dataset_id}).encode(
        "utf-8"
    )
    return hashlib.sha256(generation_source).hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, _DIRECTORY_FLAGS | _NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _raise_rename_error(error_number: int, destination_name: str) -> None:
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error_number, os.strerror(error_number), destination_name)
    raise OSError(error_number, os.strerror(error_number), destination_name)


def _rename_directory_no_replace(
    parent_fd: int, source_name: str, destination_name: str
) -> None:
    """Rename sibling directories atomically without replacing any destination."""

    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform == "darwin":
        renameatx_np = getattr(libc, "renameatx_np", None)
        if renameatx_np is None:
            raise OSError(
                errno.ENOTSUP,
                "atomic no-replace directory publication unsupported",
                destination_name,
            )
        renameatx_np.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameatx_np.restype = ctypes.c_int
        result = renameatx_np(
            parent_fd,
            source,
            parent_fd,
            destination,
            _RENAME_EXCL | _RENAME_NOFOLLOW_ANY,
        )
    elif sys.platform.startswith("linux"):
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise OSError(
                errno.ENOTSUP,
                "atomic no-replace directory publication unsupported",
                destination_name,
            )
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            parent_fd,
            source,
            parent_fd,
            destination,
            _RENAME_NOREPLACE,
        )
    else:
        raise OSError(
            errno.ENOTSUP,
            "atomic no-replace directory publication unsupported",
            destination_name,
        )
    if result != 0:
        _raise_rename_error(ctypes.get_errno(), destination_name)


def publish_directory_no_replace(staging_dir: str | Path, destination: str | Path) -> Path:
    """Atomically publish a complete sibling directory without clobbering."""

    staging_path = Path(os.path.abspath(Path(staging_dir).expanduser()))
    destination_path = Path(os.path.abspath(Path(destination).expanduser()))
    staging_parent = staging_path.parent.resolve(strict=True)
    destination_parent = destination_path.parent.resolve(strict=True)
    if staging_parent != destination_parent:
        raise ValueError("staging directory and destination must be siblings")
    staging_path = staging_parent / staging_path.name
    destination_path = destination_parent / destination_path.name
    parent_fd = os.open(staging_parent, _DIRECTORY_FLAGS | _NOFOLLOW)
    try:
        source_status = os.stat(staging_path.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(source_status.st_mode):
            raise ValueError("staging path must be a non-symlink directory")
        _rename_directory_no_replace(parent_fd, staging_path.name, destination_path.name)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return destination_path


def cleanup_private_directory(path: Path, *, expected_inode: int) -> None:
    """Remove only the unchanged, privately owned staging directory."""

    try:
        status = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISDIR(status.st_mode) and status.st_ino == expected_inode:
        shutil.rmtree(path)


def write_dataset(dataset: SyntheticDataset, output_dir: str | Path) -> Path:
    """Validate and publish all six artifacts as one directory generation."""

    requested_path = Path(os.path.abspath(Path(output_dir).expanduser()))
    dataset = SyntheticDataset.model_validate(dataset.model_dump(mode="python"))
    requested_path.parent.mkdir(parents=True, exist_ok=True)
    output_path = requested_path.parent.resolve(strict=True) / requested_path.name
    if os.path.lexists(output_path):
        raise FileExistsError(f"output path already exists: {output_path}")
    contents = data_artifact_contents(
        dataset.messages,
        dataset.campaigns,
        dataset.claims,
        dataset.outcomes,
        dataset.annotations,
    )
    generation_id, checksums = publication_metadata(dataset.manifest.dataset_id, contents)
    if dataset.manifest.generation_id != generation_id:
        raise ValueError("manifest generation_id does not match dataset artifacts")
    if dataset.manifest.artifact_checksums != checksums:
        raise ValueError("manifest artifact checksums do not match dataset artifacts")
    contents["manifest.json"] = _json(dataset.manifest.model_dump(mode="json"), indent=2) + "\n"

    staging_path = Path(
        tempfile.mkdtemp(dir=output_path.parent, prefix=f".{output_path.name}.staging-")
    )
    staging_inode = staging_path.lstat().st_ino
    try:
        for name in sorted(PUBLISHED_ARTIFACT_NAMES):
            _atomic_write_text(staging_path / name, contents[name])
        read_dataset(staging_path)
        _fsync_directory(staging_path)
        publish_directory_no_replace(staging_path, output_path)
    finally:
        cleanup_private_directory(staging_path, expected_inode=staging_inode)
    return output_path


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json_loads(content: str, source_name: str) -> Any:
    try:
        return json.loads(content, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid {source_name} JSON") from error


def _read_jsonl(content: str, source_name: str) -> list[dict[str, Any]]:
    return [
        _strict_json_loads(line, source_name)
        for line in content.splitlines()
        if line
    ]


def _read_manifest(content: str) -> DatasetManifest:
    value = _strict_json_loads(content, "manifest")
    return DatasetManifest.model_validate(value)


def _artifact_snapshot(directory_fd: int) -> dict[str, tuple[int, int, int]]:
    try:
        names = set(os.listdir(directory_fd))
    except OSError as error:
        raise ValueError(_PUBLICATION_ERROR) from error
    if names != PUBLISHED_ARTIFACT_NAMES:
        raise ValueError(_PUBLICATION_ERROR)
    snapshot: dict[str, tuple[int, int, int]] = {}
    for name in sorted(names):
        try:
            status = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as error:
            raise ValueError(_PUBLICATION_ERROR) from error
        if not stat.S_ISREG(status.st_mode):
            raise ValueError(_PUBLICATION_ERROR)
        snapshot[name] = (status.st_dev, status.st_ino, status.st_size)
    return snapshot


def _capture_artifact(directory_fd: int, name: str) -> _CapturedArtifact:
    flags = _READ_FLAGS | _NOFOLLOW
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as error:
        raise ValueError(_PUBLICATION_ERROR) from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(_PUBLICATION_ERROR)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        identity_before = (before.st_dev, before.st_ino, before.st_size)
        identity_after = (after.st_dev, after.st_ino, after.st_size)
        if identity_before != identity_after or len(content) != before.st_size:
            raise ValueError(f"artifact changed during capture: {name}")
        return _CapturedArtifact(
            content=content,
            device=before.st_dev,
            inode=before.st_ino,
            size=before.st_size,
        )
    finally:
        os.close(descriptor)


def _decode_artifact(captured: _CapturedArtifact, name: str) -> str:
    try:
        return captured.content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"invalid UTF-8 in {name}") from error


def read_dataset(input_dir: str | Path) -> SyntheticDataset:
    """Load all six artifacts and revalidate their records and references."""

    input_path = Path(input_dir).expanduser().resolve()
    if not input_path.is_dir():
        raise ValueError(_PUBLICATION_ERROR)
    try:
        directory_fd = os.open(input_path, _DIRECTORY_FLAGS | _NOFOLLOW)
    except OSError as error:
        raise ValueError(_PUBLICATION_ERROR) from error
    try:
        initial_snapshot = _artifact_snapshot(directory_fd)
        captured = {
            name: _capture_artifact(directory_fd, name)
            for name in sorted(PUBLISHED_ARTIFACT_NAMES)
        }
        final_snapshot = _artifact_snapshot(directory_fd)
        captured_snapshot = {
            name: (item.device, item.inode, item.size) for name, item in captured.items()
        }
        if final_snapshot != initial_snapshot or final_snapshot != captured_snapshot:
            raise ValueError("dataset artifacts changed during capture")
    finally:
        os.close(directory_fd)

    text = {name: _decode_artifact(item, name) for name, item in captured.items()}
    manifest = _read_manifest(text["manifest.json"])
    checksums = {
        name: hashlib.sha256(captured[name].content).hexdigest()
        for name in DATA_ARTIFACT_NAMES
    }
    if manifest.artifact_checksums != checksums:
        raise ValueError("artifact checksum mismatch")
    generation_id = _generation_id(manifest.dataset_id, checksums)
    if manifest.generation_id != generation_id:
        raise ValueError("generation identifier mismatch")
    messages = [
        MessageRecord.model_validate(row)
        for row in _read_jsonl(text["messages.jsonl"], "messages.jsonl")
    ]
    campaigns = [
        CampaignRecord.model_validate(row)
        for row in _strict_json_loads(text["campaigns.json"], "campaigns.json")
    ]
    claims = [
        ClaimRecord.model_validate(row)
        for row in _strict_json_loads(text["claims.json"], "claims.json")
    ]
    outcomes = [
        OutcomeRecord.model_validate(row)
        for row in csv.DictReader(io.StringIO(text["outcomes.csv"], newline=""))
    ]
    annotations = [
        AnnotationRecord.model_validate(row)
        for row in _read_jsonl(text["annotations.jsonl"], "annotations.jsonl")
    ]
    return SyntheticDataset(
        messages=messages,
        campaigns=campaigns,
        claims=claims,
        outcomes=outcomes,
        annotations=annotations,
        manifest=manifest,
    )

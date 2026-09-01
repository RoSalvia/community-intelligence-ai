"""Validated local serialization for synthetic datasets."""

from __future__ import annotations

import csv
import ctypes
import errno
import hashlib
import io
import json
import os
import secrets
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
    CommunityDataset,
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


@dataclass(frozen=True)
class DirectoryPublicationIdentity:
    """Immutable identity of a complete private directory generation."""

    device: int
    inode: int
    marker_name: str
    marker_token: str
    entries: tuple[tuple[str, str], ...]
    file_hashes: tuple[tuple[str, str], ...]


class PublicationIdentityError(RuntimeError):
    """Raised when a renamed directory is not the sealed staging generation."""

    def __init__(self, message: str, *, quarantine_path: Path | None = None) -> None:
        super().__init__(message)
        self.quarantine_path = quarantine_path


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


def _read_regular_file_at(directory_fd: int, name: str, expected: os.stat_result) -> bytes:
    descriptor = os.open(name, _READ_FLAGS | _NOFOLLOW, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        expected_key = (expected.st_dev, expected.st_ino, expected.st_size)
        before_key = (before.st_dev, before.st_ino, before.st_size)
        if not stat.S_ISREG(before.st_mode) or before_key != expected_key:
            raise PublicationIdentityError(f"directory entry changed during capture: {name}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        after_key = (after.st_dev, after.st_ino, after.st_size)
        if after_key != before_key or len(content) != before.st_size:
            raise PublicationIdentityError(f"directory entry changed during capture: {name}")
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino, current.st_size) != before_key:
            raise PublicationIdentityError(f"directory entry changed during capture: {name}")
        return content
    finally:
        os.close(descriptor)


def _snapshot_directory_fd(
    directory_fd: int,
    *,
    prefix: str = "",
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    entries: list[tuple[str, str]] = []
    hashes: list[tuple[str, str]] = []
    for name in sorted(os.listdir(directory_fd)):
        relative_name = f"{prefix}/{name}" if prefix else name
        status_before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISREG(status_before.st_mode):
            content = _read_regular_file_at(directory_fd, name, status_before)
            entries.append((relative_name, "file"))
            hashes.append((relative_name, hashlib.sha256(content).hexdigest()))
            continue
        if not stat.S_ISDIR(status_before.st_mode):
            raise PublicationIdentityError(
                f"sealed directory contains unsupported entry: {relative_name}"
            )
        child_fd = os.open(
            name,
            _DIRECTORY_FLAGS | _NOFOLLOW,
            dir_fd=directory_fd,
        )
        try:
            opened = os.fstat(child_fd)
            if (opened.st_dev, opened.st_ino) != (
                status_before.st_dev,
                status_before.st_ino,
            ):
                raise PublicationIdentityError(
                    f"directory entry changed during capture: {relative_name}"
                )
            child_entries, child_hashes = _snapshot_directory_fd(
                child_fd,
                prefix=relative_name,
            )
            status_after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (status_after.st_dev, status_after.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                raise PublicationIdentityError(
                    f"directory entry changed during capture: {relative_name}"
                )
        finally:
            os.close(child_fd)
        entries.append((relative_name, "directory"))
        entries.extend(child_entries)
        hashes.extend(child_hashes)
    return tuple(entries), tuple(hashes)


def _capture_directory_identity(
    directory_fd: int,
    *,
    marker_name: str,
    marker_token: str,
) -> DirectoryPublicationIdentity:
    root = os.fstat(directory_fd)
    if not stat.S_ISDIR(root.st_mode):
        raise PublicationIdentityError("staging path must be a non-symlink directory")
    entries, file_hashes = _snapshot_directory_fd(directory_fd)
    hash_by_name = dict(file_hashes)
    marker_hash = hashlib.sha256(marker_token.encode("utf-8")).hexdigest()
    if dict(entries).get(marker_name) != "file" or hash_by_name.get(marker_name) != marker_hash:
        raise PublicationIdentityError("staging ownership marker is missing or changed")
    return DirectoryPublicationIdentity(
        device=root.st_dev,
        inode=root.st_ino,
        marker_name=marker_name,
        marker_token=marker_token,
        entries=entries,
        file_hashes=file_hashes,
    )


def seal_staging_directory(staging_dir: str | Path) -> DirectoryPublicationIdentity:
    """Add an unguessable owner marker and capture the complete directory identity."""

    staging_path = Path(os.path.abspath(Path(staging_dir).expanduser()))
    parent = staging_path.parent.resolve(strict=True)
    parent_fd = os.open(parent, _DIRECTORY_FLAGS | _NOFOLLOW)
    try:
        directory_fd = os.open(
            staging_path.name,
            _DIRECTORY_FLAGS | _NOFOLLOW,
            dir_fd=parent_fd,
        )
        try:
            marker_token = secrets.token_hex(32)
            marker_name = f".community-intelligence-owner-{secrets.token_hex(16)}"
            marker_fd = os.open(
                marker_name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | _NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
            try:
                os.write(marker_fd, marker_token.encode("utf-8"))
                os.fsync(marker_fd)
            finally:
                os.close(marker_fd)
            os.fsync(directory_fd)
            return _capture_directory_identity(
                directory_fd,
                marker_name=marker_name,
                marker_token=marker_token,
            )
        finally:
            os.close(directory_fd)
    finally:
        os.close(parent_fd)


def _verify_directory_identity_fd(
    directory_fd: int,
    expected: DirectoryPublicationIdentity,
) -> None:
    observed = _capture_directory_identity(
        directory_fd,
        marker_name=expected.marker_name,
        marker_token=expected.marker_token,
    )
    if observed != expected:
        raise PublicationIdentityError("published directory identity does not match staging")


def _before_publish_rename_hook(
    parent_fd: int,
    source_name: str,
    destination_name: str,
    expected_identity: DirectoryPublicationIdentity,
) -> None:
    """Test seam at the strongest practical same-user race boundary."""


def _before_cleanup_delete_hook(
    parent_fd: int,
    quarantine_name: str,
    expected_identity: DirectoryPublicationIdentity | None,
) -> None:
    """Test seam after private quarantine and before verified deletion."""


def _unique_quarantine_name(original_name: str) -> str:
    return f".{original_name}.quarantine-{secrets.token_hex(16)}"


def _move_to_quarantine(
    parent_fd: int,
    source_name: str,
    *,
    parent_path: Path,
) -> Path:
    quarantine_name = _unique_quarantine_name(source_name)
    _rename_directory_no_replace(parent_fd, source_name, quarantine_name)
    os.fsync(parent_fd)
    return parent_path / quarantine_name


def _clear_directory_fd(directory_fd: int) -> bool:
    """Delete only entries that remain anchored to this open owned directory."""

    for name in sorted(os.listdir(directory_fd)):
        status = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(status.st_mode):
            child_fd = os.open(
                name,
                _DIRECTORY_FLAGS | _NOFOLLOW,
                dir_fd=directory_fd,
            )
            try:
                opened = os.fstat(child_fd)
                if (opened.st_dev, opened.st_ino) != (status.st_dev, status.st_ino):
                    return False
                if not _clear_directory_fd(child_fd):
                    return False
            finally:
                os.close(child_fd)
            current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (status.st_dev, status.st_ino):
                return False
            os.rmdir(name, dir_fd=directory_fd)
            continue
        if not stat.S_ISREG(status.st_mode):
            return False
        descriptor = os.open(name, _READ_FLAGS | _NOFOLLOW, dir_fd=directory_fd)
        try:
            opened = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (status.st_dev, status.st_ino) or (
            current.st_dev,
            current.st_ino,
        ) != (status.st_dev, status.st_ino):
            return False
        os.unlink(name, dir_fd=directory_fd)
    os.fsync(directory_fd)
    return True


def _remove_verified_quarantine(
    parent_fd: int,
    quarantine_name: str,
    *,
    expected_device: int | None,
    expected_inode: int,
    expected_identity: DirectoryPublicationIdentity | None,
) -> bool:
    try:
        directory_fd = os.open(
            quarantine_name,
            _DIRECTORY_FLAGS | _NOFOLLOW,
            dir_fd=parent_fd,
        )
    except FileNotFoundError:
        return False
    try:
        opened = os.fstat(directory_fd)
        if opened.st_ino != expected_inode or (
            expected_device is not None and opened.st_dev != expected_device
        ):
            return False
        if expected_identity is not None:
            try:
                _verify_directory_identity_fd(directory_fd, expected_identity)
            except PublicationIdentityError:
                return False
        if not _clear_directory_fd(directory_fd):
            return False
    finally:
        os.close(directory_fd)
    try:
        current = os.stat(quarantine_name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    if current.st_ino != expected_inode or (
        expected_device is not None and current.st_dev != expected_device
    ):
        return False
    os.rmdir(quarantine_name, dir_fd=parent_fd)
    os.fsync(parent_fd)
    return True


def publish_directory_no_replace(
    staging_dir: str | Path,
    destination: str | Path,
    *,
    expected_identity: DirectoryPublicationIdentity | None = None,
) -> Path:
    """Publish a sealed sibling directory and verify its identity after rename.

    The pre/post inode, marker, entry-set, and hash checks narrow same-user races,
    but cannot make hostile same-account mutation between syscalls impossible.
    """

    staging_path = Path(os.path.abspath(Path(staging_dir).expanduser()))
    destination_path = Path(os.path.abspath(Path(destination).expanduser()))
    staging_parent = staging_path.parent.resolve(strict=True)
    destination_parent = destination_path.parent.resolve(strict=True)
    if staging_parent != destination_parent:
        raise ValueError("staging directory and destination must be siblings")
    staging_path = staging_parent / staging_path.name
    destination_path = destination_parent / destination_path.name
    if expected_identity is None:
        expected_identity = seal_staging_directory(staging_path)
    parent_fd = os.open(staging_parent, _DIRECTORY_FLAGS | _NOFOLLOW)
    renamed = False
    try:
        source_fd = os.open(
            staging_path.name,
            _DIRECTORY_FLAGS | _NOFOLLOW,
            dir_fd=parent_fd,
        )
        try:
            _verify_directory_identity_fd(source_fd, expected_identity)
        finally:
            os.close(source_fd)
        _before_publish_rename_hook(
            parent_fd,
            staging_path.name,
            destination_path.name,
            expected_identity,
        )
        _rename_directory_no_replace(parent_fd, staging_path.name, destination_path.name)
        renamed = True
        os.fsync(parent_fd)
        destination_fd = os.open(
            destination_path.name,
            _DIRECTORY_FLAGS | _NOFOLLOW,
            dir_fd=parent_fd,
        )
        try:
            _verify_directory_identity_fd(destination_fd, expected_identity)
            os.unlink(expected_identity.marker_name, dir_fd=destination_fd)
            os.fsync(destination_fd)
            entries, file_hashes = _snapshot_directory_fd(destination_fd)
            expected_entries = tuple(
                entry
                for entry in expected_identity.entries
                if entry[0] != expected_identity.marker_name
            )
            expected_hashes = tuple(
                item
                for item in expected_identity.file_hashes
                if item[0] != expected_identity.marker_name
            )
            if entries != expected_entries or file_hashes != expected_hashes:
                raise PublicationIdentityError(
                    "published payload changed after ownership-marker removal"
                )
        finally:
            os.close(destination_fd)
    except (OSError, PublicationIdentityError) as error:
        if not renamed:
            raise
        quarantine_path: Path | None = None
        try:
            quarantine_path = _move_to_quarantine(
                parent_fd,
                destination_path.name,
                parent_path=destination_parent,
            )
        except OSError:
            quarantine_path = None
        detail = (
            f"; quarantined at {quarantine_path}"
            if quarantine_path is not None
            else "; destination was not removed because its current identity could not be isolated"
        )
        raise PublicationIdentityError(
            f"published directory failed identity verification{detail}",
            quarantine_path=quarantine_path,
        ) from error
    finally:
        os.close(parent_fd)
    return destination_path


def cleanup_private_directory(
    path: Path,
    *,
    expected_inode: int | None = None,
    expected_device: int | None = None,
    expected_identity: DirectoryPublicationIdentity | None = None,
) -> Path | None:
    """Quarantine, reverify, then delete only the captured private inode.

    A same-user process can still race individual syscalls. Root replacement is
    detected after quarantine and preserved rather than recursively deleted.
    """

    if expected_identity is not None:
        expected_inode = expected_identity.inode
        expected_device = expected_identity.device
    if expected_inode is None:
        raise TypeError("expected_inode or expected_identity is required")
    absolute = Path(os.path.abspath(path.expanduser()))
    try:
        parent = absolute.parent.resolve(strict=True)
    except FileNotFoundError:
        return None
    parent_fd = os.open(parent, _DIRECTORY_FLAGS | _NOFOLLOW)
    try:
        try:
            current = os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if not stat.S_ISDIR(current.st_mode) or current.st_ino != expected_inode or (
            expected_device is not None and current.st_dev != expected_device
        ):
            return absolute
        quarantine = _move_to_quarantine(
            parent_fd,
            absolute.name,
            parent_path=parent,
        )
        _before_cleanup_delete_hook(parent_fd, quarantine.name, expected_identity)
        removed = _remove_verified_quarantine(
            parent_fd,
            quarantine.name,
            expected_device=expected_device,
            expected_inode=expected_inode,
            expected_identity=expected_identity,
        )
        return None if removed else quarantine
    finally:
        os.close(parent_fd)


def write_dataset(dataset: CommunityDataset, output_dir: str | Path) -> Path:
    """Validate and publish all six artifacts as one directory generation."""

    requested_path = Path(os.path.abspath(Path(output_dir).expanduser()))
    dataset_type = SyntheticDataset if dataset.manifest.synthetic else CommunityDataset
    dataset = dataset_type.model_validate(dataset.model_dump(mode="python"))
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
    staging_status = staging_path.lstat()
    staging_identity: DirectoryPublicationIdentity | None = None
    try:
        for name in sorted(PUBLISHED_ARTIFACT_NAMES):
            _atomic_write_text(staging_path / name, contents[name])
        read_dataset(staging_path)
        _fsync_directory(staging_path)
        staging_identity = seal_staging_directory(staging_path)
        publish_directory_no_replace(
            staging_path,
            output_path,
            expected_identity=staging_identity,
        )
    finally:
        cleanup_private_directory(
            staging_path,
            expected_inode=staging_status.st_ino,
            expected_device=staging_status.st_dev,
            expected_identity=staging_identity,
        )
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


def read_dataset(input_dir: str | Path) -> CommunityDataset:
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
    dataset_type = SyntheticDataset if manifest.synthetic else CommunityDataset
    return dataset_type(
        messages=messages,
        campaigns=campaigns,
        claims=claims,
        outcomes=outcomes,
        annotations=annotations,
        manifest=manifest,
    )

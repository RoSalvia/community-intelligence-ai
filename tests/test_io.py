from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import pytest

import community_intelligence.io as dataset_io
from community_intelligence.io import (
    publish_directory_no_replace,
    read_dataset,
    write_dataset,
)
from community_intelligence.synthetic import generate_dataset


def _dataset(tmp_path: Path) -> Path:
    return write_dataset(generate_dataset(message_count=120), tmp_path / "dataset")


@pytest.mark.parametrize("extra_kind", ["file", "directory", "nested_directory", "symlink"])
def test_read_dataset_rejects_every_extra_filesystem_entry(tmp_path: Path, extra_kind: str) -> None:
    dataset = _dataset(tmp_path)
    extra = dataset / "extra"
    if extra_kind == "file":
        extra.write_text("junk", encoding="utf-8")
    elif extra_kind == "directory":
        extra.mkdir()
    elif extra_kind == "nested_directory":
        extra.mkdir()
        (extra / "nested-junk").write_text("junk", encoding="utf-8")
    else:
        extra.symlink_to(tmp_path / "missing-target")

    with pytest.raises(ValueError, match="regular non-symlink artifacts"):
        read_dataset(dataset)


@pytest.mark.parametrize("wrong_kind", ["directory", "symlink"])
def test_read_dataset_rejects_wrong_artifact_type(tmp_path: Path, wrong_kind: str) -> None:
    dataset = _dataset(tmp_path)
    artifact = dataset / "messages.jsonl"
    outside = tmp_path / "original-messages.jsonl"
    artifact.rename(outside)
    if wrong_kind == "directory":
        artifact.mkdir()
    else:
        artifact.symlink_to(outside)

    with pytest.raises(ValueError, match="regular non-symlink artifacts"):
        read_dataset(dataset)


def test_read_dataset_rejects_swap_to_symlink_without_parsing_reopened_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = _dataset(tmp_path)
    attacker = tmp_path / "attacker-claims.json"
    attacker.write_text(
        json.dumps(
            [
                {
                    "claim_id": "stake_reward",
                    "campaign_id": "campaign_stake",
                    "claim_text": "UN checksummed attacker content",
                    "importance": "critical",
                }
            ]
        ),
        encoding="utf-8",
    )
    real_capture = dataset_io._capture_artifact
    real_loads = dataset_io._strict_json_loads
    parsed_sources: list[str] = []

    def capture_and_swap(directory_fd: int, name: str):
        captured = real_capture(directory_fd, name)
        if name == "claims.json":
            os.rename(
                "claims.json",
                "claims.original",
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            os.symlink(attacker, "claims.json", dir_fd=directory_fd)
        return captured

    def record_parse(content: str, source_name: str):
        parsed_sources.append(content)
        return real_loads(content, source_name)

    monkeypatch.setattr(dataset_io, "_capture_artifact", capture_and_swap)
    monkeypatch.setattr(dataset_io, "_strict_json_loads", record_parse)

    with pytest.raises(ValueError, match="changed during capture|regular non-symlink"):
        read_dataset(dataset)
    assert parsed_sources == []


@pytest.mark.parametrize("existing_kind", ["file", "directory", "symlink"])
def test_publish_directory_no_replace_preserves_every_existing_destination(
    tmp_path: Path, existing_kind: str
) -> None:
    staging = tmp_path / "private-staging"
    staging.mkdir()
    (staging / "complete.txt").write_text("complete", encoding="utf-8")
    destination = tmp_path / "published"
    if existing_kind == "file":
        destination.write_text("keep", encoding="utf-8")
    elif existing_kind == "directory":
        destination.mkdir()
        (destination / "keep.txt").write_text("keep", encoding="utf-8")
    else:
        destination.symlink_to(tmp_path / "missing-target")
    before = destination.lstat()

    with pytest.raises(FileExistsError):
        publish_directory_no_replace(staging, destination)

    assert destination.lstat().st_ino == before.st_ino
    assert staging.is_dir()
    if existing_kind == "file":
        assert destination.read_text(encoding="utf-8") == "keep"
    elif existing_kind == "directory":
        assert (destination / "keep.txt").read_text(encoding="utf-8") == "keep"
    else:
        assert destination.is_symlink()


@pytest.mark.parametrize("race_kind", ["file", "directory", "symlink"])
def test_write_dataset_concurrent_destination_creation_never_publishes_partial_or_deletes_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, race_kind: str
) -> None:
    destination = tmp_path / "dataset"
    real_rename = dataset_io._rename_directory_no_replace

    def create_racer(parent_fd: int, source_name: str, destination_name: str) -> None:
        if race_kind == "file":
            descriptor = os.open(
                destination_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=parent_fd,
            )
            os.write(descriptor, b"racer")
            os.close(descriptor)
        elif race_kind == "directory":
            os.mkdir(destination_name, dir_fd=parent_fd)
        else:
            os.symlink("missing-target", destination_name, dir_fd=parent_fd)
        real_rename(parent_fd, source_name, destination_name)

    monkeypatch.setattr(dataset_io, "_rename_directory_no_replace", create_racer)

    with pytest.raises(FileExistsError):
        write_dataset(generate_dataset(message_count=120), destination)

    assert os.path.lexists(destination)
    assert not list(tmp_path.glob(".dataset.staging-*"))
    if race_kind == "file":
        assert destination.read_bytes() == b"racer"
    elif race_kind == "directory":
        assert list(destination.iterdir()) == []
    else:
        assert destination.is_symlink()


def test_publish_directory_no_replace_fails_safely_when_platform_primitive_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "private-staging"
    staging.mkdir()
    destination = tmp_path / "published"

    def unsupported(parent_fd: int, source_name: str, destination_name: str) -> None:
        raise OSError(errno.ENOTSUP, "atomic no-replace directory publication unsupported")

    monkeypatch.setattr(dataset_io, "_rename_directory_no_replace", unsupported)

    with pytest.raises(OSError, match="unsupported"):
        publish_directory_no_replace(staging, destination)
    assert staging.is_dir()
    assert not os.path.lexists(destination)

from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import pytest

import community_intelligence.io as dataset_io
from community_intelligence.io import (
    PublicationIdentityError,
    cleanup_private_directory,
    data_artifact_contents,
    publication_metadata,
    publish_directory_no_replace,
    read_dataset,
    seal_staging_directory,
    write_dataset,
)
from community_intelligence.models import CommunityDataset
from community_intelligence.synthetic import generate_dataset


def _dataset(tmp_path: Path) -> Path:
    return write_dataset(generate_dataset(message_count=120), tmp_path / "dataset")


def test_write_and_read_production_community_only_dataset(tmp_path: Path) -> None:
    source = generate_dataset(message_count=120)
    messages = [message.model_copy(update={"campaign_id": None}) for message in source.messages]
    contents = data_artifact_contents(messages, [], [], [], [])
    generation_id, checksums = publication_metadata("telegram-production", contents)
    dataset = CommunityDataset(
        messages=messages,
        campaigns=[],
        claims=[],
        outcomes=[],
        annotations=[],
        manifest=source.manifest.model_copy(
            update={
                "dataset_id": "telegram-production",
                "synthetic": False,
                "seed": None,
                "campaign_ids": [],
                "scenarios": {},
                "generation_id": generation_id,
                "artifact_checksums": checksums,
                "source_format": "telegram_desktop_json",
                "source_sha256": "a" * 64,
            }
        ),
    )

    output = write_dataset(dataset, tmp_path / "production")
    loaded = read_dataset(output)

    assert type(loaded) is CommunityDataset
    assert loaded == dataset


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

    def create_racer(
        parent_fd: int,
        source_name: str,
        destination_name: str,
        expected_identity: object,
    ) -> None:
        del source_name, expected_identity
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

    monkeypatch.setattr(dataset_io, "_before_publish_rename_hook", create_racer)

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


def test_publish_directory_pins_marker_inode_and_complete_content_identity(
    tmp_path: Path,
) -> None:
    staging = tmp_path / "private-staging"
    staging.mkdir()
    (staging / "complete.txt").write_text("complete", encoding="utf-8")
    identity = seal_staging_directory(staging)

    assert identity.marker_name.startswith(".community-intelligence-owner-")
    assert len(identity.marker_token) >= 32
    assert (staging / identity.marker_name).read_text(encoding="utf-8") == (
        identity.marker_token
    )
    assert identity.device == staging.lstat().st_dev
    assert identity.inode == staging.lstat().st_ino
    assert ("complete.txt", "file") in identity.entries
    assert any(name == "complete.txt" for name, _digest in identity.file_hashes)

    destination = publish_directory_no_replace(
        staging,
        tmp_path / "published",
        expected_identity=identity,
    )

    assert sorted(path.name for path in destination.iterdir()) == ["complete.txt"]
    assert (destination / "complete.txt").read_text(encoding="utf-8") == "complete"


def test_publish_quarantines_replaced_staging_without_deleting_attacker_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "private-staging"
    staging.mkdir()
    (staging / "complete.txt").write_text("owned", encoding="utf-8")
    identity = seal_staging_directory(staging)
    owned_relocated = tmp_path / "owned-relocated"

    def replace_after_prevalidation(
        parent_fd: int,
        source_name: str,
        destination_name: str,
        expected_identity: object,
    ) -> None:
        del destination_name, expected_identity
        os.rename(
            source_name,
            owned_relocated.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.mkdir(source_name, dir_fd=parent_fd)
        attacker_fd = os.open(
            source_name,
            os.O_RDONLY | os.O_DIRECTORY,
            dir_fd=parent_fd,
        )
        try:
            descriptor = os.open(
                "attacker.txt",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=attacker_fd,
            )
            try:
                os.write(descriptor, b"attacker survives")
            finally:
                os.close(descriptor)
        finally:
            os.close(attacker_fd)

    monkeypatch.setattr(
        dataset_io,
        "_before_publish_rename_hook",
        replace_after_prevalidation,
    )

    with pytest.raises(PublicationIdentityError, match="quarantine") as caught:
        publish_directory_no_replace(
            staging,
            tmp_path / "published",
            expected_identity=identity,
        )

    assert not os.path.lexists(tmp_path / "published")
    assert caught.value.quarantine_path is not None
    assert (caught.value.quarantine_path / "attacker.txt").read_bytes() == (
        b"attacker survives"
    )
    assert (owned_relocated / "complete.txt").read_text(encoding="utf-8") == "owned"


def test_publish_quarantines_non_directory_replacement_after_successful_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "private-staging"
    staging.mkdir()
    (staging / "complete.txt").write_text("owned", encoding="utf-8")
    identity = seal_staging_directory(staging)
    owned_relocated = tmp_path / "owned-relocated"

    def replace_with_file(
        parent_fd: int,
        source_name: str,
        destination_name: str,
        expected_identity: object,
    ) -> None:
        del destination_name, expected_identity
        os.rename(
            source_name,
            owned_relocated.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        descriptor = os.open(
            source_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=parent_fd,
        )
        try:
            os.write(descriptor, b"attacker file survives")
        finally:
            os.close(descriptor)

    monkeypatch.setattr(dataset_io, "_before_publish_rename_hook", replace_with_file)

    with pytest.raises(PublicationIdentityError, match="quarantine") as caught:
        publish_directory_no_replace(
            staging,
            tmp_path / "published",
            expected_identity=identity,
        )

    assert not os.path.lexists(tmp_path / "published")
    assert caught.value.quarantine_path is not None
    assert caught.value.quarantine_path.read_bytes() == b"attacker file survives"
    assert (owned_relocated / "complete.txt").read_text(encoding="utf-8") == "owned"


def test_cleanup_quarantines_then_preserves_replacement_if_owned_path_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "private-staging"
    staging.mkdir()
    (staging / "complete.txt").write_text("owned", encoding="utf-8")
    identity = seal_staging_directory(staging)
    owned_relocated = tmp_path / "owned-cleanup-relocated"
    observed_quarantine: list[Path] = []

    def replace_before_delete(
        parent_fd: int,
        quarantine_name: str,
        expected_identity: object,
    ) -> None:
        del expected_identity
        quarantine = tmp_path / quarantine_name
        observed_quarantine.append(quarantine)
        os.rename(
            quarantine_name,
            owned_relocated.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.mkdir(quarantine_name, dir_fd=parent_fd)
        (quarantine / "replacement.txt").write_text("keep me", encoding="utf-8")

    monkeypatch.setattr(
        dataset_io,
        "_before_cleanup_delete_hook",
        replace_before_delete,
    )

    retained = cleanup_private_directory(staging, expected_identity=identity)

    assert retained == observed_quarantine[0]
    assert (retained / "replacement.txt").read_text(encoding="utf-8") == "keep me"
    assert (owned_relocated / "complete.txt").read_text(encoding="utf-8") == "owned"
    assert not os.path.lexists(staging)

from __future__ import annotations

from pathlib import Path

import pytest

from community_intelligence.io import read_dataset, write_dataset
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

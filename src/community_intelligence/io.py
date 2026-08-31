"""Validated local serialization for synthetic datasets."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import tempfile
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
    generation_source = _json(
        {"artifact_checksums": checksums, "dataset_id": dataset_id}
    ).encode("utf-8")
    return hashlib.sha256(generation_source).hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_dataset(dataset: SyntheticDataset, output_dir: str | Path) -> Path:
    """Validate and publish all six artifacts as one directory generation."""

    output_path = Path(os.path.abspath(Path(output_dir).expanduser()))
    if os.path.lexists(output_path):
        raise FileExistsError(f"output path already exists: {output_path}")
    dataset = SyntheticDataset.model_validate(dataset.model_dump(mode="python"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
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
    contents["manifest.json"] = (
        _json(dataset.manifest.model_dump(mode="json"), indent=2) + "\n"
    )

    staging_path = Path(
        tempfile.mkdtemp(dir=output_path.parent, prefix=f".{output_path.name}.staging-")
    )
    try:
        for name in sorted(PUBLISHED_ARTIFACT_NAMES):
            _atomic_write_text(staging_path / name, contents[name])
        read_dataset(staging_path)
        _fsync_directory(staging_path)
        if os.path.lexists(output_path):
            raise FileExistsError(f"output path already exists: {output_path}")
        os.rename(staging_path, output_path)
        _fsync_directory(output_path.parent)
    finally:
        if staging_path.exists():
            shutil.rmtree(staging_path)
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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        _strict_json_loads(line, path.name)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _read_manifest(path: Path) -> DatasetManifest:
    value = _strict_json_loads(path.read_text(encoding="utf-8"), "manifest")
    return DatasetManifest.model_validate(value)


def read_dataset(input_dir: str | Path) -> SyntheticDataset:
    """Load all six artifacts and revalidate their records and references."""

    input_path = Path(input_dir).expanduser().resolve()
    published_names = {path.name for path in input_path.iterdir() if path.is_file()}
    if published_names != PUBLISHED_ARTIFACT_NAMES:
        raise ValueError("complete dataset publication must contain exactly six artifacts")
    manifest = _read_manifest(input_path / "manifest.json")
    checksums = {
        name: hashlib.sha256((input_path / name).read_bytes()).hexdigest()
        for name in DATA_ARTIFACT_NAMES
    }
    if manifest.artifact_checksums != checksums:
        raise ValueError("artifact checksum mismatch")
    generation_id = _generation_id(manifest.dataset_id, checksums)
    if manifest.generation_id != generation_id:
        raise ValueError("generation identifier mismatch")
    messages = [
        MessageRecord.model_validate(row)
        for row in _read_jsonl(input_path / "messages.jsonl")
    ]
    campaigns = [
        CampaignRecord.model_validate(row)
        for row in _strict_json_loads(
            (input_path / "campaigns.json").read_text(encoding="utf-8"),
            "campaigns.json",
        )
    ]
    claims = [
        ClaimRecord.model_validate(row)
        for row in _strict_json_loads(
            (input_path / "claims.json").read_text(encoding="utf-8"),
            "claims.json",
        )
    ]
    with (input_path / "outcomes.csv").open(encoding="utf-8", newline="") as handle:
        outcomes = [OutcomeRecord.model_validate(row) for row in csv.DictReader(handle)]
    annotations = [
        AnnotationRecord.model_validate(row)
        for row in _read_jsonl(input_path / "annotations.jsonl")
    ]
    return SyntheticDataset(
        messages=messages,
        campaigns=campaigns,
        claims=claims,
        outcomes=outcomes,
        annotations=annotations,
        manifest=manifest,
    )

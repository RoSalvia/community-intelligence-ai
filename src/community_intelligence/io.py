"""Validated local serialization for synthetic datasets."""

from __future__ import annotations

import csv
import io
import json
import os
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


def write_dataset(dataset: SyntheticDataset, output_dir: str | Path) -> Path:
    """Write the six validated dataset artifacts using replace-on-complete files."""

    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    _atomic_write_text(output_path / "messages.jsonl", _jsonl(dataset.messages))
    _atomic_write_text(
        output_path / "campaigns.json",
        _json([record.model_dump(mode="json") for record in dataset.campaigns], indent=2) + "\n",
    )
    _atomic_write_text(
        output_path / "claims.json",
        _json([record.model_dump(mode="json") for record in dataset.claims], indent=2) + "\n",
    )

    outcome_buffer = io.StringIO(newline="")
    fieldnames = list(OutcomeRecord.model_fields)
    writer = csv.DictWriter(outcome_buffer, fieldnames=fieldnames)
    writer.writeheader()
    for outcome in dataset.outcomes:
        writer.writerow(outcome.model_dump(mode="json"))
    _atomic_write_text(output_path / "outcomes.csv", outcome_buffer.getvalue())

    _atomic_write_text(output_path / "annotations.jsonl", _jsonl(dataset.annotations))
    _atomic_write_text(
        output_path / "manifest.json",
        _json(dataset.manifest.model_dump(mode="json"), indent=2) + "\n",
    )
    return output_path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def read_dataset(input_dir: str | Path) -> SyntheticDataset:
    """Load all six artifacts and revalidate their records and references."""

    input_path = Path(input_dir).expanduser().resolve()
    messages = [
        MessageRecord.model_validate(row)
        for row in _read_jsonl(input_path / "messages.jsonl")
    ]
    campaigns = [
        CampaignRecord.model_validate(row)
        for row in json.loads((input_path / "campaigns.json").read_text(encoding="utf-8"))
    ]
    claims = [
        ClaimRecord.model_validate(row)
        for row in json.loads((input_path / "claims.json").read_text(encoding="utf-8"))
    ]
    with (input_path / "outcomes.csv").open(encoding="utf-8", newline="") as handle:
        outcomes = [OutcomeRecord.model_validate(row) for row in csv.DictReader(handle)]
    annotations = [
        AnnotationRecord.model_validate(row)
        for row in _read_jsonl(input_path / "annotations.jsonl")
    ]
    manifest = DatasetManifest.model_validate_json(
        (input_path / "manifest.json").read_text(encoding="utf-8")
    )
    return SyntheticDataset(
        messages=messages,
        campaigns=campaigns,
        claims=claims,
        outcomes=outcomes,
        annotations=annotations,
        manifest=manifest,
    )

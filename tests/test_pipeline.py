from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from community_intelligence.io import read_dataset, write_dataset
from community_intelligence.models import MessageRecord, SyntheticDataset
from community_intelligence.pipeline import _select_cluster_count, run_pipeline
from community_intelligence.synthetic import generate_dataset


def _dataset(tmp_path: Path, *, annotations: bool = True) -> Path:
    dataset = generate_dataset(message_count=120)
    if not annotations:
        dataset = SyntheticDataset(
            messages=dataset.messages,
            campaigns=dataset.campaigns,
            claims=dataset.claims,
            outcomes=dataset.outcomes,
            annotations=[],
            manifest=dataset.manifest.model_copy(
                update={
                    "artifact_checksums": {
                        **dataset.manifest.artifact_checksums,
                        "annotations.jsonl": hashlib.sha256(b"").hexdigest(),
                    }
                }
            ),
        )
        from community_intelligence.io import data_artifact_contents, publication_metadata

        generation_id, checksums = publication_metadata(
            dataset.manifest.dataset_id,
            data_artifact_contents(
                dataset.messages,
                dataset.campaigns,
                dataset.claims,
                dataset.outcomes,
                dataset.annotations,
            ),
        )
        dataset = SyntheticDataset(
            **{
                **dataset.model_dump(mode="python"),
                "manifest": dataset.manifest.model_copy(
                    update={"generation_id": generation_id, "artifact_checksums": checksums}
                ),
            }
        )
    return write_dataset(dataset, tmp_path / "dataset")


def _read_report(output: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    evidence = [
        json.loads(line)
        for line in (output / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    return report, evidence


def _evidence_references(value: object) -> set[str]:
    references: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_ids":
                references.update(item)
            else:
                references.update(_evidence_references(item))
    elif isinstance(value, list):
        for item in value:
            references.update(_evidence_references(item))
    return references


def test_pipeline_is_deterministic_evidence_linked_and_does_not_mutate_source(
    tmp_path: Path,
) -> None:
    dataset_dir = _dataset(tmp_path)
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in dataset_dir.iterdir()
    }

    first = run_pipeline(dataset_dir, tmp_path / "report-a")
    second = run_pipeline(dataset_dir, tmp_path / "report-b")

    assert (first / "report.json").read_bytes() == (second / "report.json").read_bytes()
    assert (first / "evidence.jsonl").read_bytes() == (second / "evidence.jsonl").read_bytes()
    assert before == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in dataset_dir.iterdir()
    }

    report, evidence = _read_report(first)
    assert report["data_status"] == "synthetic"
    assert report["limitations"]["general_multilingual_semantic_ai"] == "Not implemented"
    assert "moderator_score" not in json.dumps(report).lower()
    assert len(report["Campaign"]["judgments"]) == 28
    assert report["Campaign"]["resource_source"] == (
        "explicit synthetic constants independent of annotations"
    )
    assert len(report["Metric Lab"]["observations"]) == 12
    assert len(report["Metric Lab"]["metric_records"]) == 120
    assert {item["status"] for item in report["Metric Lab"]["validation"]} <= {
        "Candidate",
        "Promising",
        "Rejected",
    }
    propagation = report["Metric Lab"]["pipeline_contracts"]["conversation_propagation_depth"]
    assert propagation["formula"] == (
        "sum episode longest-path message-node counts / conversation episodes"
    )

    evidence_ids = [item["evidence_id"] for item in evidence]
    assert len(evidence_ids) == len(set(evidence_ids))
    assert _evidence_references(report) == set(evidence_ids)
    messages = {message.message_id: message for message in read_dataset(dataset_dir).messages}
    for item in evidence:
        if item["message_id"] is not None:
            assert item["source_text"] == messages[item["message_id"]].text


def test_pipeline_does_not_depend_on_annotations(tmp_path: Path) -> None:
    dataset_dir = _dataset(tmp_path, annotations=False)
    output = run_pipeline(dataset_dir, tmp_path / "report")
    report, evidence = _read_report(output)
    serialized = json.dumps([report, evidence], ensure_ascii=False)
    assert "expected_behaviors" not in serialized
    assert "expected_claim_status" not in serialized
    assert "expected_question_status" not in serialized


@pytest.mark.parametrize("existing_kind", ["file", "directory", "symlink"])
def test_pipeline_refuses_every_existing_output_kind(tmp_path: Path, existing_kind: str) -> None:
    dataset_dir = _dataset(tmp_path)
    output = tmp_path / "report"
    if existing_kind == "file":
        output.write_text("keep", encoding="utf-8")
    elif existing_kind == "directory":
        output.mkdir()
    else:
        output.symlink_to(tmp_path / "missing-target")

    with pytest.raises(FileExistsError):
        run_pipeline(dataset_dir, output)
    assert os.path.lexists(output)


def test_pipeline_rejects_missing_or_tampered_source(tmp_path: Path) -> None:
    missing = _dataset(tmp_path / "missing")
    (missing / "claims.json").unlink()
    with pytest.raises(ValueError, match="six artifacts"):
        run_pipeline(missing, tmp_path / "missing-report")

    tampered = _dataset(tmp_path / "tampered")
    with (tampered / "messages.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    with pytest.raises(ValueError, match="checksum"):
        run_pipeline(tampered, tmp_path / "tampered-report")


def test_pipeline_cleans_staging_and_reserved_output_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset_dir = _dataset(tmp_path)
    output = tmp_path / "report"
    import community_intelligence.pipeline as pipeline

    calls = 0
    real_write = pipeline._write_text

    def fail_second(path: Path, content: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic write failure")
        real_write(path, content)

    monkeypatch.setattr(pipeline, "_write_text", fail_second)
    with pytest.raises(OSError, match="synthetic write failure"):
        run_pipeline(dataset_dir, output)
    assert not os.path.lexists(output)
    assert not list(tmp_path.glob(".report.staging-*"))


def test_pipeline_preserves_undefined_metric_rows(tmp_path: Path) -> None:
    output = run_pipeline(_dataset(tmp_path), tmp_path / "report")
    report, _ = _read_report(output)
    organic = [
        row
        for row in report["Metric Lab"]["metric_records"]
        if row["metric_name"] == "organic_project_mention_rate"
    ]
    assert len(organic) == 12
    assert all(row["value"] is None for row in organic)
    assert all(row["diagnostic"] == "zero_denominator" for row in organic)


def test_cluster_selection_degrades_for_a_tiny_tokenless_vector_space() -> None:
    message = MessageRecord(
        message_id="msg_small",
        community_id="community_small",
        language="en",
        user_id_hash="usr_abcdef",
        user_role="user",
        timestamp=datetime(2026, 9, 1, tzinfo=UTC),
        text="a",
        reply_to_message_id=None,
        campaign_id=None,
    )
    assert _select_cluster_count([message]) == 0

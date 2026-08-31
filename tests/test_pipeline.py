from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from community_intelligence.io import (
    data_artifact_contents,
    publication_metadata,
    read_dataset,
    write_dataset,
)
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


def _silent_scope_dataset(
    tmp_path: Path,
    *,
    campaign_id: str = "campaign_stake",
    community_id: str = "community_a",
) -> Path:
    source = generate_dataset(message_count=120)
    messages = [
        message
        for message in source.messages
        if not (
            message.campaign_id == campaign_id
            and message.community_id == community_id
        )
    ]
    message_ids = {message.message_id for message in messages}
    annotations = [
        annotation
        for annotation in source.annotations
        if annotation.message_id in message_ids
    ]
    generation_id, checksums = publication_metadata(
        source.manifest.dataset_id,
        data_artifact_contents(
            messages,
            source.campaigns,
            source.claims,
            source.outcomes,
            annotations,
        ),
    )
    dataset = SyntheticDataset(
        messages=messages,
        campaigns=source.campaigns,
        claims=source.claims,
        outcomes=source.outcomes,
        annotations=annotations,
        manifest=source.manifest.model_copy(
            update={
                "message_count": len(messages),
                "generation_id": generation_id,
                "artifact_checksums": checksums,
            }
        ),
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


def _source_snapshot(root: Path) -> dict[str, tuple[int, str | None, str | None]]:
    snapshot: dict[str, tuple[int, str | None, str | None]] = {}
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        mode = stat.S_IFMT(entry.lstat().st_mode)
        target = os.readlink(entry) if entry.is_symlink() else None
        digest = hashlib.sha256(entry.read_bytes()).hexdigest() if entry.is_file() else None
        snapshot[entry.name] = (mode, target, digest)
    return snapshot


def test_pipeline_is_deterministic_evidence_linked_and_does_not_mutate_source(
    tmp_path: Path,
) -> None:
    dataset_dir = _dataset(tmp_path)
    before = _source_snapshot(dataset_dir)

    first = run_pipeline(dataset_dir, tmp_path / "report-a")
    second = run_pipeline(dataset_dir, tmp_path / "report-b")

    assert (first / "report.json").read_bytes() == (second / "report.json").read_bytes()
    assert (first / "evidence.jsonl").read_bytes() == (second / "evidence.jsonl").read_bytes()
    assert before == _source_snapshot(dataset_dir)

    report, evidence = _read_report(first)
    assert report["data_status"] == "synthetic"
    assert report["capabilities"] == {
        "general_multilingual_semantic_campaign_judgment": "Not implemented",
        "llm_behavior_interpretation": "Not implemented",
        "multilingual_embedding_retrieval_provider": "Implemented and verified offline",
        "pipeline_semantic_retrieval_integration": "Not implemented",
    }
    assert report["analysis_methods"]["campaign"] == "curated_alias_baseline"
    assert report["analysis_methods"]["semantic_provider_used_by_pipeline"] is False
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


def test_every_metric_record_has_auditable_evidence_with_specialized_routing(
    tmp_path: Path,
) -> None:
    dataset_dir = _dataset(tmp_path)
    output = run_pipeline(dataset_dir, tmp_path / "report")
    report, evidence = _read_report(output)
    evidence_by_id = {item["evidence_id"]: item for item in evidence}
    dataset = read_dataset(dataset_dir)
    message_ids = {message.message_id for message in dataset.messages}
    claim_ids = {claim.claim_id for claim in dataset.claims}
    campaign_ids = {campaign.campaign_id for campaign in dataset.campaigns}
    community_ids = set(dataset.manifest.community_ids)

    records = report["Metric Lab"]["metric_records"]
    assert len(records) == 120
    assert all(record["evidence_ids"] for record in records)
    for record in records:
        linked = [evidence_by_id[evidence_id] for evidence_id in record["evidence_ids"]]
        assert all(item["campaign_id"] == record["campaign_id"] for item in linked)
        assert all(item["community_id"] == record["community_id"] for item in linked)
        assert sum(item["evidence_type"] == "analysis_scope" for item in linked) == 1

    campaign_records = [
        record for record in records if record["metric_name"] == "campaign_discussion_share"
    ]
    for record in campaign_records:
        methods = {
            evidence_by_id[evidence_id]["method"]
            for evidence_id in record["evidence_ids"]
        }
        assert methods == {
            "analysis_scope_v1",
            "metric:campaign_discussion_share:campaign_message",
        }

    organic_records = [
        record for record in records if record["metric_name"] == "organic_project_mention_rate"
    ]
    assert all(record["evidence_ids"] for record in organic_records)
    assert {
        evidence_by_id[evidence_id]["method"]
        for record in organic_records
        for evidence_id in record["evidence_ids"]
    } == {
        "analysis_scope_v1",
        "metric:organic_project_mention_rate:zero_denominator_scope",
    }

    semantic_records = [
        record
        for record in records
        if record["metric_name"] in {"semantic_campaign_coverage", "semantic_drift_rate"}
    ]
    for record in semantic_records:
        linked = [evidence_by_id[evidence_id] for evidence_id in record["evidence_ids"]]
        assert all(
            item["claim_id"]
            for item in linked
            if item["evidence_type"] != "analysis_scope"
        )
    assert any(
        item["message_id"] is None
        and item["method"] == "curated_alias_baseline:no_message_judgment"
        for item in evidence
    )

    for item in evidence:
        assert item["message_id"] is None or item["message_id"] in message_ids
        assert item["claim_id"] is None or item["claim_id"] in claim_ids
        assert item["campaign_id"] is None or item["campaign_id"] in campaign_ids
        assert item["community_id"] is None or item["community_id"] in community_ids


def test_silent_community_campaign_scope_is_audited_without_fabricated_message(
    tmp_path: Path,
) -> None:
    dataset_dir = _silent_scope_dataset(tmp_path)
    report, evidence = _read_report(run_pipeline(dataset_dir, tmp_path / "report"))
    scope_id = "campaign_stake:community_a"
    scope_records = [
        item
        for item in evidence
        if item["evidence_type"] == "analysis_scope"
        and item["campaign_id"] == "campaign_stake"
        and item["community_id"] == "community_a"
    ]
    assert len(scope_records) == 1
    scope = scope_records[0]
    assert scope["message_id"] is None
    assert scope["source_text"] is None
    assert scope["message_count"] == 0
    assert scope["denominator_facts"] == {
        "all_messages": 0,
        "campaign_linked_real_user_messages": 0,
        "noncampaign_real_user_messages": 0,
        "real_user_messages": 0,
    }

    metric_records = [
        item
        for item in report["Metric Lab"]["metric_records"]
        if item["observation_id"] == scope_id
    ]
    assert len(metric_records) == 10
    assert all(scope["evidence_id"] in item["evidence_ids"] for item in metric_records)
    by_name = {item["metric_name"]: item for item in metric_records}
    for metric_name in {
        "campaign_discussion_share",
        "community_response_latency",
        "conversation_propagation_depth",
        "meaningful_interaction_ratio",
        "organic_project_mention_rate",
        "peer_support_ratio",
        "unanswered_question_rate",
        "user_to_user_interaction_ratio",
    }:
        assert by_name[metric_name]["value"] is None
        assert by_name[metric_name]["diagnostic"] == "zero_denominator"
    assert by_name["semantic_campaign_coverage"]["value"] == 0.0
    assert by_name["semantic_drift_rate"]["value"] == 0.0
    assert _evidence_references(report) == {item["evidence_id"] for item in evidence}


def test_uncertain_judgments_with_messages_do_not_create_false_no_message_evidence(
    tmp_path: Path,
) -> None:
    report, evidence = _read_report(
        run_pipeline(_dataset(tmp_path), tmp_path / "report")
    )
    evidence_by_id = {item["evidence_id"]: item for item in evidence}
    uncertain = [
        judgment
        for judgment in report["Campaign"]["judgments"]
        if judgment["status"] == "uncertain"
    ]
    assert uncertain
    for judgment in uncertain:
        linked = [evidence_by_id[item] for item in judgment["evidence_ids"]]
        assert len(linked) >= 2
        assert all(item["message_id"] is not None for item in linked)
        assert all(
            item["method"] != "curated_alias_baseline:no_message_judgment"
            for item in linked
        )


def test_report_exposes_feedback_seed_evidence_without_faking_missing_capabilities(
    tmp_path: Path,
) -> None:
    report, evidence = _read_report(run_pipeline(_dataset(tmp_path), tmp_path / "report"))
    feedback = report["Community Feedback"]
    available = {
        "complaint",
        "positive_feedback",
        "negative_feedback",
        "feature_request",
        "FUD",
    }
    assert set(feedback["seed_counts"]) == available
    assert all(
        item["method_status"] == "Implemented"
        for item in feedback["seed_counts"].values()
    )
    for item in feedback["seed_counts"].values():
        expected_status = "Observed" if item["count"] > 0 else "Not observed in this dataset"
        assert item["observation_status"] == expected_status
        assert item["evidence_available"] is bool(item["evidence_ids"])
    referenced = {
        evidence_id
        for item in feedback["seed_counts"].values()
        for evidence_id in item["evidence_ids"]
    }
    assert referenced <= {item["evidence_id"] for item in evidence}
    assert feedback["seed_capabilities"]["confusion"] == "Not implemented"
    assert all(
        feedback["seed_capabilities"][behavior] == "Implemented"
        for behavior in available
    )
    assert feedback["capabilities"] == {
        "concern_clustering": "Not implemented",
        "general_multilingual_sentiment": "Not implemented",
        "stance": "Not implemented",
        "topic_extraction": "Not implemented",
    }
    assert set(feedback["limitations"]) == set(feedback["capabilities"]) | {
        "confusion",
        "single_label_classification",
    }


def test_synthetic_arabic_negative_feedback_is_observed_with_exact_source_evidence(
    tmp_path: Path,
) -> None:
    dataset_dir = _dataset(tmp_path)
    report, evidence = _read_report(run_pipeline(dataset_dir, tmp_path / "report"))
    messages = {message.message_id: message for message in read_dataset(dataset_dir).messages}
    item = report["Community Feedback"]["seed_counts"]["negative_feedback"]
    assert item["method_status"] == "Implemented"
    assert item["observation_status"] == "Observed"
    assert item["count"] > 0
    assert item["evidence_available"] is True
    assert item["evidence_ids"]
    evidence_by_id = {record["evidence_id"]: record for record in evidence}
    linked = [evidence_by_id[evidence_id] for evidence_id in item["evidence_ids"]]
    assert all(record["message_id"] in messages for record in linked)
    assert all(
        record["source_text"] == messages[record["message_id"]].text
        for record in linked
    )
    assert all(messages[record["message_id"]].language == "ar" for record in linked)


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


@pytest.mark.parametrize("placement", ["equal", "nested", "normalized_symlink"])
def test_pipeline_rejects_output_in_dataset_without_mutating_input(
    tmp_path: Path, placement: str
) -> None:
    dataset_dir = _dataset(tmp_path)
    before = _source_snapshot(dataset_dir)
    if placement == "equal":
        output = dataset_dir
    elif placement == "nested":
        output = dataset_dir / "reports" / "current"
    else:
        alias = tmp_path / "dataset-alias"
        alias.symlink_to(dataset_dir, target_is_directory=True)
        output = alias / "nested" / ".." / "report"

    with pytest.raises(ValueError, match="inside dataset_dir"):
        run_pipeline(dataset_dir, output)
    assert before == _source_snapshot(dataset_dir)
    if output != dataset_dir:
        assert not os.path.lexists(output)


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

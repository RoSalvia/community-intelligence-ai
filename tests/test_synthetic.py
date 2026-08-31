import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from community_intelligence import io as dataset_io
from community_intelligence import synthetic
from community_intelligence.io import read_dataset, write_dataset
from community_intelligence.models import MessageRecord
from community_intelligence.synthetic import generate_dataset

ARTIFACT_NAMES = {
    "messages.jsonl",
    "campaigns.json",
    "claims.json",
    "outcomes.csv",
    "annotations.jsonl",
    "manifest.json",
}


def test_generation_is_reproducible_and_meets_contract() -> None:
    first = generate_dataset(seed=20260901, message_count=1200)
    second = generate_dataset(seed=20260901, message_count=1200)

    assert first == second
    assert len(first.messages) == 1200
    assert {message.community_id for message in first.messages} == {
        "community_a",
        "community_b",
        "community_c",
        "community_d",
    }
    assert len({message.language for message in first.messages}) >= 4
    assert len(first.campaigns) == 3
    assert first.manifest.synthetic is True
    assert first.manifest.message_count == 1200
    assert set(first.manifest.scenarios) == {
        "community_a",
        "community_b",
        "community_c",
        "community_d",
    }


def test_generation_uses_hashed_ids_and_integral_reply_links() -> None:
    dataset = generate_dataset(seed=7, message_count=160)
    message_ids = {message.message_id for message in dataset.messages}

    assert all(re.fullmatch(r"usr_[0-9a-f]+", message.user_id_hash) for message in dataset.messages)
    assert any(message.reply_to_message_id is not None for message in dataset.messages)
    assert all(
        message.reply_to_message_id is None or message.reply_to_message_id in message_ids
        for message in dataset.messages
    )


def test_campaign_episodes_match_content_windows_and_reply_campaigns() -> None:
    dataset = generate_dataset(seed=41, message_count=120)
    campaigns = {campaign.campaign_id: campaign for campaign in dataset.campaigns}
    messages = {message.message_id: message for message in dataset.messages}

    assert len({(message.community_id, message.campaign_id) for message in dataset.messages}) == 12
    for message in dataset.messages:
        assert message.campaign_id is not None
        campaign = campaigns[message.campaign_id]
        assert campaign.campaign_name in message.text
        assert campaign.start_time <= message.timestamp < campaign.end_time
        if message.reply_to_message_id is not None:
            assert messages[message.reply_to_message_id].campaign_id == message.campaign_id


def test_scenario_templates_carry_explicit_annotation_metadata() -> None:
    assert hasattr(synthetic, "SCENARIO_TEMPLATES")
    for templates in synthetic.SCENARIO_TEMPLATES.values():
        assert templates
        for template in templates:
            assert template.text
            assert template.role in {"moderator", "user", "bot"}
            assert template.behaviors
            assert template.claim_status is not None


def test_representative_semantic_labels_match_message_meaning() -> None:
    dataset = generate_dataset(seed=43, message_count=120)
    annotations = {annotation.message_id: annotation for annotation in dataset.annotations}

    correct_messages = [
        message
        for message in dataset.messages
        if "我看到的合成说明写的是 100 个代币和星期五" in message.text
    ]
    assert correct_messages
    assert all(
        annotations[message.message_id].expected_claim_status == "covered"
        for message in correct_messages
    )

    moderator_followups = [
        message
        for message in dataset.messages
        if message.user_role == "moderator" and "سنراجع الأسئلة لاحقاً" in message.text
    ]
    assert moderator_followups
    assert all(
        "campaign_question" not in annotations[message.message_id].expected_behaviors
        for message in moderator_followups
    )


def test_annotations_are_separate_from_production_messages() -> None:
    dataset = generate_dataset(seed=11, message_count=80)
    message_ids = {message.message_id for message in dataset.messages}

    assert "annotations" not in MessageRecord.model_fields
    assert "expected_behaviors" not in MessageRecord.model_fields
    assert "expected_claim_status" not in MessageRecord.model_fields
    assert dataset.annotations
    assert all(annotation.message_id in message_ids for annotation in dataset.annotations)
    assert {annotation.scenario for annotation in dataset.annotations} == {
        "high_volume_filler_duplicates",
        "healthy_replies",
        "semantic_drift",
        "unanswered_questions_negative_feedback",
    }


def test_generation_includes_synthetic_outcomes_for_each_community_and_campaign() -> None:
    dataset = generate_dataset(seed=23, message_count=120)

    assert len(dataset.outcomes) == 12
    assert len({(outcome.community_id, outcome.campaign_id) for outcome in dataset.outcomes}) == 12
    assert all(outcome.synthetic for outcome in dataset.outcomes)


def test_dataset_file_round_trip_preserves_validated_data(tmp_path: Path) -> None:
    dataset = generate_dataset(seed=29, message_count=96)

    output_dir = write_dataset(dataset, tmp_path / "generated")
    loaded = read_dataset(output_dir)

    assert {path.name for path in output_dir.iterdir()} == ARTIFACT_NAMES
    assert loaded == dataset

    first_message = json.loads((output_dir / "messages.jsonl").read_text().splitlines()[0])
    assert set(first_message) == set(MessageRecord.model_fields)
    assert not any(key.startswith("expected_") for key in first_message)


def test_write_boundary_revalidates_a_mutated_complete_dataset(tmp_path: Path) -> None:
    dataset = generate_dataset(seed=47, message_count=120)
    dataset.messages[0] = dataset.messages[0].model_copy(update={"user_id_hash": "Alice"})

    with pytest.raises(ValidationError, match="user_id_hash"):
        write_dataset(dataset, tmp_path / "rejected")

    assert not (tmp_path / "rejected").exists()


def test_publication_manifest_records_and_verifies_artifact_checksums(tmp_path: Path) -> None:
    output_dir = write_dataset(generate_dataset(seed=53, message_count=120), tmp_path / "dataset")
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert "generation_id" in manifest
    assert "artifact_checksums" in manifest
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["generation_id"])
    assert set(manifest["artifact_checksums"]) == ARTIFACT_NAMES - {"manifest.json"}
    assert manifest["artifact_checksums"] == {
        name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
        for name in ARTIFACT_NAMES - {"manifest.json"}
    }

    message_path = output_dir / "messages.jsonl"
    lines = message_path.read_text(encoding="utf-8").splitlines()
    first_message = json.loads(lines[0])
    first_message["text"] += " tampered"
    lines[0] = json.dumps(first_message, ensure_ascii=False, sort_keys=True)
    message_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact checksum mismatch"):
        read_dataset(output_dir)


def test_reader_rejects_duplicate_manifest_json_keys(tmp_path: Path) -> None:
    output_dir = write_dataset(generate_dataset(seed=71, message_count=120), tmp_path / "dataset")
    manifest_path = output_dir / "manifest.json"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        manifest_text.replace(
            '"synthetic": true',
            '"synthetic": false,\n  "synthetic": true',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate JSON key: synthetic"):
        read_dataset(output_dir)


def test_reader_rejects_malformed_manifest_json(tmp_path: Path) -> None:
    output_dir = write_dataset(generate_dataset(seed=73, message_count=120), tmp_path / "dataset")
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text('{"synthetic": true', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid manifest JSON"):
        read_dataset(output_dir)


def test_reader_rejects_incomplete_six_file_publication(tmp_path: Path) -> None:
    output_dir = write_dataset(generate_dataset(seed=79, message_count=120), tmp_path / "dataset")
    (output_dir / "claims.json").unlink()

    with pytest.raises(
        ValueError,
        match="complete dataset publication must contain exactly six artifacts",
    ):
        read_dataset(output_dir)


def test_failed_directory_publish_preserves_previous_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = write_dataset(generate_dataset(seed=59, message_count=120), tmp_path / "dataset")
    previous = read_dataset(output_dir)
    previous_bytes = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    replacement = generate_dataset(seed=61, message_count=120)
    real_replace = dataset_io.os.replace
    injected = False

    def fail_staging_publish(source: str | Path, destination: str | Path) -> None:
        nonlocal injected
        source_path = Path(source)
        destination_path = Path(destination)
        if (
            not injected
            and destination_path == output_dir
            and ".staging-" in source_path.name
        ):
            injected = True
            raise OSError("injected publish failure")
        real_replace(source, destination)

    monkeypatch.setattr(dataset_io.os, "replace", fail_staging_publish)

    with pytest.raises(OSError, match="injected publish failure"):
        write_dataset(replacement, output_dir)

    assert injected is True
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == previous_bytes
    assert read_dataset(output_dir) == previous


def test_minimum_message_count_guarantees_scenarios_and_replies() -> None:
    assert getattr(synthetic, "MIN_MESSAGE_COUNT", None) == 60
    dataset = generate_dataset(seed=67, message_count=60)
    episode_messages: dict[tuple[str, str | None], list[MessageRecord]] = {}
    for message in dataset.messages:
        episode_messages.setdefault((message.community_id, message.campaign_id), []).append(message)

    assert len(dataset.messages) == 60
    assert len(episode_messages) == 12
    assert all(
        any(message.reply_to_message_id is not None for message in messages)
        for messages in episode_messages.values()
    )

    with pytest.raises(ValueError, match="message_count must be at least 60"):
        generate_dataset(seed=67, message_count=59)


def test_cli_rejects_too_few_messages_without_traceback(tmp_path: Path) -> None:
    output_dir = tmp_path / "too-small"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "community_intelligence.cli",
            "generate",
            "--output",
            str(output_dir),
            "--messages",
            "59",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "argument --messages: must be at least 60" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert not output_dir.exists()


def test_cli_generate_creates_six_artifacts_and_prints_absolute_path(tmp_path: Path) -> None:
    output_dir = tmp_path / "cli-output"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "community_intelligence.cli",
            "generate",
            "--output",
            str(output_dir),
            "--seed",
            "31",
            "--messages",
            "60",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == str(output_dir.resolve())
    assert {path.name for path in output_dir.iterdir()} == ARTIFACT_NAMES
    assert json.loads((output_dir / "manifest.json").read_text())["message_count"] == 60

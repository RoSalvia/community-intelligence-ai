import json
import re
import subprocess
import sys
from pathlib import Path

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
            "48",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == str(output_dir.resolve())
    assert {path.name for path in output_dir.iterdir()} == ARTIFACT_NAMES
    assert json.loads((output_dir / "manifest.json").read_text())["message_count"] == 48

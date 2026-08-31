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


def _directory_file_bytes(path: Path) -> dict[str, bytes]:
    return {
        str(file_path.relative_to(path)): file_path.read_bytes()
        for file_path in path.rglob("*")
        if file_path.is_file()
    }


def _refresh_publication_metadata(output_dir: Path) -> None:
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_names = ARTIFACT_NAMES - {"manifest.json"}
    checksums = {
        name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
        for name in payload_names
    }
    generation_source = json.dumps(
        {
            "artifact_checksums": checksums,
            "dataset_id": manifest["dataset_id"],
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    manifest["artifact_checksums"] = checksums
    manifest["generation_id"] = hashlib.sha256(generation_source).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _duplicate_first_json_key(path: Path, key: str) -> None:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        first_record = json.loads(text.splitlines()[0])
    else:
        first_record = json.loads(text)[0]
    token = f'{json.dumps(key)}: {json.dumps(first_record[key], ensure_ascii=False)}'
    path.write_text(text.replace(token, f"{token}, {token}", 1), encoding="utf-8")


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


def test_generated_episodes_carry_explicit_annotation_metadata() -> None:
    dataset = generate_dataset(seed=37, message_count=60)
    annotations = {annotation.message_id: annotation for annotation in dataset.annotations}

    assert set(annotations) == {message.message_id for message in dataset.messages}
    assert all(annotation.expected_behaviors for annotation in annotations.values())
    assert all(annotation.expected_claim_status is not None for annotation in annotations.values())
    assert {annotation.scenario for annotation in annotations.values()} == {
        "high_volume_filler_duplicates",
        "healthy_replies",
        "semantic_drift",
        "unanswered_questions_negative_feedback",
    }


def test_semantic_drift_questions_have_consistent_explicit_answers() -> None:
    dataset = generate_dataset(seed=39, message_count=1200)
    annotations = {annotation.message_id: annotation for annotation in dataset.annotations}
    expected_eligibility = {
        "campaign_stake": "资格条件未变：仅已验证成员符合资格",
        "campaign_referral": "资格条件未变：仅合格好友推荐计入活动",
        "campaign_launch": "资格条件未变：所有社区成员均可提交反馈",
    }
    questions = [
        message
        for message in dataset.messages
        if "资格条件是不是也发生了变化" in message.text
    ]

    assert {question.campaign_id for question in questions} == set(expected_eligibility)
    for question in questions:
        question_annotation = annotations[question.message_id]
        assert set(question_annotation.expected_behaviors) == {"campaign_question", "confusion"}
        assert question_annotation.expected_claim_status == "uncertain"
        assert question_annotation.expected_question_status == "answered"

        answers = [
            message
            for message in dataset.messages
            if message.reply_to_message_id == question.message_id
        ]
        assert len(answers) == 1
        answer = answers[0]
        answer_annotation = annotations[answer.message_id]
        assert answer.user_role == "moderator"
        assert answer.community_id == question.community_id
        assert answer.campaign_id == question.campaign_id
        assert expected_eligibility[answer.campaign_id] in answer.text
        assert answer_annotation.expected_behaviors == ["question_answering"]
        assert answer_annotation.expected_claim_status == "covered"
        assert answer_annotation.expected_question_status == "answered"


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


@pytest.mark.parametrize(
    ("artifact_name", "duplicate_key"),
    [
        ("campaigns.json", "campaign_id"),
        ("claims.json", "claim_id"),
        ("messages.jsonl", "message_id"),
        ("annotations.jsonl", "annotation_id"),
    ],
)
def test_reader_rejects_duplicate_keys_in_payload_json_records(
    tmp_path: Path,
    artifact_name: str,
    duplicate_key: str,
) -> None:
    output_dir = write_dataset(generate_dataset(seed=72, message_count=120), tmp_path / "dataset")
    _duplicate_first_json_key(output_dir / artifact_name, duplicate_key)
    _refresh_publication_metadata(output_dir)

    with pytest.raises(ValueError, match=f"duplicate JSON key: {duplicate_key}"):
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


def test_write_refuses_existing_arbitrary_directory_without_modification(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    (output_dir / "keep-me.txt").write_bytes(b"keep this exact content\n")
    before = _directory_file_bytes(output_dir)

    with pytest.raises(FileExistsError, match="output path already exists"):
        write_dataset(generate_dataset(seed=59, message_count=120), output_dir)

    assert _directory_file_bytes(output_dir) == before


def test_write_refuses_repository_like_directory_without_modification(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "repository"
    (output_dir / ".git").mkdir(parents=True)
    (output_dir / ".git" / "config").write_bytes(b"[core]\n\trepositoryformatversion = 0\n")
    (output_dir / "src").mkdir()
    (output_dir / "src" / "keep.py").write_bytes(b"VALUE = 'unchanged'\n")
    (output_dir / "keep-me.txt").write_bytes(b"repository sentinel\n")
    before = _directory_file_bytes(output_dir)

    with pytest.raises(FileExistsError, match="output path already exists"):
        write_dataset(generate_dataset(seed=61, message_count=120), output_dir)

    assert _directory_file_bytes(output_dir) == before


def test_failed_first_publication_removes_only_staging_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "dataset"
    unrelated = tmp_path / "keep-me.txt"
    unrelated.write_bytes(b"outside staging\n")
    real_rename = dataset_io.os.rename
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
        real_rename(source, destination)

    monkeypatch.setattr(dataset_io.os, "rename", fail_staging_publish)

    with pytest.raises(OSError, match="injected publish failure"):
        write_dataset(generate_dataset(seed=67, message_count=120), output_dir)

    assert injected is True
    assert not output_dir.exists()
    assert unrelated.read_bytes() == b"outside staging\n"
    assert list(tmp_path.glob(".dataset.staging-*")) == []


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

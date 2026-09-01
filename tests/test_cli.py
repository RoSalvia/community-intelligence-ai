from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from community_intelligence.cli import main
from community_intelligence.io import (
    data_artifact_contents,
    publication_metadata,
    write_dataset,
)
from community_intelligence.models import SyntheticDataset
from community_intelligence.synthetic import generate_dataset


def _no_campaign_dataset(tmp_path: Path) -> Path:
    source = generate_dataset(message_count=120)
    messages = [
        message.model_copy(update={"campaign_id": None}) for message in source.messages
    ]
    contents = data_artifact_contents(messages, [], [], [], source.annotations)
    generation_id, checksums = publication_metadata(source.manifest.dataset_id, contents)
    dataset = SyntheticDataset(
        messages=messages,
        campaigns=[],
        claims=[],
        outcomes=[],
        annotations=source.annotations,
        manifest=source.manifest.model_copy(
            update={
                "campaign_ids": [],
                "generation_id": generation_id,
                "artifact_checksums": checksums,
            }
        ),
    )
    return write_dataset(dataset, tmp_path / "dataset")


def test_analyze_cli_prints_absolute_artifacts_and_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = write_dataset(generate_dataset(message_count=120), tmp_path / "dataset")
    output = tmp_path / "report"
    assert main(["analyze", "--input", str(dataset), "--output", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert Path(result["report_json"]).is_absolute()
    assert Path(result["evidence_jsonl"]).is_absolute()
    assert result["message_count"] == 120
    assert result["metric_observation_count"] == 12


def test_demo_cli_is_create_only_and_builds_dataset_and_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = tmp_path / "demo"
    assert main(["demo", "--workspace", str(workspace), "--messages", "120"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert Path(result["dataset_dir"]) == workspace / "dataset"
    assert Path(result["report_dir"]) == workspace / "report"
    assert (workspace / "dataset" / "manifest.json").is_file()
    assert (workspace / "report" / "report.json").is_file()

    assert main(["demo", "--workspace", str(workspace), "--messages", "120"]) == 1


@pytest.mark.parametrize("existing_kind", ["file", "directory", "symlink"])
def test_demo_cli_rejects_every_existing_workspace_kind(tmp_path: Path, existing_kind: str) -> None:
    workspace = tmp_path / "demo"
    if existing_kind == "file":
        workspace.write_text("keep", encoding="utf-8")
    elif existing_kind == "directory":
        workspace.mkdir()
    else:
        workspace.symlink_to(tmp_path / "missing-target")
    assert main(["demo", "--workspace", str(workspace), "--messages", "120"]) == 1


def test_cli_parse_error_uses_nonzero_exit_status() -> None:
    with pytest.raises(SystemExit) as error:
        main(["analyze"])
    assert error.value.code == 2


def test_analyze_cli_rejects_existing_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = write_dataset(generate_dataset(message_count=120), tmp_path / "dataset")
    output = tmp_path / "report"
    output.mkdir()
    assert main(["analyze", "--input", str(dataset), "--output", str(output)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: output path already exists:")
    assert "Traceback" not in captured.err


def test_analyze_cli_rejects_nested_output_without_creating_it(tmp_path: Path) -> None:
    dataset = write_dataset(generate_dataset(message_count=120), tmp_path / "dataset")
    output = dataset / "reports" / "current"
    assert main(["analyze", "--input", str(dataset), "--output", str(output)]) == 1
    assert not output.exists()


def test_analyze_cli_normalizes_symlink_and_parent_segments_before_output(
    tmp_path: Path,
) -> None:
    dataset = write_dataset(generate_dataset(message_count=120), tmp_path / "dataset")
    alias = tmp_path / "dataset-alias"
    alias.symlink_to(dataset, target_is_directory=True)
    output = alias / "nested" / ".." / "report"
    assert main(["analyze", "--input", str(dataset), "--output", str(output)]) == 1
    assert not os.path.lexists(dataset / "report")


def test_demo_concurrent_workspace_creation_is_preserved_without_partial_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import community_intelligence.cli as cli
    from community_intelligence.io import publish_directory_no_replace as real_publish

    workspace = tmp_path / "demo"

    def create_racer(staging: Path, destination: Path) -> Path:
        destination.mkdir()
        (destination / "keep.txt").write_text("racer", encoding="utf-8")
        return real_publish(staging, destination)

    monkeypatch.setattr(cli, "publish_directory_no_replace", create_racer, raising=False)

    with pytest.raises(FileExistsError):
        cli._demo(workspace, seed=20260901, messages=120)
    assert (workspace / "keep.txt").read_text(encoding="utf-8") == "racer"
    assert sorted(path.name for path in workspace.iterdir()) == ["keep.txt"]
    assert not list(tmp_path.glob(".demo.staging-*"))


def test_cli_missing_input_returns_nonzero_concise_error_without_output_mutation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "report"

    result = main(
        [
            "analyze",
            "--input",
            str(tmp_path / "missing-dataset"),
            "--output",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err
    assert not os.path.lexists(output)


def test_cli_no_campaign_dataset_returns_nonzero_before_output_creation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = _no_campaign_dataset(tmp_path)
    output = tmp_path / "report"

    result = main(["analyze", "--input", str(dataset), "--output", str(output)])

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err == (
        "error: at least one campaign required for this campaign-centric MVP\n"
    )
    assert not os.path.lexists(output)


def test_cli_expected_oserror_is_concise_and_has_no_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import community_intelligence.cli as cli

    def fail_write(dataset: object, output: Path) -> Path:
        raise OSError("synthetic I/O failure")

    monkeypatch.setattr(cli, "write_dataset", fail_write)
    output = tmp_path / "dataset"

    result = main(["generate", "--output", str(output), "--messages", "120"])

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err == "error: synthetic I/O failure\n"
    assert "Traceback" not in captured.err
    assert not os.path.lexists(output)

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from community_intelligence.cli import main
from community_intelligence.io import write_dataset
from community_intelligence.synthetic import generate_dataset


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

    with pytest.raises(FileExistsError):
        main(["demo", "--workspace", str(workspace), "--messages", "120"])


@pytest.mark.parametrize("existing_kind", ["file", "directory", "symlink"])
def test_demo_cli_rejects_every_existing_workspace_kind(tmp_path: Path, existing_kind: str) -> None:
    workspace = tmp_path / "demo"
    if existing_kind == "file":
        workspace.write_text("keep", encoding="utf-8")
    elif existing_kind == "directory":
        workspace.mkdir()
    else:
        workspace.symlink_to(tmp_path / "missing-target")
    with pytest.raises(FileExistsError):
        main(["demo", "--workspace", str(workspace), "--messages", "120"])


def test_cli_parse_error_uses_nonzero_exit_status() -> None:
    with pytest.raises(SystemExit) as error:
        main(["analyze"])
    assert error.value.code == 2


def test_analyze_cli_rejects_existing_output(tmp_path: Path) -> None:
    dataset = write_dataset(generate_dataset(message_count=120), tmp_path / "dataset")
    output = tmp_path / "report"
    output.mkdir()
    with pytest.raises(FileExistsError):
        main(["analyze", "--input", str(dataset), "--output", str(output)])


def test_analyze_cli_rejects_nested_output_without_creating_it(tmp_path: Path) -> None:
    dataset = write_dataset(generate_dataset(message_count=120), tmp_path / "dataset")
    output = dataset / "reports" / "current"
    with pytest.raises(ValueError, match="inside dataset_dir"):
        main(["analyze", "--input", str(dataset), "--output", str(output)])
    assert not output.exists()


def test_analyze_cli_normalizes_symlink_and_parent_segments_before_output(
    tmp_path: Path,
) -> None:
    dataset = write_dataset(generate_dataset(message_count=120), tmp_path / "dataset")
    alias = tmp_path / "dataset-alias"
    alias.symlink_to(dataset, target_is_directory=True)
    output = alias / "nested" / ".." / "report"
    with pytest.raises(ValueError, match="inside dataset_dir"):
        main(["analyze", "--input", str(dataset), "--output", str(output)])
    assert not os.path.lexists(dataset / "report")

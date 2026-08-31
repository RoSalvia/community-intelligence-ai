"""Command-line entry points for the offline Community Intelligence demo."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path

from community_intelligence.io import write_dataset
from community_intelligence.pipeline import run_pipeline
from community_intelligence.synthetic import MIN_MESSAGE_COUNT, generate_dataset


def _message_count(value: str) -> int:
    try:
        message_count = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer") from None
    if message_count < MIN_MESSAGE_COUNT:
        raise argparse.ArgumentTypeError(f"must be at least {MIN_MESSAGE_COUNT}")
    return message_count


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="community-intelligence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="generate a synthetic dataset")
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--seed", type=int, default=20260901)
    generate.add_argument("--messages", type=_message_count, default=1200)
    analyze = subparsers.add_parser("analyze", help="analyze a validated offline dataset")
    analyze.add_argument("--input", type=Path, required=True)
    analyze.add_argument("--output", type=Path, required=True)
    demo = subparsers.add_parser("demo", help="create a synthetic dataset and report workspace")
    demo.add_argument("--workspace", type=Path, required=True)
    demo.add_argument("--seed", type=int, default=20260901)
    demo.add_argument("--messages", type=_message_count, default=1200)
    return parser


def _summary(dataset_dir: Path, report_dir: Path) -> dict[str, object]:
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    evidence_count = len((report_dir / "evidence.jsonl").read_text(encoding="utf-8").splitlines())
    return {
        "dataset_dir": str(dataset_dir.resolve()),
        "report_dir": str(report_dir.resolve()),
        "report_json": str((report_dir / "report.json").resolve()),
        "evidence_jsonl": str((report_dir / "evidence.jsonl").resolve()),
        "message_count": report["Overview"]["message_count"],
        "campaign_judgment_count": len(report["Campaign"]["judgments"]),
        "metric_observation_count": len(report["Metric Lab"]["observations"]),
        "evidence_count": evidence_count,
    }


def _demo(workspace: Path, *, seed: int, messages: int) -> dict[str, object]:
    destination = Path(os.path.abspath(workspace.expanduser()))
    if os.path.lexists(destination):
        raise FileExistsError(f"workspace already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix=f".{destination.name}.staging-"))
    reserved = False
    try:
        dataset_dir = write_dataset(
            generate_dataset(seed=seed, message_count=messages), staging / "dataset"
        )
        report_dir = run_pipeline(dataset_dir, staging / "report")
        os.mkdir(destination)
        reserved = True
        os.rename(dataset_dir, destination / "dataset")
        os.rename(report_dir, destination / "report")
        return _summary(destination / "dataset", destination / "report")
    except BaseException:
        if reserved and destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate":
        dataset = generate_dataset(seed=args.seed, message_count=args.messages)
        output_path = write_dataset(dataset, args.output)
        print(output_path)
        return 0
    if args.command == "analyze":
        report_dir = run_pipeline(args.input, args.output)
        print(json.dumps(_summary(args.input, report_dir), sort_keys=True))
        return 0
    if args.command == "demo":
        print(
            json.dumps(
                _demo(args.workspace, seed=args.seed, messages=args.messages),
                sort_keys=True,
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

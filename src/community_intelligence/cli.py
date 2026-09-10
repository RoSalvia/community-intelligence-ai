"""Command-line entry points for the offline Community Intelligence demo."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from community_intelligence.importers.telegram import import_telegram_export
from community_intelligence.importers.telegram_html import canonicalize_telegram_html_exports
from community_intelligence.io import (
    cleanup_private_directory,
    publish_directory_no_replace,
    write_dataset,
)
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


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("must be between 1 and 65535")
    return port


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
    import_command = subparsers.add_parser("import", help="import a supported community export")
    import_formats = import_command.add_subparsers(dest="import_format", required=True)
    telegram = import_formats.add_parser(
        "telegram", help="import Telegram Desktop chat-history result.json"
    )
    telegram.add_argument("--input", type=Path, required=True)
    telegram.add_argument("--output", type=Path, required=True)
    telegram.add_argument("--language", default="und")
    telegram_html = import_formats.add_parser(
        "telegram-html",
        help="normalize one or more Telegram Desktop HTML export snapshots",
    )
    telegram_html.add_argument("--input", type=Path, action="append", required=True)
    telegram_html.add_argument("--output", type=Path, required=True)
    telegram_html.add_argument("--community-id", required=True)
    telegram_html.add_argument("--language", default="und")
    telegram_html.add_argument("--source-timezone", required=True)
    telegram_html.add_argument("--timezone-provenance", required=True)
    telegram_html.add_argument("--identity-salt-file", type=Path, required=True)
    serve = subparsers.add_parser("serve", help="open the local web product")
    serve.add_argument("--port", type=_port, default=8765)
    serve.add_argument("--no-open", action="store_true", help="do not open a browser")
    serve.add_argument(
        "--m1-review",
        action="store_true",
        help="enable the internal M1 product-review harness",
    )
    serve.add_argument(
        "--knowledge-review",
        action="store_true",
        help="enable the internal M2 Knowledge product-review surface",
    )
    serve.add_argument(
        "--semantic-model-dir",
        type=Path,
        help="verified local multilingual embedding model directory",
    )
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


def _load_or_create_identity_salt(path: Path) -> str:
    requested = Path(os.path.abspath(path.expanduser()))
    requested.parent.mkdir(parents=True, exist_ok=True)
    try:
        metadata = requested.lstat()
    except FileNotFoundError:
        salt = secrets.token_hex(32)
        descriptor = os.open(
            requested,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        try:
            os.write(descriptor, f"{salt}\n".encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return salt
    if not stat.S_ISREG(metadata.st_mode) or requested.is_symlink():
        raise ValueError("identity salt path must be a regular non-symlink file")
    salt = requested.read_text(encoding="utf-8").strip()
    if len(salt) < 16:
        raise ValueError("identity salt must contain at least 16 characters")
    return salt


def _demo(workspace: Path, *, seed: int, messages: int) -> dict[str, object]:
    requested = Path(os.path.abspath(workspace.expanduser()))
    requested.parent.mkdir(parents=True, exist_ok=True)
    destination = requested.parent.resolve(strict=True) / requested.name
    if os.path.lexists(destination):
        raise FileExistsError(f"workspace already exists: {destination}")
    staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix=f".{destination.name}.staging-"))
    staging_inode = staging.lstat().st_ino
    try:
        dataset_dir = write_dataset(
            generate_dataset(seed=seed, message_count=messages), staging / "dataset"
        )
        run_pipeline(dataset_dir, staging / "report")
        publish_directory_no_replace(staging, destination)
        return _summary(destination / "dataset", destination / "report")
    finally:
        cleanup_private_directory(staging, expected_inode=staging_inode)


def _open_when_ready(base_url: str, page_url: str) -> None:
    health_url = f"{base_url}api/health"
    for _ in range(100):
        try:
            with urllib.request.urlopen(health_url, timeout=0.25) as response:
                if response.status == 200:
                    webbrowser.open(page_url)
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)


def _serve(
    *,
    port: int,
    open_browser: bool,
    m1_review: bool = False,
    knowledge_review: bool = False,
    semantic_model_dir: Path | None = None,
) -> None:
    base_url = f"http://127.0.0.1:{port}/"
    if knowledge_review:
        page_url = f"{base_url}internal/knowledge-review"
    elif m1_review:
        page_url = f"{base_url}internal/m1-review"
    else:
        page_url = base_url
    review_variable = "COMMUNITY_INTELLIGENCE_INTERNAL_REVIEW"
    previous_review_value = os.environ.get(review_variable)
    semantic_variable = "COMMUNITY_INTELLIGENCE_SEMANTIC_MODEL_DIR"
    previous_semantic_value = os.environ.get(semantic_variable)
    if m1_review or knowledge_review:
        os.environ[review_variable] = "1"
    if semantic_model_dir:
        os.environ[semantic_variable] = str(semantic_model_dir.expanduser().resolve())
    print(f"Community Intelligence is available at {page_url}")
    if open_browser:
        threading.Thread(
            target=_open_when_ready,
            args=(base_url, page_url),
            daemon=True,
        ).start()
    try:
        uvicorn.run(
            "community_intelligence.web.app:create_app",
            factory=True,
            host="127.0.0.1",
            port=port,
            log_level="info",
        )
    finally:
        if (m1_review or knowledge_review) and previous_review_value is None:
            os.environ.pop(review_variable, None)
        elif m1_review or knowledge_review:
            os.environ[review_variable] = previous_review_value
        if semantic_model_dir and previous_semantic_value is None:
            os.environ.pop(semantic_variable, None)
        elif semantic_model_dir:
            os.environ[semantic_variable] = previous_semantic_value


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate":
            dataset = generate_dataset(seed=args.seed, message_count=args.messages)
            output_path = write_dataset(dataset, args.output)
            print(output_path)
            return 0
        if args.command == "analyze":
            report_dir = run_pipeline(args.input, args.output)
            print(json.dumps(_summary(args.input, report_dir), sort_keys=True))
            return 0
        if args.command == "import" and args.import_format == "telegram":
            dataset = import_telegram_export(args.input, language=args.language)
            output_path = write_dataset(dataset, args.output)
            print(
                json.dumps(
                    {
                        "dataset_dir": str(output_path.resolve()),
                        "message_count": len(dataset.messages),
                        "source_format": dataset.manifest.source_format,
                        "limitations": dataset.manifest.limitations,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "import" and args.import_format == "telegram-html":
            salt_path = Path(os.path.abspath(args.identity_salt_file.expanduser()))
            input_roots = [path.expanduser().resolve(strict=True) for path in args.input]
            if any(salt_path.is_relative_to(root) for root in input_roots):
                raise ValueError("identity salt must be outside source export roots")
            identity_salt = _load_or_create_identity_salt(salt_path)
            output_path = canonicalize_telegram_html_exports(
                input_roots,
                args.output,
                community_id=args.community_id,
                language=args.language,
                source_timezone=args.source_timezone,
                timezone_provenance=args.timezone_provenance,
                identity_salt=identity_salt,
            )
            manifest = json.loads(
                (output_path / "dataset_manifest.json").read_text(encoding="utf-8")
            )
            print(
                json.dumps(
                    {
                        "dataset_dir": str(output_path.resolve()),
                        "ordinary_message_count": manifest["profile"]["ordinary_message_count"],
                        "output_fingerprint": manifest["output_fingerprint"],
                        "parse_quarantine_count": manifest["profile"]["parse_quarantine_count"],
                        "service_event_count": manifest["profile"]["service_event_count"],
                        "source_format": manifest["source_format"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "demo":
            print(
                json.dumps(
                    _demo(args.workspace, seed=args.seed, messages=args.messages),
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "serve":
            _serve(
                port=args.port,
                open_browser=not args.no_open,
                m1_review=args.m1_review,
                knowledge_review=args.knowledge_review,
                semantic_model_dir=args.semantic_model_dir,
            )
            return 0
    except (OSError, ValueError) as error:
        message = str(error).splitlines()[0]
        print(f"error: {message}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

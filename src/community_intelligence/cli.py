"""Command-line entry points for local synthetic data generation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from community_intelligence.io import write_dataset
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate":
        dataset = generate_dataset(seed=args.seed, message_count=args.messages)
        output_path = write_dataset(dataset, args.output)
        print(output_path)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

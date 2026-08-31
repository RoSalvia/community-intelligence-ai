"""Explicitly prefetch the one pinned semantic model for offline integration tests."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from community_intelligence.semantic import (
    MANIFEST_FILENAME,
    MODEL_ID,
    MODEL_MAX_SEQUENCE_LENGTH,
    MODEL_REVISION,
    build_model_manifest,
)

DEFAULT_OUTPUT = Path(
    "data/generated/models/paraphrase-multilingual-MiniLM-L12-v2-e8f8c211"
)
ModelLoader = Callable[..., Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def reserve_destination(output: Path) -> Path:
    """Atomically reserve a new local directory without replacing any path."""

    lexical_destination = output.expanduser()
    if not lexical_destination.is_absolute():
        lexical_destination = Path.cwd() / lexical_destination
    if os.path.lexists(lexical_destination):
        raise FileExistsError(
            f"refusing to replace existing path entry: {lexical_destination}"
        )
    lexical_destination.parent.mkdir(parents=True, exist_ok=True)
    validated_parent = lexical_destination.parent.resolve(strict=True)
    if not validated_parent.is_dir():
        raise NotADirectoryError(f"destination parent is not a directory: {validated_parent}")
    destination = validated_parent / lexical_destination.name
    destination.mkdir(mode=0o700)
    return destination


def _default_model_loader(*args: object, **kwargs: object) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(*args, **kwargs)


def prefetch(output: Path, *, model_loader: ModelLoader | None = None) -> Path:
    loader = model_loader or _default_model_loader
    destination = reserve_destination(output)
    try:
        model = loader(
            MODEL_ID,
            revision=MODEL_REVISION,
            trust_remote_code=False,
        )
        if int(model.max_seq_length) != MODEL_MAX_SEQUENCE_LENGTH:
            raise ValueError("downloaded model does not expose the expected 128-token limit")
        model.save_pretrained(str(destination), safe_serialization=True)
        manifest = build_model_manifest(destination)
        (destination / MANIFEST_FILENAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except BaseException:
        # Reservation proves this invocation created the path. Never clean a
        # pre-existing file, directory, or symlink after a failed reservation.
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination, ignore_errors=True)
        raise
    print(destination)
    return destination


def main() -> None:
    prefetch(parse_args().output)


if __name__ == "__main__":
    main()

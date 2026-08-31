"""Explicitly prefetch the one pinned semantic model for offline integration tests."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def prefetch(output: Path) -> Path:
    from sentence_transformers import SentenceTransformer

    destination = output.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to replace existing path: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        model = SentenceTransformer(
            MODEL_ID,
            revision=MODEL_REVISION,
            trust_remote_code=False,
        )
        if int(model.max_seq_length) != MODEL_MAX_SEQUENCE_LENGTH:
            raise ValueError("downloaded model does not expose the expected 128-token limit")
        model.save_pretrained(str(stage), safe_serialization=True)
        manifest = build_model_manifest(stage)
        (stage / MANIFEST_FILENAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        stage.rename(destination)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    print(destination)
    return destination


def main() -> None:
    prefetch(parse_args().output)


if __name__ == "__main__":
    main()

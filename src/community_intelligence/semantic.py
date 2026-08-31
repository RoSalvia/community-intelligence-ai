"""Offline-only provider for one pinned multilingual sentence-transformer."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
MODEL_MAX_SEQUENCE_LENGTH = 128
MANIFEST_FILENAME = "community_intelligence_manifest.json"
_UNSAFE_WEIGHT_SUFFIXES = {".bin", ".pt", ".pth"}

ModelLoader = Callable[..., Any]


@dataclass(frozen=True)
class RankedText:
    text: str
    score: float
    original_index: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_model_manifest(model_dir: str | Path) -> dict[str, object]:
    """Describe every saved model artifact for later offline verification."""

    directory = Path(model_dir).resolve()
    files = {
        path.relative_to(directory).as_posix(): _sha256(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != MANIFEST_FILENAME
    }
    if not files:
        raise ValueError("model directory contains no artifacts")
    if any(
        Path(relative_path).suffix.casefold() in _UNSAFE_WEIGHT_SUFFIXES
        for relative_path in files
    ):
        raise ValueError("model directory contains unsafe serialized weights")
    return {
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "max_seq_length": MODEL_MAX_SEQUENCE_LENGTH,
        "safe_serialization": True,
        "files": files,
    }


def _validated_model_directory(model_dir: str | Path) -> Path:
    directory = Path(model_dir).expanduser()
    if not directory.is_dir():
        raise ValueError("remote model identifiers are rejected; provide a local directory")
    directory = directory.resolve()
    manifest_path = directory / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise ValueError("local directory requires a verified model manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError("verified model manifest is not readable JSON") from error
    expected_metadata = {
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "max_seq_length": MODEL_MAX_SEQUENCE_LENGTH,
        "safe_serialization": True,
    }
    if any(manifest.get(key) != value for key, value in expected_metadata.items()):
        raise ValueError("verified model manifest does not match the pinned model")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("verified model manifest must contain artifact checksums")
    actual_files = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path.name != MANIFEST_FILENAME
    }
    if any(
        Path(relative_path).suffix.casefold() in _UNSAFE_WEIGHT_SUFFIXES
        for relative_path in actual_files
    ):
        raise ValueError("verified model directory contains unsafe serialized weights")
    if actual_files != set(files):
        raise ValueError("verified model directory contains unlisted or missing artifacts")
    for relative_path, expected_checksum in files.items():
        if not isinstance(relative_path, str) or not isinstance(expected_checksum, str):
            raise ValueError("verified model manifest contains invalid checksum entries")
        artifact = (directory / relative_path).resolve()
        if directory not in artifact.parents or not artifact.is_file():
            raise ValueError("verified model manifest references a missing artifact")
        if artifact.suffix.casefold() in _UNSAFE_WEIGHT_SUFFIXES:
            raise ValueError("verified model directory contains unsafe serialized weights")
        if _sha256(artifact) != expected_checksum:
            raise ValueError(f"model artifact checksum mismatch: {relative_path}")
    return directory


def _default_model_loader(path: str, **kwargs: object) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise RuntimeError(
            "semantic support is not installed; sync the semantic optional dependency"
        ) from error
    return SentenceTransformer(path, **kwargs)


class SentenceTransformerProvider:
    """Load and query a checksum-verified local model without network access."""

    def __init__(
        self,
        model_dir: str | Path,
        *,
        model_loader: ModelLoader | None = None,
    ) -> None:
        self.model_dir = _validated_model_directory(model_dir)
        loader = model_loader or _default_model_loader
        self._model = loader(
            str(self.model_dir),
            local_files_only=True,
            trust_remote_code=False,
        )
        if int(self._model.max_seq_length) != MODEL_MAX_SEQUENCE_LENGTH:
            raise ValueError("loaded model does not expose the verified 128-token limit")

    def _chunks(self, text: str) -> list[str]:
        if not text.strip():
            raise ValueError("semantic text must not be empty")
        tokenizer = self._model.tokenizer
        token_ids = tokenizer.encode(text, add_special_tokens=False)
        special_tokens = int(tokenizer.num_special_tokens_to_add(pair=False))
        content_limit = MODEL_MAX_SEQUENCE_LENGTH - special_tokens
        if content_limit < 1:
            raise ValueError("tokenizer special-token count exceeds model limit")
        if len(token_ids) <= content_limit:
            return [text]
        return [
            tokenizer.decode(token_ids[start : start + content_limit], skip_special_tokens=True)
            for start in range(0, len(token_ids), content_limit)
        ]

    def embed(self, texts: list[str]) -> np.ndarray:
        """Encode, chunk, mean-pool and L2-normalize each input text."""

        vectors: list[np.ndarray] = []
        for text in texts:
            chunk_vectors = [
                np.asarray(
                    self._model.encode(
                        [chunk],
                        normalize_embeddings=True,
                        convert_to_numpy=True,
                        show_progress_bar=False,
                    )[0],
                    dtype=float,
                )
                for chunk in self._chunks(text)
            ]
            pooled = np.mean(np.vstack(chunk_vectors), axis=0)
            norm = float(np.linalg.norm(pooled))
            if norm == 0:
                raise ValueError("semantic model returned a zero embedding")
            vectors.append(pooled / norm)
        if not vectors:
            return np.empty((0, 0), dtype=float)
        return np.vstack(vectors)

    def rank(self, query: str, candidates: list[str]) -> list[RankedText]:
        """Rank candidate texts by cosine similarity to one query."""

        if not candidates:
            return []
        embeddings = self.embed([query, *candidates])
        scores = embeddings[1:] @ embeddings[0]
        ranked = [
            RankedText(text=text, score=float(scores[index]), original_index=index)
            for index, text in enumerate(candidates)
        ]
        return sorted(ranked, key=lambda item: (-item.score, item.original_index))

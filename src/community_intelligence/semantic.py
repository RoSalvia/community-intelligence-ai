"""Offline-only provider for one pinned multilingual sentence-transformer."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np

MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
MODEL_MAX_SEQUENCE_LENGTH = 128
MANIFEST_FILENAME = "community_intelligence_manifest.json"
PREFETCH_FLOW_ID = "community_intelligence.prefetch_semantic_model.v2"
PINNED_ARTIFACT_SHA256 = MappingProxyType(
    {
        "1_Pooling/config.json": (
            "4fef0a7e8c8ee36e74c0fad89bab60ade72324442d43f559ea219bb7c2580710"
        ),
        "README.md": (
            "1e98ea05b0de579fcaad3d625b62ea55647142ed674d5f5ebf1440e4bbbb6f23"
        ),
        "config.json": (
            "bca510755ecfe5db7addd38b7c181176bb5b5fc3e8493897f1c5a25fb430f2e6"
        ),
        "config_sentence_transformers.json": (
            "d05a05d11f53531f9313483f14112b6849e90a039c4c37e734bfb73579f72512"
        ),
        "model.safetensors": (
            "7f4f89d628f87ade0e0b57c40affb6402cd77abc8110584d8d35dc86da514ee8"
        ),
        "modules.json": (
            "e4068aab8a95663636c4c28044a95eafdb6492387397ec8283d8f8b31078d645"
        ),
        "sentence_bert_config.json": (
            "3084164002c0bca01b0259c5327123803fce32e660a57feb93184ffead186fc8"
        ),
        "tokenizer.json": (
            "cad551d5600a84242d0973327029452a1e3672ba6313c2a3c3d69c4310e12719"
        ),
        "tokenizer_config.json": (
            "52202d0e04ff99028314e47c17f34b434d464d5329439874caedaefa9408e047"
        ),
    }
)
_UNSAFE_WEIGHT_SUFFIXES = {".bin", ".joblib", ".pickle", ".pkl", ".pt", ".pth"}

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
    """Verify and describe the exact pinned artifact for offline loading."""

    directory = Path(model_dir).resolve()
    root_manifest = directory / MANIFEST_FILENAME
    files = {
        path.relative_to(directory).as_posix(): _sha256(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path != root_manifest
    }
    if not files:
        raise ValueError("model directory contains no artifacts")
    if any(
        Path(relative_path).suffix.casefold() in _UNSAFE_WEIGHT_SUFFIXES
        for relative_path in files
    ):
        raise ValueError("model directory contains unsafe serialized weights")
    if "model.safetensors" not in files:
        raise ValueError("pinned artifact requires model.safetensors")
    if files != dict(PINNED_ARTIFACT_SHA256):
        raise ValueError("model directory does not match pinned artifact SHA-256 identity")
    return {
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "max_seq_length": MODEL_MAX_SEQUENCE_LENGTH,
        "safe_serialization": True,
        "files": files,
        "provenance": {
            "flow_id": PREFETCH_FLOW_ID,
            "source_model_id": MODEL_ID,
            "source_revision": MODEL_REVISION,
        },
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
        if path.is_file() and path != manifest_path
    }
    if any(
        Path(relative_path).suffix.casefold() in _UNSAFE_WEIGHT_SUFFIXES
        for relative_path in actual_files
    ):
        raise ValueError("verified model directory contains unsafe serialized weights")
    if "model.safetensors" not in actual_files:
        raise ValueError("verified model directory requires model.safetensors")
    if actual_files != set(files):
        raise ValueError("verified model directory contains unlisted or missing artifacts")
    if files != dict(PINNED_ARTIFACT_SHA256):
        raise ValueError("verified model manifest checksum identity is not the pinned artifact")
    provenance = manifest.get("provenance")
    expected_provenance = {
        "flow_id": PREFETCH_FLOW_ID,
        "source_model_id": MODEL_ID,
        "source_revision": MODEL_REVISION,
    }
    if provenance is not None and provenance != expected_provenance:
        raise ValueError("verified model manifest has invalid prefetch provenance")
    # Legacy manifests from the same prefetch script did not include a provenance
    # object. Their complete, immutable pinned hash set plus the top-level source
    # and revision is sufficient to recognize the already-prefetched artifact.
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

    def _chunks(self, text: str) -> list[tuple[str, int]]:
        if not text.strip():
            raise ValueError("semantic text must not be empty")
        tokenizer = self._model.tokenizer
        token_ids = tokenizer.encode(text, add_special_tokens=False)
        if not token_ids:
            raise ValueError("semantic text is semantically empty: tokenizer produced zero tokens")
        special_tokens = int(tokenizer.num_special_tokens_to_add(pair=False))
        content_limit = MODEL_MAX_SEQUENCE_LENGTH - special_tokens
        if content_limit < 1:
            raise ValueError("tokenizer special-token count exceeds model limit")
        if len(token_ids) <= content_limit:
            return [(text, len(token_ids))]
        return [
            (
                tokenizer.decode(
                    token_ids[start : start + content_limit], skip_special_tokens=True
                ),
                len(token_ids[start : start + content_limit]),
            )
            for start in range(0, len(token_ids), content_limit)
        ]

    def embed(self, texts: list[str]) -> np.ndarray:
        """Encode, chunk, mean-pool and L2-normalize each input text."""

        vectors: list[np.ndarray] = []
        for text in texts:
            chunks = self._chunks(text)
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
                for chunk, _token_count in chunks
            ]
            pooled = np.average(
                np.vstack(chunk_vectors),
                axis=0,
                weights=[token_count for _chunk, token_count in chunks],
            )
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

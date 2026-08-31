import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from community_intelligence.semantic import (
    MANIFEST_FILENAME,
    MODEL_ID,
    MODEL_REVISION,
    SentenceTransformerProvider,
    build_model_manifest,
)


class FakeTokenizer:
    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]:
        assert add_special_tokens is False
        return [int(token.removeprefix("t")) for token in text.split()]

    def decode(self, token_ids: list[int], *, skip_special_tokens: bool) -> str:
        assert skip_special_tokens is True
        return " ".join(f"t{token_id}" for token_id in token_ids)

    def num_special_tokens_to_add(self, *, pair: bool) -> int:
        assert pair is False
        return 2


class FakeModel:
    max_seq_length = 128
    tokenizer = FakeTokenizer()

    def __init__(self) -> None:
        self.encoded_batches: list[tuple[str, ...]] = []

    def encode(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
        show_progress_bar: bool,
    ) -> np.ndarray:
        assert normalize_embeddings is True
        assert convert_to_numpy is True
        assert show_progress_bar is False
        self.encoded_batches.append(tuple(texts))
        vectors = []
        for text in texts:
            token_ids = self.tokenizer.encode(text, add_special_tokens=False)
            vectors.append([float(sum(token_ids)), float(len(token_ids))])
        values = np.asarray(vectors, dtype=float)
        norms = np.linalg.norm(values, axis=1, keepdims=True)
        return values / np.where(norms == 0, 1.0, norms)


def local_model_dir(tmp_path: Path) -> Path:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.safetensors").write_bytes(b"synthetic-safe-model")
    (model_dir / "config.json").write_text('{"synthetic": true}\n', encoding="utf-8")
    manifest = build_model_manifest(model_dir)
    (model_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    return model_dir


def test_model_target_is_exactly_pinned() -> None:
    assert MODEL_ID == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert MODEL_REVISION == "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


def test_provider_rejects_remote_or_unverified_model_identifiers(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="remote model identifiers are rejected"):
        SentenceTransformerProvider(MODEL_ID)

    unverified = tmp_path / "unverified"
    unverified.mkdir()
    with pytest.raises(ValueError, match="verified model manifest"):
        SentenceTransformerProvider(unverified)


def test_provider_rejects_modified_local_artifact(tmp_path: Path) -> None:
    model_dir = local_model_dir(tmp_path)
    (model_dir / "config.json").write_text('{"tampered": true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="checksum"):
        SentenceTransformerProvider(model_dir)


def test_provider_rejects_unlisted_or_unsafe_local_artifact(tmp_path: Path) -> None:
    model_dir = local_model_dir(tmp_path)
    (model_dir / "pytorch_model.bin").write_bytes(b"unlisted-unsafe-weights")

    with pytest.raises(ValueError, match="unlisted|unsafe"):
        SentenceTransformerProvider(model_dir, model_loader=lambda *args, **kwargs: FakeModel())


def test_provider_loads_local_only_and_chunks_at_128_token_limit(tmp_path: Path) -> None:
    model_dir = local_model_dir(tmp_path)
    fake_model = FakeModel()
    loader_calls: list[tuple[str, bool, bool]] = []

    def loader(path: str, *, local_files_only: bool, trust_remote_code: bool) -> FakeModel:
        loader_calls.append((path, local_files_only, trust_remote_code))
        return fake_model

    provider = SentenceTransformerProvider(model_dir, model_loader=loader)
    long_text = " ".join(f"t{index}" for index in range(1, 301))

    vector = provider.embed([long_text])[0]

    assert loader_calls == [(str(model_dir.resolve()), True, False)]
    assert [len(batch[0].split()) for batch in fake_model.encoded_batches] == [126, 126, 48]
    assert np.linalg.norm(vector) == pytest.approx(1.0)


def test_cosine_rank_is_descending_and_stable(tmp_path: Path) -> None:
    model_dir = local_model_dir(tmp_path)
    provider = SentenceTransformerProvider(
        model_dir, model_loader=lambda *args, **kwargs: FakeModel()
    )

    ranked = provider.rank("t9 t10", ["t1 t2", "t8 t9", "t3 t4"])

    assert [item.text for item in ranked] == ["t8 t9", "t3 t4", "t1 t2"]
    assert ranked[0].score >= ranked[1].score >= ranked[2].score


def test_manifest_records_sha256_for_every_model_artifact(tmp_path: Path) -> None:
    model_dir = local_model_dir(tmp_path)
    manifest = json.loads((model_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))

    assert manifest["model_id"] == MODEL_ID
    assert manifest["revision"] == MODEL_REVISION
    assert manifest["max_seq_length"] == 128
    assert manifest["safe_serialization"] is True
    assert set(manifest["files"]) == {"config.json", "model.safetensors"}
    assert manifest["files"]["model.safetensors"] == hashlib.sha256(
        b"synthetic-safe-model"
    ).hexdigest()


@pytest.fixture
def local_semantic_model() -> Path:
    configured = os.environ.get("COMMUNITY_INTELLIGENCE_SEMANTIC_MODEL")
    candidate = Path(configured) if configured else Path(
        "data/generated/models/paraphrase-multilingual-MiniLM-L12-v2-e8f8c211"
    )
    if not (candidate / MANIFEST_FILENAME).is_file():
        pytest.skip("prefetched verified semantic model is not available locally")
    return candidate


@pytest.mark.semantic
def test_multilingual_model_ranks_correct_claim_first(local_semantic_model: Path) -> None:
    provider = SentenceTransformerProvider(local_semantic_model)
    ranked = provider.rank(
        "Stake before Friday to qualify for rewards",
        ["质押截止时间是星期五", "今天价格有波动", "欢迎新成员"],
    )
    assert ranked[0].text == "质押截止时间是星期五"
    assert ranked[0].score > ranked[1].score

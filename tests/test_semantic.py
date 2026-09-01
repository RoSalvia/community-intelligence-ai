import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pytest

import community_intelligence.semantic as semantic_module
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


def local_model_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    fake_hashes: dict[str, str] = {}
    for relative_path in semantic_module.PINNED_ARTIFACT_SHA256:
        artifact = model_dir / relative_path
        artifact.parent.mkdir(parents=True, exist_ok=True)
        content = f"synthetic:{relative_path}".encode()
        artifact.write_bytes(content)
        fake_hashes[relative_path] = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(
        semantic_module, "PINNED_ARTIFACT_SHA256", MappingProxyType(fake_hashes)
    )
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


def test_provider_rejects_modified_local_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = local_model_dir(tmp_path, monkeypatch)
    (model_dir / "config.json").write_text('{"tampered": true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="checksum"):
        SentenceTransformerProvider(model_dir)


def test_provider_rejects_unlisted_or_unsafe_local_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = local_model_dir(tmp_path, monkeypatch)
    (model_dir / "weights.pkl").write_bytes(b"unlisted-unsafe-weights")

    with pytest.raises(ValueError, match="unlisted|unsafe"):
        SentenceTransformerProvider(model_dir, model_loader=lambda *args, **kwargs: FakeModel())


def test_provider_loads_local_only_and_chunks_at_128_token_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = local_model_dir(tmp_path, monkeypatch)
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


def test_cosine_rank_is_descending_and_stable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = local_model_dir(tmp_path, monkeypatch)
    provider = SentenceTransformerProvider(
        model_dir, model_loader=lambda *args, **kwargs: FakeModel()
    )

    ranked = provider.rank("t9 t10", ["t1 t2", "t8 t9", "t3 t4"])

    assert [item.text for item in ranked] == ["t8 t9", "t3 t4", "t1 t2"]
    assert ranked[0].score >= ranked[1].score >= ranked[2].score


def test_manifest_records_sha256_identity_and_prefetch_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = local_model_dir(tmp_path, monkeypatch)
    manifest = json.loads((model_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))

    assert manifest["model_id"] == MODEL_ID
    assert manifest["revision"] == MODEL_REVISION
    assert manifest["max_seq_length"] == 128
    assert manifest["safe_serialization"] is True
    assert manifest["files"] == dict(semantic_module.PINNED_ARTIFACT_SHA256)
    assert manifest["provenance"] == {
        "flow_id": semantic_module.PREFETCH_FLOW_ID,
        "source_model_id": MODEL_ID,
        "source_revision": MODEL_REVISION,
    }


def test_manifest_rejects_pickle_only_and_alternative_safetensors_dirs(
    tmp_path: Path,
) -> None:
    pickle_dir = tmp_path / "pickle"
    pickle_dir.mkdir()
    (pickle_dir / "weights.pkl").write_bytes(b"unsafe")
    with pytest.raises(ValueError, match="unsafe|safetensors|pinned"):
        build_model_manifest(pickle_dir)

    alternative = tmp_path / "alternative"
    alternative.mkdir()
    for relative_path in semantic_module.PINNED_ARTIFACT_SHA256:
        artifact = alternative / relative_path
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(f"alternative:{relative_path}".encode())
    with pytest.raises(ValueError, match="pinned artifact SHA-256"):
        build_model_manifest(alternative)


def test_nested_manifest_basename_is_an_unexpected_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = local_model_dir(tmp_path, monkeypatch)
    nested_manifest = model_dir / "nested" / MANIFEST_FILENAME
    nested_manifest.parent.mkdir()
    nested_manifest.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="pinned artifact SHA-256"):
        build_model_manifest(model_dir)


class WeightedFakeModel(FakeModel):
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
        token_count = len(self.tokenizer.encode(texts[0], add_special_tokens=False))
        return np.asarray([[1.0, 0.0] if token_count == 126 else [0.0, 1.0]])


def test_chunk_pooling_is_weighted_by_token_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = local_model_dir(tmp_path, monkeypatch)
    provider = SentenceTransformerProvider(
        model_dir, model_loader=lambda *args, **kwargs: WeightedFakeModel()
    )
    text = " ".join(f"t{index}" for index in range(127))

    vector = provider.embed([text])[0]

    assert vector[0] / vector[1] == pytest.approx(126.0)


class TokenlessFakeTokenizer(FakeTokenizer):
    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]:
        assert add_special_tokens is False
        assert set(text) <= {"\u200b", "\u200d", "\ufeff"}
        return []


class TokenlessFakeModel(FakeModel):
    tokenizer = TokenlessFakeTokenizer()

    def encode(self, *args: object, **kwargs: object) -> np.ndarray:
        raise AssertionError("tokenless text must be rejected before model encoding")


@pytest.mark.parametrize("text", ["\u200b", "\u200d", "\ufeff", "\u200b\u200d\ufeff"])
def test_tokenless_semantic_text_is_rejected_before_weighted_pooling(
    text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = local_model_dir(tmp_path, monkeypatch)
    provider = SentenceTransformerProvider(
        model_dir, model_loader=lambda *args, **kwargs: TokenlessFakeModel()
    )

    with pytest.raises(ValueError, match="zero tokens|semantically empty"):
        provider.embed([text])


@pytest.fixture
def local_semantic_model() -> Path:
    if importlib.util.find_spec("sentence_transformers") is None:
        pytest.skip("semantic optional dependency is not installed")
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


@pytest.mark.semantic
def test_real_model_rejects_zero_width_only_text(local_semantic_model: Path) -> None:
    provider = SentenceTransformerProvider(local_semantic_model)

    with pytest.raises(ValueError, match="zero tokens|semantically empty"):
        provider.embed(["\u200b\u200d\ufeff"])

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import MappingProxyType, ModuleType

import pytest

import community_intelligence.semantic as semantic_module


def load_prefetch_module() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "prefetch_semantic_model.py"
    spec = importlib.util.spec_from_file_location("prefetch_semantic_model", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_destination_reservation_is_create_only(tmp_path: Path) -> None:
    destination = tmp_path / "model"
    reserve_destination = load_prefetch_module().reserve_destination

    reserved = reserve_destination(destination)

    assert reserved == destination.resolve()
    assert destination.is_dir()
    with pytest.raises(FileExistsError):
        reserve_destination(destination)


def test_existing_empty_directory_is_never_replaced(tmp_path: Path) -> None:
    destination = tmp_path / "model"
    destination.mkdir()
    original_identity = destination.stat()
    reserve_destination = load_prefetch_module().reserve_destination

    with pytest.raises(FileExistsError):
        reserve_destination(destination)

    current_identity = destination.stat()
    assert (current_identity.st_dev, current_identity.st_ino) == (
        original_identity.st_dev,
        original_identity.st_ino,
    )
    assert not tuple(destination.iterdir())


def test_existing_symlink_is_never_replaced(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    destination = tmp_path / "model"
    destination.symlink_to(target, target_is_directory=True)
    reserve_destination = load_prefetch_module().reserve_destination

    with pytest.raises(FileExistsError):
        reserve_destination(destination)

    assert destination.is_symlink()


def test_existing_file_is_never_replaced(tmp_path: Path) -> None:
    destination = tmp_path / "model"
    destination.write_text("existing", encoding="utf-8")
    reserve_destination = load_prefetch_module().reserve_destination

    with pytest.raises(FileExistsError):
        reserve_destination(destination)

    assert destination.read_text(encoding="utf-8") == "existing"


def test_dangling_symlink_entry_is_rejected_without_creating_its_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "missing-target"
    destination = tmp_path / "model"
    destination.symlink_to(target, target_is_directory=True)
    assert os.path.lexists(destination)
    reserve_destination = load_prefetch_module().reserve_destination

    with pytest.raises(FileExistsError):
        reserve_destination(destination)

    assert destination.is_symlink()
    assert not target.exists()


def test_prefetch_cleans_reservation_when_constructor_fails(tmp_path: Path) -> None:
    destination = tmp_path / "model"
    module = load_prefetch_module()

    def failing_loader(*args: object, **kwargs: object) -> object:
        raise RuntimeError("synthetic download failure")

    with pytest.raises(RuntimeError, match="synthetic download failure"):
        module.prefetch(destination, model_loader=failing_loader)

    assert not os.path.lexists(destination)


def test_prefetch_cleans_partial_artifacts_when_save_fails(tmp_path: Path) -> None:
    destination = tmp_path / "model"
    module = load_prefetch_module()

    class SaveFailureModel:
        max_seq_length = 128

        def save_pretrained(self, path: str, *, safe_serialization: bool) -> None:
            assert safe_serialization is True
            (Path(path) / "partial.file").write_bytes(b"partial")
            raise RuntimeError("synthetic save failure")

    with pytest.raises(RuntimeError, match="synthetic save failure"):
        module.prefetch(destination, model_loader=lambda *args, **kwargs: SaveFailureModel())

    assert not os.path.lexists(destination)


def test_prefetch_publishes_completed_verified_manifest_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "model"
    module = load_prefetch_module()
    fake_contents = {
        relative_path: f"synthetic:{relative_path}".encode()
        for relative_path in semantic_module.PINNED_ARTIFACT_SHA256
    }
    fake_hashes = {
        relative_path: hashlib.sha256(content).hexdigest()
        for relative_path, content in fake_contents.items()
    }
    monkeypatch.setattr(semantic_module, "PINNED_ARTIFACT_SHA256", MappingProxyType(fake_hashes))
    loader_calls: list[tuple[str, str, bool]] = []

    class SuccessfulModel:
        max_seq_length = 128

        def save_pretrained(self, path: str, *, safe_serialization: bool) -> None:
            assert safe_serialization is True
            assert not (Path(path) / semantic_module.MANIFEST_FILENAME).exists()
            for relative_path, content in fake_contents.items():
                artifact = Path(path) / relative_path
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_bytes(content)

    def loader(model_id: str, *, revision: str, trust_remote_code: bool) -> SuccessfulModel:
        loader_calls.append((model_id, revision, trust_remote_code))
        return SuccessfulModel()

    result = module.prefetch(destination, model_loader=loader)

    manifest_path = destination / semantic_module.MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result == destination.resolve()
    assert loader_calls == [(semantic_module.MODEL_ID, semantic_module.MODEL_REVISION, False)]
    assert manifest["files"] == fake_hashes
    assert manifest["provenance"]["flow_id"] == semantic_module.PREFETCH_FLOW_ID

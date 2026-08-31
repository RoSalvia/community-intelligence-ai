import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


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
    sentinel = destination / "owner-sentinel"
    sentinel.write_text("existing", encoding="utf-8")
    reserve_destination = load_prefetch_module().reserve_destination

    with pytest.raises(FileExistsError):
        reserve_destination(destination)

    assert sentinel.read_text(encoding="utf-8") == "existing"


def test_existing_symlink_is_never_replaced(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    destination = tmp_path / "model"
    destination.symlink_to(target, target_is_directory=True)
    reserve_destination = load_prefetch_module().reserve_destination

    with pytest.raises(FileExistsError):
        reserve_destination(destination)

    assert destination.is_symlink()

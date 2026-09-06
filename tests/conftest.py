from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def restore_command_imports(tmp_path_factory: pytest.TempPathFactory):
    """Discard modules loaded from test packages after each test."""
    before = dict(sys.modules)
    temporary_root = tmp_path_factory.getbasetemp().resolve()
    example_root = (Path(__file__).parents[1] / "examples").resolve()
    yield
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not isinstance(filename, str):
            continue
        path = Path(filename).resolve()
        if not (path.is_relative_to(temporary_root) or path.is_relative_to(example_root)):
            continue
        if name in before:
            sys.modules[name] = before[name]
        else:
            sys.modules.pop(name, None)
    importlib.invalidate_caches()

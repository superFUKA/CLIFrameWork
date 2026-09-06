from __future__ import annotations

import importlib
from pathlib import Path
from collections.abc import Mapping

import pytest


def write_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    files: Mapping[str, str] | None = None,
) -> Path:
    """Create a package without importing it, preserving lazy-load tests."""
    package = tmp_path / name
    package.mkdir()
    sources = {"__init__.py": "", **(files or {})}
    for relative, source in sources.items():
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    return package

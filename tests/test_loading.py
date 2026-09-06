from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fixtures.packages import write_package

from cli_framework.errors import DefinitionError
from cli_framework.loading import load_command, load_function
from cli_framework.model import CommandDescriptor, SourceDescriptor


def _write_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
) -> Path:
    return write_package(monkeypatch, tmp_path, name)


def _descriptor(name: str, module_name: str, path: Path) -> CommandDescriptor:
    return CommandDescriptor(name, SourceDescriptor(module_name, path, line=1))


def test_command_module_is_imported_only_when_loaded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _write_package(monkeypatch, tmp_path, "lazy_commands")
    marker = tmp_path / "loaded.txt"
    module_path = package / "build.py"
    module_path.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "def command():\n"
        "    return 7\n",
        encoding="utf-8",
    )
    descriptor = _descriptor("build", "lazy_commands.build", module_path)

    assert not marker.exists()
    command = load_command(descriptor)

    assert marker.exists()
    assert command() == 7
    assert command is sys.modules["lazy_commands.build"].command


def test_loading_one_command_does_not_import_sibling_helper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _write_package(monkeypatch, tmp_path, "selected_commands")
    marker = tmp_path / "helper-loaded.txt"
    (package / "helper.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        encoding="utf-8",
    )
    module_path = package / "build.py"
    module_path.write_text("def command(): pass\n", encoding="utf-8")

    load_command(_descriptor("build", "selected_commands.build", module_path))

    assert not marker.exists()
    assert "selected_commands.helper" not in sys.modules


def test_missing_command_after_discovery_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _write_package(monkeypatch, tmp_path, "missing_commands")
    module_path = package / "build.py"
    module_path.write_text("value = 1\n", encoding="utf-8")
    descriptor = _descriptor("build", "missing_commands.build", module_path)

    with pytest.raises(DefinitionError, match="見つかりません") as captured:
        load_command(descriptor)

    assert captured.value.source == descriptor.source
    assert captured.value.route == ("build",)


def test_command_imported_from_another_module_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _write_package(monkeypatch, tmp_path, "foreign_commands")
    (package / "helper.py").write_text("def command(): pass\n", encoding="utf-8")
    module_path = package / "build.py"
    module_path.write_text("from .helper import command\n", encoding="utf-8")

    with pytest.raises(DefinitionError, match="一致しません"):
        load_command(_descriptor("build", "foreign_commands.build", module_path))


def test_command_overwritten_with_non_function_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _write_package(monkeypatch, tmp_path, "changed_commands")
    module_path = package / "build.py"
    module_path.write_text("command = object()\n", encoding="utf-8")

    with pytest.raises(DefinitionError, match="Python関数"):
        load_command(_descriptor("build", "changed_commands.build", module_path))


def test_async_command_at_load_time_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _write_package(monkeypatch, tmp_path, "async_commands")
    module_path = package / "build.py"
    module_path.write_text("async def command(): pass\n", encoding="utf-8")

    with pytest.raises(DefinitionError, match="非同期command"):
        load_command(_descriptor("build", "async_commands.build", module_path))


def test_module_import_failure_is_a_definition_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _write_package(monkeypatch, tmp_path, "broken_commands")
    module_path = package / "build.py"
    module_path.write_text("raise RuntimeError('broken import')\n", encoding="utf-8")
    descriptor = _descriptor("build", "broken_commands.build", module_path)

    with pytest.raises(DefinitionError, match="importできません") as captured:
        load_command(descriptor)

    assert isinstance(captured.value.__cause__, RuntimeError)
    assert captured.value.source == descriptor.source


def test_generic_loader_supports_discovered_lifecycle_function(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _write_package(monkeypatch, tmp_path, "lifecycle_commands")
    module_path = package / "__init__.py"
    module_path.write_text("def setup(): return 'ready'\n", encoding="utf-8")
    source = SourceDescriptor("lifecycle_commands", module_path, line=1)

    setup = load_function(source, "setup")

    assert setup() == "ready"

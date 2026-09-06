from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from cli_framework.discovery import scan_package
from cli_framework.errors import DefinitionError


def _package(name: str, path: Path) -> ModuleType:
    package = ModuleType(name)
    package.__path__ = [str(path)]  # type: ignore[attr-defined]
    return package


def test_scan_detects_docstring_and_top_level_functions(tmp_path: Path) -> None:
    package_path = tmp_path / "commands"
    package_path.mkdir()
    source = package_path / "__init__.py"
    source.write_text(
        '"""管理コマンド。"""\n'
        "\n"
        "def setup():\n"
        "    pass\n"
        "\n"
        "def command():\n"
        "    pass\n"
        "\n"
        "def teardown():\n"
        "    pass\n",
        encoding="utf-8",
    )

    scans = scan_package(_package("sample.commands", package_path))

    assert len(scans) == 1
    scan = scans[0]
    assert scan.source.module_name == "sample.commands"
    assert scan.is_package is True
    assert scan.docstring == "管理コマンド。"
    assert scan.setup is not None and scan.setup.line == 3
    assert scan.command is not None and scan.command.line == 6
    assert scan.teardown is not None and scan.teardown.line == 9


def test_scan_maps_nested_module_names_and_sorts_results(tmp_path: Path) -> None:
    package_path = tmp_path / "commands"
    nested_path = package_path / "admin"
    nested_path.mkdir(parents=True)
    (package_path / "zeta.py").write_text("def command(): pass\n", encoding="utf-8")
    (nested_path / "__init__.py").write_text('"""管理。"""\n', encoding="utf-8")
    (nested_path / "build.py").write_text("def command(): pass\n", encoding="utf-8")

    scans = scan_package(_package("sample.commands", package_path))

    assert [scan.source.module_name for scan in scans] == [
        "sample.commands.admin",
        "sample.commands.admin.build",
        "sample.commands.zeta",
    ]
    assert [scan.is_package for scan in scans] == [True, False, False]


def test_helper_module_is_scanned_without_being_imported(tmp_path: Path) -> None:
    package_path = tmp_path / "commands"
    package_path.mkdir()
    marker = tmp_path / "imported.txt"
    (package_path / "helper.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "from somewhere import command\n",
        encoding="utf-8",
    )

    scans = scan_package(_package("sample.commands", package_path))

    assert len(scans) == 1
    assert scans[0].command is None
    assert not marker.exists()


def test_scan_ignores_nested_and_imported_command_names(tmp_path: Path) -> None:
    package_path = tmp_path / "commands"
    package_path.mkdir()
    (package_path / "helper.py").write_text(
        "from elsewhere import command\n"
        "if True:\n"
        "    def setup(): pass\n"
        "def wrapper():\n"
        "    def command(): pass\n",
        encoding="utf-8",
    )

    scan = scan_package(_package("sample.commands", package_path))[0]

    assert scan.command is None
    assert scan.setup is None


@pytest.mark.parametrize("function_name", ["command", "setup", "teardown"])
def test_async_special_function_is_a_definition_error(
    tmp_path: Path,
    function_name: str,
) -> None:
    package_path = tmp_path / "commands"
    package_path.mkdir()
    source = package_path / "job.py"
    source.write_text(f"async def {function_name}(): pass\n", encoding="utf-8")

    with pytest.raises(DefinitionError) as captured:
        scan_package(_package("sample.commands", package_path))

    assert f"非同期{function_name}関数" in str(captured.value)
    assert captured.value.source is not None
    assert captured.value.source.module_name == "sample.commands.job"
    assert captured.value.source.line == 1


def test_scan_reports_syntax_error_with_source_location(tmp_path: Path) -> None:
    package_path = tmp_path / "commands"
    package_path.mkdir()
    source = package_path / "broken.py"
    source.write_text("def command(:\n", encoding="utf-8")

    with pytest.raises(DefinitionError) as captured:
        scan_package(_package("sample.commands", package_path))

    assert "構文エラー" in str(captured.value)
    assert captured.value.source is not None
    assert captured.value.source.path == source
    assert captured.value.source.line == 1


def test_scan_rejects_a_non_package_module() -> None:
    module = ModuleType("sample.commands")

    with pytest.raises(DefinitionError, match="Pythonパッケージ"):
        scan_package(module)

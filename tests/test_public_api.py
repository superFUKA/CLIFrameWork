from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import click
import pytest
from fixtures.packages import write_package
from fixtures.runner import CliRunner

import cli_framework
from cli_framework import Context, create_cli, current_context
from cli_framework.errors import CliFrameworkError, DefinitionError


def _import_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    files: dict[str, str],
) -> ModuleType:
    write_package(monkeypatch, tmp_path, name, files)
    return importlib.import_module(name)


def test_public_api_exports_factory_context_and_errors() -> None:
    assert cli_framework.create_cli is create_cli
    assert cli_framework.Context is Context
    assert cli_framework.current_context is current_context
    assert cli_framework.CliFrameworkError is CliFrameworkError
    assert cli_framework.DefinitionError is DefinitionError


def test_create_cli_integrates_routes_bindings_context_and_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_package(
        monkeypatch,
        tmp_path,
        "integrated_commands",
        {
            "__init__.py": (
                "from cli_framework import current_context\n"
                "def setup(): current_context().state['prefix'] = 'ready'\n"
                "def teardown():\n"
                "    assert current_context().exception is None\n"
            ),
            "_name_/__init__.py": '"""プロジェクト操作。"""\n',
            "_name_/build.py": (
                '"""プロジェクトをビルドします。"""\n'
                "from typing import Annotated\n"
                "from cli_framework import current_context\n"
                "def command(source: Annotated[str, '入力元'], jobs: int = 1):\n"
                "    context = current_context()\n"
                "    print(f\"{context.state['prefix']}:{context.get_binding('_name_')}:{source}:{jobs}\")\n"
            ),
        },
    )

    cli = create_cli(
        package,
        name="tool",
        bindings={"_name_": "alpha"},
    )
    result = CliRunner().invoke(
        cli,
        ["alpha", "build", "src", "--jobs", "3"],
    )

    assert isinstance(cli, click.Command)
    assert cli.name == "tool"
    assert result.exit_code == 0
    assert result.stdout == "ready:alpha:src:3\n"


def test_create_cli_uses_last_package_segment_as_default_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application = tmp_path / "default_name_app"
    commands_path = application / "commands"
    commands_path.mkdir(parents=True)
    (application / "__init__.py").write_text("", encoding="utf-8")
    (commands_path / "__init__.py").write_text("", encoding="utf-8")
    (commands_path / "status.py").write_text(
        "def command(): pass\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    package = importlib.import_module("default_name_app.commands")

    cli = create_cli(package)

    assert cli.name == "commands"


def test_create_cli_copies_bindings_at_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_package(
        monkeypatch,
        tmp_path,
        "copied_binding_commands",
        {
            "__init__.py": "",
            "_name_/__init__.py": "",
            "_name_/show.py": (
                "from cli_framework import current_context\n"
                "def command(): print(current_context().get_binding('_name_'))\n"
            ),
        },
    )
    bindings = {"_name_": "original"}
    cli = create_cli(package, bindings=bindings)
    bindings["_name_"] = "changed"

    result = CliRunner().invoke(cli, ["original", "show"])

    assert result.exit_code == 0
    assert result.stdout == "original\n"


def test_create_cli_does_not_import_helper_or_command_modules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    marker = tmp_path / "imported.txt"
    package = _import_package(
        monkeypatch,
        tmp_path,
        "lazy_public_commands",
        {
            "__init__.py": "",
            "helper.py": f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
            "build.py": (
                f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
                "def command(): pass\n"
            ),
        },
    )

    cli = create_cli(package, name="tool")
    help_result = CliRunner().invoke(cli, ["--help"])

    assert help_result.exit_code == 0
    assert not marker.exists()
    assert "lazy_public_commands.helper" not in sys.modules
    assert "lazy_public_commands.build" not in sys.modules


def test_create_cli_propagates_debug_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_package(
        monkeypatch,
        tmp_path,
        "debug_public_commands",
        {
            "__init__.py": "",
            "fail.py": "def command(): raise RuntimeError('public debug')\n",
        },
    )

    result = CliRunner().invoke(
        create_cli(package, debug=True),
        ["fail"],
    )

    assert result.exit_code == 1
    assert "Traceback (most recent call last)" in result.stderr
    assert "RuntimeError: public debug" in result.stderr


def test_create_cli_reports_definition_errors_during_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_package(
        monkeypatch,
        tmp_path,
        "invalid_public_commands",
        {
            "__init__.py": "",
            "_name_/__init__.py": "",
            "_name_/build.py": "def command(): pass\n",
        },
    )

    with pytest.raises(DefinitionError, match="_name_"):
        create_cli(package)


@pytest.mark.parametrize("name", ["", "-tool", "two words", "bad\x00name"])
def test_create_cli_rejects_invalid_explicit_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
) -> None:
    package = _import_package(
        monkeypatch,
        tmp_path,
        f"invalid_name_{len(name)}_{ord(name[0]) if name else 0}",
        {"__init__.py": ""},
    )

    with pytest.raises(DefinitionError, match="CLI名"):
        create_cli(package, name=name)


def test_create_cli_rejects_non_package_module() -> None:
    with pytest.raises(DefinitionError, match="Pythonパッケージ"):
        create_cli(ModuleType("not_a_package"))


def test_command_docstring_is_discovered_without_import(monkeypatch, tmp_path):
    package = _import_package(monkeypatch, tmp_path, "function_help_commands", {
        "__init__.py": '"""Root description."""\n',
        "build.py": '"""Module fallback."""\n'
                    'def command():\n    """Function description."""\n',
        "fallback.py": '"""Fallback description."""\ndef command(): pass\n',
    })
    cli = create_cli(package)
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert result.stderr == ""
    assert "Function description." in result.stdout
    assert "Module fallback." not in result.stdout
    assert "Fallback description." in result.stdout
    assert "function_help_commands.build" not in sys.modules
    detail = CliRunner().invoke(cli, ["build", "--help"])
    assert detail.exit_code == 0
    assert detail.stderr == ""
    assert "Function description." in detail.stdout


@pytest.mark.parametrize("debug", [False, True])
def test_lazy_definition_error_is_reported_at_cli_boundary(monkeypatch, tmp_path, debug):
    package = _import_package(monkeypatch, tmp_path, f"invalid_signature_{debug}", {
        "bad.py": "def command(value: list[str]): pass\n",
    })
    cli = create_cli(package, debug=debug)
    assert CliRunner().invoke(cli, ["--help"]).exit_code == 0
    for args in (["bad", "x"], ["bad", "--help"]):
        result = CliRunner().invoke(cli, args)
        assert result.exit_code == 1
        assert result.stdout == ""
        assert "value" in result.stderr
        assert package.__name__ in result.stderr
        assert ("Traceback" in result.stderr) is debug
    with pytest.raises(DefinitionError):
        cli.main(["bad", "x"], standalone_mode=False)

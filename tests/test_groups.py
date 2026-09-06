from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.packages import write_package
from fixtures.runner import CliRunner

from cli_framework.click_group import build_click_group
from cli_framework.model import CommandDescriptor, GroupDescriptor, SourceDescriptor


def _package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
) -> Path:
    return write_package(monkeypatch, tmp_path, name)


def _command(name: str, module: str, path: Path) -> CommandDescriptor:
    return CommandDescriptor(name, SourceDescriptor(module, path, line=1))


def test_default_command_runs_group_directly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _package(monkeypatch, tmp_path, "default_commands")
    module_path = package / "__init__.py"
    module_path.write_text(
        "def command(target: str = 'all'):\n"
        "    print(f'default:{target}')\n",
        encoding="utf-8",
    )
    root = GroupDescriptor(
        "project",
        command=_command("project", "default_commands", module_path),
    )

    cli = build_click_group(root)
    no_arguments = CliRunner().invoke(cli, [])
    with_option = CliRunner().invoke(cli, ["--target", "one"])

    assert no_arguments.exit_code == 0
    assert no_arguments.stdout == "default:all\n"
    assert with_option.exit_code == 0
    assert with_option.stdout == "default:one\n"


def test_precedence_prefers_exact_child_name_over_default_argument(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _package(monkeypatch, tmp_path, "precedence_commands")
    (package / "__init__.py").write_text(
        "def command(target: str):\n"
        "    print(f'default:{target}')\n",
        encoding="utf-8",
    )
    build_path = package / "build.py"
    build_path.write_text(
        "def command():\n"
        "    print('child:build')\n",
        encoding="utf-8",
    )
    root = GroupDescriptor(
        "project",
        command=_command(
            "project", "precedence_commands", package / "__init__.py"
        ),
        children=(
            _command("build", "precedence_commands.build", build_path),
        ),
    )
    cli = build_click_group(root)

    exact = CliRunner().invoke(cli, ["build"])
    fallback = CliRunner().invoke(cli, ["other"])

    assert exact.exit_code == 0
    assert exact.stdout == "child:build\n"
    assert fallback.exit_code == 0
    assert fallback.stdout == "default:other\n"


def test_precedence_keeps_child_usage_error_instead_of_falling_back(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _package(monkeypatch, tmp_path, "precedence_error_commands")
    (package / "__init__.py").write_text(
        "def command(target: str): pass\n",
        encoding="utf-8",
    )
    child_path = package / "build.py"
    child_path.write_text("def command(source: str): pass\n", encoding="utf-8")
    root = GroupDescriptor(
        "project",
        command=_command(
            "project", "precedence_error_commands", package / "__init__.py"
        ),
        children=(
            _command("build", "precedence_error_commands.build", child_path),
        ),
    )

    result = CliRunner().invoke(build_click_group(root), ["build"])

    assert result.exit_code == 2
    assert "Missing argument" in result.stderr


def test_default_help_loads_signature_without_running_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _package(monkeypatch, tmp_path, "default_help_commands")
    marker = tmp_path / "default-imported.txt"
    module_path = package / "__init__.py"
    module_path.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "from typing import Annotated\n"
        "def setup(): raise AssertionError('setup ran')\n"
        "def teardown(): raise AssertionError('teardown ran')\n"
        "def command(target: Annotated[str, 'Target description'], jobs: int = 2):\n"
        "    raise AssertionError('command ran')\n",
        encoding="utf-8",
    )
    root = GroupDescriptor(
        "project",
        help_text="グループの説明。",
        command=_command("project", "default_help_commands", module_path),
    )

    result = CliRunner().invoke(build_click_group(root), ["--help"])

    assert result.exit_code == 0
    assert "グループの説明。" in result.stdout
    assert marker.exists()
    assert result.stderr == ""
    assert "Default usage:" in result.stdout
    assert "TARGET" in result.stdout
    assert "Target description" in result.stdout
    assert "--jobs INTEGER" in result.stdout


def test_missing_default_command_makes_direct_execution_a_usage_error() -> None:
    root = GroupDescriptor("tool")

    result = CliRunner().invoke(build_click_group(root), [])

    assert result.exit_code == 2
    assert "Usage:" in result.stderr

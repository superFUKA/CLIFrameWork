from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from click import Command
from fixtures.runner import CliRunner


EXAMPLE_ROOT = Path(__file__).parents[1] / "examples" / "example_app"
EXAMPLE_SRC = EXAMPLE_ROOT / "src"


@pytest.fixture
def example_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Command, ModuleType]:
    monkeypatch.syspath_prepend(str(EXAMPLE_SRC))
    importlib.invalidate_caches()
    cli_module = importlib.import_module("example_cli.cli")
    events_module = importlib.import_module("example_cli.commands.events")
    events_module.events.clear()
    return cli_module.cli, events_module


def test_example_project_declares_standard_console_entry_point() -> None:
    metadata = (EXAMPLE_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '[project.scripts]' in metadata
    assert 'example-cli = "example_cli.cli:cli"' in metadata
    assert 'where = ["src"]' in metadata
    assert 'requires-python = ">=3.10"' in metadata


def test_example_exposes_three_level_command_with_binding_and_types(
    example_cli: tuple[Command, ModuleType],
) -> None:
    cli, events_module = example_cli

    result = CliRunner().invoke(
        cli,
        ["demo", "release", "build", "src", "--jobs", "2", "--clean"],
    )

    assert result.exit_code == 0
    assert result.stdout == "example:demo:active:src:jobs=2:clean=True\n"
    assert events_module.events == [
        "root:setup",
        "project:setup:demo",
        "release:setup",
        "build:command",
        "release:teardown",
        "project:teardown",
        "root:teardown",
    ]


def test_example_group_is_directly_executable(
    example_cli: tuple[Command, ModuleType],
) -> None:
    cli, events_module = example_cli

    result = CliRunner().invoke(cli, ["demo", "--target", "summary"])

    assert result.exit_code == 0
    assert result.stdout == "example:demo:summary\n"
    assert events_module.events == [
        "root:setup",
        "project:setup:demo",
        "project:command",
        "project:teardown",
        "root:teardown",
    ]


def test_example_has_useful_help_at_every_level(
    example_cli: tuple[Command, ModuleType],
) -> None:
    cli, events_module = example_cli
    runner = CliRunner()

    root_help = runner.invoke(cli, ["--help"])
    project_help = runner.invoke(cli, ["demo", "--help"])
    release_help = runner.invoke(cli, ["demo", "release", "--help"])
    command_help = runner.invoke(
        cli, ["demo", "release", "build", "--help"]
    )

    assert root_help.exit_code == 0
    assert "サンプルアプリケーションのルートコマンド。" in root_help.stdout
    assert "demo" in root_help.stdout
    assert project_help.exit_code == 0
    assert "bindingで選択されるプロジェクト" in project_help.stdout
    assert "release" in project_help.stdout
    assert "--target TEXT" in project_help.stdout
    assert release_help.exit_code == 0
    assert "リリース成果物を操作します。" in release_help.stdout
    assert "build" in release_help.stdout
    assert command_help.exit_code == 0
    assert "リリース成果物をビルドします。" in command_help.stdout
    assert "入力元" in command_help.stdout
    assert "--jobs INTEGER" in command_help.stdout
    assert "--clean / --no-clean" in command_help.stdout
    assert events_module.events == []


def test_example_package_can_run_through_module_entry(
    tmp_path: Path,
) -> None:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env["PYTHONPATH"] = os.pathsep.join([
        str(EXAMPLE_SRC), str(EXAMPLE_ROOT.parents[1] / "src"),
    ])
    result = subprocess.run(
        [sys.executable, "-m", "example_cli", "demo", "--target", "summary"],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0
    assert result.stdout == "example:demo:summary\n"
    assert result.stderr == ""

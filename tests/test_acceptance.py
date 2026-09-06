from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest
from fixtures.packages import write_package
from fixtures.runner import CliRunner

from cli_framework import DefinitionError, create_cli


def _import_command_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    files: dict[str, str],
) -> ModuleType:
    """利用者が用意するコマンドパッケージを一時ディレクトリに構築する。"""

    write_package(monkeypatch, tmp_path, name, files)
    return importlib.import_module(name)


def test_directory_cli_acceptance_happy_path_and_help(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_command_package(
        monkeypatch,
        tmp_path,
        "acceptance_happy_commands",
        {
            "events.py": "events = []\n",
            "__init__.py": (
                '"""配布作業を管理します。"""\n'
                "from cli_framework import current_context\n"
                "from .events import events\n"
                "def setup():\n"
                "    current_context().state['root'] = 'ready'\n"
                "    events.append('root-setup')\n"
                "def teardown():\n"
                "    events.append('root-teardown:' + str(current_context().exception))\n"
            ),
            "_tenant_/__init__.py": (
                '"""テナントを選択します。"""\n'
                "from cli_framework import current_context\n"
                "from ..events import events\n"
                "def setup():\n"
                "    events.append('tenant-setup:' + current_context().get_binding('_tenant_'))\n"
                "def teardown():\n"
                "    events.append('tenant-teardown:' + str(current_context().exception))\n"
            ),
            "_tenant_/release/__init__.py": (
                '"""リリースを操作します。"""\n'
                "from cli_framework import current_context\n"
                "from ...events import events\n"
                "def setup():\n"
                "    events.append('release-setup:' + current_context().state['root'])\n"
                "def teardown():\n"
                "    events.append('release-teardown:' + str(current_context().exception))\n"
            ),
            "_tenant_/release/build.py": (
                '"""成果物をビルドします。"""\n'
                "from typing import Annotated\n"
                "from cli_framework import current_context\n"
                "from ...events import events\n"
                "def command(\n"
                "    source: Annotated[str, '入力元'],\n"
                "    count: Annotated[int, '反復回数'] = 2,\n"
                "    ratio: Annotated[float, '圧縮率'] = 1.5,\n"
                "    clean: Annotated[bool, '事前に削除する'] = False,\n"
                "):\n"
                "    context = current_context()\n"
                "    events.append('command')\n"
                "    print(f\"{context.get_binding('_tenant_')}:{source}:{type(source).__name__}\")\n"
                "    print(f\"{count}:{type(count).__name__}:{ratio}:{type(ratio).__name__}:{clean}:{type(clean).__name__}\")\n"
                "    return 0\n"
            ),
        },
    )
    cli = create_cli(
        package,
        name="ship",
        bindings={"_tenant_": "acme"},
    )
    runner = CliRunner()

    root_help = runner.invoke(cli, ["--help"])
    tenant_help = runner.invoke(cli, ["acme", "--help"])
    release_help = runner.invoke(cli, ["acme", "release", "--help"])
    command_help = runner.invoke(
        cli, ["acme", "release", "build", "--help"]
    )
    events = importlib.import_module("acceptance_happy_commands.events").events

    assert root_help.exit_code == 0
    assert "配布作業を管理します。" in root_help.stdout
    assert tenant_help.exit_code == 0
    assert "テナントを選択します。" in tenant_help.stdout
    assert release_help.exit_code == 0
    assert "リリースを操作します。" in release_help.stdout
    assert command_help.exit_code == 0
    assert "成果物をビルドします。" in command_help.stdout
    assert "入力元" in command_help.stdout
    assert "反復回数" in command_help.stdout
    assert "圧縮率" in command_help.stdout
    assert "--clean / --no-clean" in command_help.stdout
    assert events == []

    result = runner.invoke(
        cli,
        [
            "acme",
            "release",
            "build",
            "src",
            "--count",
            "3",
            "--ratio",
            "2.25",
            "--clean",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == "acme:src:str\n3:int:2.25:float:True:bool\n"
    assert result.stderr == ""
    assert events == [
        "root-setup",
        "tenant-setup:acme",
        "release-setup:ready",
        "command",
        "release-teardown:None",
        "tenant-teardown:None",
        "root-teardown:None",
    ]


def test_exact_child_has_priority_over_group_default_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_command_package(
        monkeypatch,
        tmp_path,
        "acceptance_precedence_commands",
        {
            "__init__.py": "",
            "_tenant_/__init__.py": (
                "def command(target: str):\n"
                "    print('default:' + target)\n"
            ),
            "_tenant_/build.py": (
                "def command():\n"
                "    print('child:build')\n"
            ),
        },
    )
    cli = create_cli(package, bindings={"_tenant_": "acme"})
    runner = CliRunner()

    child = runner.invoke(cli, ["acme", "build"])
    fallback = runner.invoke(cli, ["acme", "other"])

    assert child.exit_code == 0
    assert child.stdout == "child:build\n"
    assert fallback.exit_code == 0
    assert fallback.stdout == "default:other\n"


def test_binding_collision_is_rejected_during_cli_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_command_package(
        monkeypatch,
        tmp_path,
        "acceptance_collision_commands",
        {
            "__init__.py": "",
            "_target_.py": "def command(): pass\n",
            "acme.py": "def command(): pass\n",
        },
    )

    with pytest.raises(DefinitionError, match="衝突"):
        create_cli(package, bindings={"_target_": "acme"})


def test_lifecycle_failure_uses_stderr_and_preserves_the_primary_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_command_package(
        monkeypatch,
        tmp_path,
        "acceptance_failure_commands",
        {
            "events.py": "events = []\n",
            "__init__.py": (
                "from cli_framework import current_context\n"
                "from .events import events\n"
                "def setup(): events.append('setup')\n"
                "def teardown():\n"
                "    events.append('teardown:' + str(current_context().exception))\n"
                "    raise OSError('cleanup failed')\n"
            ),
            "run.py": (
                "from .events import events\n"
                "def command():\n"
                "    print('started')\n"
                "    events.append('command')\n"
                "    raise RuntimeError('run failed')\n"
            ),
        },
    )

    result = CliRunner().invoke(create_cli(package), ["run"])
    events = importlib.import_module("acceptance_failure_commands.events").events

    assert result.exit_code == 1
    assert result.stdout == "started\n"
    assert result.stderr == "Error: run failed\n"
    assert "Traceback" not in result.stderr
    assert "cleanup failed" not in result.stderr
    assert events == ["setup", "command", "teardown:run failed"]


def test_exit_codes_distinguish_success_custom_usage_and_application_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_command_package(
        monkeypatch,
        tmp_path,
        "acceptance_exit_commands",
        {
            "__init__.py": "",
            "ok.py": "def command(): pass\n",
            "custom.py": "def command(): return 7\n",
            "need.py": "def command(value: int): pass\n",
            "fail.py": "def command(): raise ValueError('application failed')\n",
        },
    )
    cli = create_cli(package)
    runner = CliRunner()

    success = runner.invoke(cli, ["ok"])
    custom = runner.invoke(cli, ["custom"])
    usage = runner.invoke(cli, ["need", "not-an-integer"])
    routing = runner.invoke(cli, ["missing"])
    failure = runner.invoke(cli, ["fail"])

    assert success.exit_code == 0
    assert custom.exit_code == 7
    assert usage.exit_code == 2
    assert routing.exit_code == 2
    assert failure.exit_code == 1
    assert success.stderr == ""
    assert custom.stderr == ""
    assert "Error:" in usage.stderr
    assert "Error:" in routing.stderr
    assert failure.stdout == ""
    assert failure.stderr == "Error: application failed\n"

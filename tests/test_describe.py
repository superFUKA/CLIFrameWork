from __future__ import annotations

import dataclasses
import importlib
import sys
from pathlib import Path
from types import ModuleType

import click
import pytest
from fixtures.packages import write_package

import cli_framework
from cli_framework import (
    CliFrameworkError,
    DefinitionError,
    ParameterInfo,
    RouteInfo,
    create_cli,
    describe_cli,
)

BUILD = '''"""ビルドします。"""
from typing import Annotated


def command(
    source: Annotated[str, "入力元"],
    *targets: Annotated[str, "対象"],
    jobs: Annotated[int, "並列数"] = 1,
    clean_first: bool = False,
    ratio: float = 0.5,
) -> int:
    return 0
'''


def _import_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    files: dict[str, str],
) -> ModuleType:
    write_package(monkeypatch, tmp_path, name, files)
    return importlib.import_module(name)


def _child(route: RouteInfo, *names: str) -> RouteInfo:
    for name in names:
        route = next(child for child in route.children if child.name == name)
    return route


def test_public_api_exports_description() -> None:
    assert cli_framework.describe_cli is describe_cli
    assert cli_framework.RouteInfo is RouteInfo
    assert cli_framework.ParameterInfo is ParameterInfo


def test_describe_cli_returns_the_route_tree_without_importing_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_package(monkeypatch, tmp_path, "describe_tree", {
        "status.py": 'def command():\n    """状態を表示します。"""\n',
        "project/__init__.py": '"""プロジェクト操作"""\n',
        "project/build.py": BUILD,
        "project/add.py": "def command(name: str):\n    pass\n",
        "sync/__init__.py": (
            '"""取り込み"""\n\n'
            'def command(force: bool = False):\n    """取り込みます。"""\n'
        ),
        "sync/abort.py": "def command():\n    pass\n",
        "_helper.py": "raise RuntimeError('補助モジュールは読み込まない')\n",
    })

    root = describe_cli(create_cli(package, name="tool"))

    assert (root.name, root.path, root.runnable) == ("tool", (), False)
    assert [child.name for child in root.children] == ["project", "status", "sync"]
    status = _child(root, "status")
    assert (status.path, status.runnable, status.children) == (("status",), True, ())
    assert status.help == status.command_help == "状態を表示します。"
    assert status.module == "describe_tree.status"
    assert status.file == tmp_path / "describe_tree" / "status.py"
    project = _child(root, "project")
    assert (project.help, project.command_help, project.runnable) == (
        "プロジェクト操作", None, False,
    )
    assert project.module == "describe_tree.project"
    assert [child.path for child in project.children] == [
        ("project", "add"), ("project", "build"),
    ]
    assert project.parameters() == ()
    sync = _child(root, "sync")
    assert (sync.help, sync.command_help, sync.runnable) == (
        "取り込み", "取り込みます。", True,
    )
    assert [child.name for child in sync.children] == ["abort"]
    for name in ("status", "project.build", "project.add", "sync.abort"):
        assert f"describe_tree.{name}" not in sys.modules


def test_parameters_are_described_in_declaration_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_package(monkeypatch, tmp_path, "describe_params", {
        "build.py": BUILD,
        "sync/__init__.py": "def command(force: bool = False):\n    pass\n",
    })
    cli = create_cli(package, name="tool")
    root = describe_cli(cli)

    parameters = _child(root, "build").parameters()

    assert "describe_params.build" in sys.modules
    assert parameters == (
        ParameterInfo("source", "str", "argument", True, False, None, "入力元", None, None),
        ParameterInfo("targets", "str", "argument", False, True, None, "対象", None, None),
        ParameterInfo("jobs", "int", "option", False, False, 1, "並列数", "--jobs", None),
        ParameterInfo(
            "clean_first", "bool", "option", False, False, False, None,
            "--clean-first", "--no-clean-first",
        ),
        ParameterInfo("ratio", "float", "option", False, False, 0.5, None, "--ratio", None),
    )
    assert _child(root, "sync").parameters() == (
        ParameterInfo("force", "bool", "option", False, False, False, None, "--force", "--no-force"),
    )
    # 実際のClickコマンドのOption名と一致する
    assert isinstance(cli, click.Group)
    build = cli.get_command(click.Context(cli), "build")
    assert build is not None
    click_options = {
        parameter.name: (parameter.opts, parameter.secondary_opts)
        for parameter in build.get_params(click.Context(build))
        if isinstance(parameter, click.Option) and parameter.name != "help"
        and "--help" not in parameter.opts
    }
    assert click_options == {
        info.name: ([info.option], [info.negative] if info.negative else [])
        for info in parameters if info.kind == "option"
    }


def test_description_reflects_name_bindings_and_extensions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_package(monkeypatch, tmp_path, "describe_main", {
        "_name_/build.py": "def command():\n    pass\n",
        "file/list.py": "def command():\n    pass\n",
    })
    extension = _import_package(monkeypatch, tmp_path, "describe_plugin", {
        "copy.py": "def command(source: str):\n    pass\n",
    })

    root = describe_cli(create_cli(
        package, name="tool", bindings={"_name_": "alpha"}, extensions=[("file", extension)],
    ))

    assert _child(root, "alpha", "build").path == ("alpha", "build")
    copy = _child(root, "file", "copy")
    assert (copy.path, copy.module) == (("file", "copy"), "describe_plugin.copy")
    assert [info.name for info in copy.parameters()] == ["source"]


def test_parameters_report_definition_errors_like_help_does(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_package(monkeypatch, tmp_path, "describe_errors", {
        "untyped.py": "def command(value):\n    pass\n",
        "clash.py": "def command(help: bool = False):\n    pass\n",
    })

    root = describe_cli(create_cli(package, name="tool"))

    with pytest.raises(DefinitionError, match="型注釈が必要です"):
        _child(root, "untyped").parameters()
    with pytest.raises(DefinitionError, match="--help"):
        _child(root, "clash").parameters()


def test_describe_cli_rejects_other_click_commands() -> None:
    with pytest.raises(CliFrameworkError, match="create_cli"):
        describe_cli(click.Command("other"))


def test_description_is_read_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _import_package(monkeypatch, tmp_path, "describe_frozen", {
        "run.py": "def command(count: int = 1):\n    pass\n",
    })

    root = describe_cli(create_cli(package))

    with pytest.raises(dataclasses.FrozenInstanceError):
        root.name = "other"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        _child(root, "run").parameters()[0].default = 2  # type: ignore[misc]

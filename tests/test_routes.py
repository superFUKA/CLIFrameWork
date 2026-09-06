from pathlib import Path

import pytest

from cli_framework.discovery import ModuleScan
from cli_framework.errors import DefinitionError
from cli_framework.model import CommandDescriptor, GroupDescriptor, SourceDescriptor
from cli_framework.routes import build_route_tree


def _source(module_name: str, filename: str, line: int | None = None) -> SourceDescriptor:
    return SourceDescriptor(module_name, Path(filename), line=line)


def _scan(
    module_name: str,
    filename: str,
    *,
    package: bool = False,
    docstring: str | None = None,
    command: bool = False,
    setup: bool = False,
    teardown: bool = False,
) -> ModuleScan:
    source = _source(module_name, filename)
    return ModuleScan(
        source=source,
        is_package=package,
        docstring=docstring,
        command=_source(module_name, filename, 3) if command else None,
        setup=_source(module_name, filename, 5) if setup else None,
        teardown=_source(module_name, filename, 7) if teardown else None,
    )


def test_tree_builds_nested_groups_and_commands() -> None:
    scans = [
        _scan("app.commands", "commands/__init__.py", package=True, docstring="ルート"),
        _scan("app.commands.project", "commands/project/__init__.py",
              package=True, docstring="プロジェクト", setup=True, teardown=True),
        _scan("app.commands.project.build", "commands/project/build.py",
              command=True, docstring="ビルド"),
    ]

    root = build_route_tree("app.commands", scans)

    assert root.name == "commands"
    assert root.help_text == "ルート"
    project = root.children[0]
    assert isinstance(project, GroupDescriptor)
    assert project.name == "project"
    assert project.help_text == "プロジェクト"
    assert project.setup is not None and project.teardown is not None
    build = project.children[0]
    assert isinstance(build, CommandDescriptor)
    assert build.name == "build"
    assert build.help_text == "ビルド"


def test_tree_keeps_file_and_directory_names_unchanged() -> None:
    scans = [
        _scan("app.commands.admin_tools", "admin_tools/__init__.py", package=True),
        _scan("app.commands.admin_tools.build_release", "admin_tools/build_release.py",
              command=True),
    ]

    root = build_route_tree("app.commands", scans)

    group = root.children[0]
    assert isinstance(group, GroupDescriptor)
    assert group.name == "admin_tools"
    assert group.children[0].name == "build_release"


def test_order_is_deterministic_at_every_level() -> None:
    scans = [
        _scan("app.commands.zeta", "zeta.py", command=True),
        _scan("app.commands.alpha.two", "alpha/two.py", command=True),
        _scan("app.commands.alpha.one", "alpha/one.py", command=True),
        _scan("app.commands.middle", "middle.py", command=True),
    ]

    root = build_route_tree("app.commands", reversed(scans))

    assert [child.name for child in root.children] == ["alpha", "middle", "zeta"]
    alpha = root.children[0]
    assert isinstance(alpha, GroupDescriptor)
    assert [child.name for child in alpha.children] == ["one", "two"]


def test_tree_ignores_helper_modules_and_empty_groups() -> None:
    scans = [
        _scan("app.commands.helpers", "helpers.py"),
        _scan("app.commands.empty", "empty/__init__.py",
              package=True, docstring="空", setup=True),
    ]

    root = build_route_tree("app.commands", scans)

    assert root.children == ()


def test_tree_creates_default_command_for_executable_group() -> None:
    scans = [
        _scan("app.commands.project", "project/__init__.py",
              package=True, docstring="プロジェクト", command=True)
    ]

    root = build_route_tree("app.commands", scans)

    project = root.children[0]
    assert isinstance(project, GroupDescriptor)
    assert project.command is not None
    assert project.command.name == "project"
    assert project.command.help_text == "プロジェクト"


def test_duplicate_command_names_are_rejected() -> None:
    scans = [
        _scan("app.commands.build", "root-a/build.py", command=True),
        _scan("app.commands.build", "root-b/build.py", command=True),
    ]

    with pytest.raises(DefinitionError, match="コマンドが複数") as captured:
        build_route_tree("app.commands", scans)

    assert captured.value.route == ("commands", "build")


def test_duplicate_group_and_command_names_are_rejected() -> None:
    scans = [
        _scan("app.commands.deploy", "deploy.py", command=True),
        _scan("app.commands.deploy.run", "deploy/run.py", command=True),
    ]

    with pytest.raises(DefinitionError, match="グループとコマンド") as captured:
        build_route_tree("app.commands", scans)

    assert captured.value.route == ("commands", "deploy")


def test_duplicate_package_definitions_are_rejected() -> None:
    scans = [
        _scan("app.commands", "root-a/__init__.py", package=True),
        _scan("app.commands", "root-b/__init__.py", package=True),
    ]

    with pytest.raises(DefinitionError, match="パッケージの定義が複数"):
        build_route_tree("app.commands", scans)

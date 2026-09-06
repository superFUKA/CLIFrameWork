from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.packages import write_package
from fixtures.runner import CliRunner

from cli_framework.click_group import RouteGroup, build_click_group
from cli_framework.model import CommandDescriptor, GroupDescriptor, SourceDescriptor


def _package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
) -> Path:
    return write_package(monkeypatch, tmp_path, name)


def _command(name: str, module: str, path: Path, help_text: str) -> CommandDescriptor:
    return CommandDescriptor(
        name,
        SourceDescriptor(module, path, line=1),
        help_text=help_text,
    )


def test_nested_groups_dispatch_to_a_three_level_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _package(monkeypatch, tmp_path, "nested_commands")
    admin = package / "admin"
    project = admin / "project"
    project.mkdir(parents=True)
    (admin / "__init__.py").write_text("", encoding="utf-8")
    (project / "__init__.py").write_text("", encoding="utf-8")
    module_path = project / "build.py"
    module_path.write_text(
        "def command(target: str):\n"
        "    print(f'built:{target}')\n",
        encoding="utf-8",
    )
    leaf = _command(
        "build", "nested_commands.admin.project.build", module_path, "ビルド"
    )
    root = GroupDescriptor(
        "tool",
        children=(
            GroupDescriptor(
                "admin",
                children=(GroupDescriptor("project", children=(leaf,)),),
            ),
        ),
    )

    cli = build_click_group(root)
    result = CliRunner().invoke(cli, ["admin", "project", "build", "release"])

    assert result.exit_code == 0
    assert result.stdout == "built:release\n"
    assert isinstance(cli, RouteGroup)
    assert cli.descriptor is root


def test_help_uses_directory_and_command_docstrings_without_importing_children(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _package(monkeypatch, tmp_path, "group_help_commands")
    marker = tmp_path / "imported.txt"
    module_path = package / "build.py"
    module_path.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "def command(): pass\n",
        encoding="utf-8",
    )
    leaf = _command(
        "build", "group_help_commands.build", module_path, "成果物を作成します。"
    )
    root = GroupDescriptor(
        "tool",
        help_text="プロジェクト操作。",
        children=(leaf,),
    )

    result = CliRunner().invoke(build_click_group(root), ["--help"])

    assert result.exit_code == 0
    assert "プロジェクト操作。" in result.output
    assert "build" in result.output
    assert "成果物を作成します。" in result.output
    assert not marker.exists()


def test_help_at_nested_group_uses_its_directory_docstring(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _package(monkeypatch, tmp_path, "nested_help_commands")
    module_path = package / "status.py"
    module_path.write_text("def command(): pass\n", encoding="utf-8")
    leaf = _command(
        "status", "nested_help_commands.status", module_path, "状態表示"
    )
    root = GroupDescriptor(
        "tool",
        children=(
            GroupDescriptor("project", help_text="プロジェクト管理。", children=(leaf,)),
        ),
    )

    result = CliRunner().invoke(build_click_group(root), ["project", "--help"])

    assert result.exit_code == 0
    assert "プロジェクト管理。" in result.output
    assert "status" in result.output


def test_order_is_dictionary_order_at_each_group() -> None:
    source = SourceDescriptor("unused", Path("unused.py"), line=1)
    root = GroupDescriptor(
        "tool",
        children=(
            CommandDescriptor("zeta", source, "Z"),
            GroupDescriptor(
                "middle",
                children=(
                    CommandDescriptor("two", source, "2"),
                    CommandDescriptor("one", source, "1"),
                ),
            ),
            CommandDescriptor("alpha", source, "A"),
        ),
    )
    cli = build_click_group(root)

    root_help = CliRunner().invoke(cli, ["--help"]).output
    middle_help = CliRunner().invoke(cli, ["middle", "--help"]).output

    assert root_help.index("alpha") < root_help.index("middle") < root_help.index("zeta")
    assert middle_help.index("one") < middle_help.index("two")


def test_help_does_not_execute_command_or_lifecycle_functions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _package(monkeypatch, tmp_path, "side_effect_help_commands")
    marker = tmp_path / "executed.txt"
    module_path = package / "clean.py"
    module_path.write_text(
        "from pathlib import Path\n"
        f"MARKER = Path({str(marker)!r})\n"
        "def command(): MARKER.touch()\n",
        encoding="utf-8",
    )
    leaf = _command(
        "clean", "side_effect_help_commands.clean", module_path, "掃除"
    )
    lifecycle = SourceDescriptor(
        "side_effect_help_commands",
        package / "__init__.py",
        line=1,
    )
    root = GroupDescriptor(
        "tool",
        setup=lifecycle,
        teardown=lifecycle,
        children=(leaf,),
    )
    cli = build_click_group(root)

    root_result = CliRunner().invoke(cli, ["--help"])
    leaf_result = CliRunner().invoke(cli, ["clean", "--help"])

    assert root_result.exit_code == 0
    assert leaf_result.exit_code == 0
    assert not marker.exists()


def test_nested_unknown_command_is_a_usage_error() -> None:
    root = GroupDescriptor(
        "tool",
        children=(GroupDescriptor("project", children=()),),
    )

    result = CliRunner().invoke(build_click_group(root), ["missing"])

    assert result.exit_code == 2
    assert "No such command" in result.stderr

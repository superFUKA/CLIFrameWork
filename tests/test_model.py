from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from cli_framework.model import (
    CommandDescriptor,
    GroupDescriptor,
    SourceDescriptor,
)


def test_source_descriptor_formats_portable_location() -> None:
    source = SourceDescriptor(
        module_name="my_tool.commands.build",
        path=Path("my_tool/commands/build.py"),
        line=12,
        column=4,
    )

    assert source.location() == "my_tool/commands/build.py:12:4"


def test_source_descriptor_omits_unknown_line_and_column() -> None:
    source = SourceDescriptor("my_tool.commands", Path("my_tool/commands/__init__.py"))

    assert source.location() == "my_tool/commands/__init__.py"


def test_group_descriptor_can_contain_commands_and_groups() -> None:
    source = SourceDescriptor("my_tool.commands.build", Path("commands/build.py"))
    build = CommandDescriptor("build", source, "ビルドします。")
    nested = GroupDescriptor("project", children=(build,))
    root = GroupDescriptor("tool", children=(nested,))

    assert root.children == (nested,)
    assert nested.children == (build,)
    assert build.help_text == "ビルドします。"


def test_group_descriptor_can_have_a_default_command() -> None:
    source = SourceDescriptor("my_tool.commands", Path("commands/__init__.py"))
    default = CommandDescriptor("project", source, "プロジェクトを表示します。")
    group = GroupDescriptor("project", source=source, command=default)

    assert group.command is default
    assert group.source is source


def test_descriptors_are_immutable() -> None:
    source = SourceDescriptor("my_tool.commands.build", Path("commands/build.py"))
    command = CommandDescriptor("build", source)

    with pytest.raises(FrozenInstanceError):
        command.name = "test"  # type: ignore[misc]

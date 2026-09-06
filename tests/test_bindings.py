from pathlib import Path

import pytest

from cli_framework.bindings import resolve_bindings
from cli_framework.errors import DefinitionError
from cli_framework.model import CommandDescriptor, GroupDescriptor, SourceDescriptor


def _source(module: str) -> SourceDescriptor:
    return SourceDescriptor(module, Path(*module.split(".")).with_suffix(".py"))


def _command(name: str) -> CommandDescriptor:
    return CommandDescriptor(name, _source(f"app.commands.{name}"))


def test_resolves_complete_placeholder_segments_recursively() -> None:
    leaf = _command("_action_")
    group_source = _source("app.commands._name_")
    default = CommandDescriptor("_name_", group_source)
    group = GroupDescriptor(
        "_name_",
        source=group_source,
        command=default,
        children=(leaf,),
    )
    root = GroupDescriptor("tool", children=(group,))

    resolved = resolve_bindings(
        root,
        {"_name_": "aaaa", "_action_": "build"},
    )

    resolved_group = resolved.children[0]
    assert isinstance(resolved_group, GroupDescriptor)
    assert resolved_group.name == "aaaa"
    assert resolved_group.command is not None
    assert resolved_group.command.name == "aaaa"
    assert resolved_group.children[0].name == "build"
    assert root.children[0].name == "_name_"


def test_reuses_the_same_binding_at_multiple_locations() -> None:
    root = GroupDescriptor(
        "tool",
        children=(
            GroupDescriptor("_name_", children=(_command("build"),)),
            GroupDescriptor("archive", children=(_command("_name_"),)),
        ),
    )

    resolved = resolve_bindings(root, {"_name_": "project"})

    assert resolved.children[0].name == "archive"
    assert resolved.children[0].children[0].name == "project"  # type: ignore[union-attr]
    assert resolved.children[1].name == "project"


def test_only_a_complete_valid_placeholder_is_replaced() -> None:
    root = GroupDescriptor(
        "tool",
        children=(
            _command("prefix_name_"),
            _command("_1_"),
            _command("_name_suffix"),
        ),
    )

    resolved = resolve_bindings(root, {"_name_": "changed"})

    assert [child.name for child in resolved.children] == [
        "_1_",
        "_name_suffix",
        "prefix_name_",
    ]


def test_unused_bindings_are_allowed_without_value_validation() -> None:
    root = GroupDescriptor("tool", children=(_command("build"),))

    resolved = resolve_bindings(root, {"_unused_": ""})

    assert resolved == root


def test_missing_binding_is_rejected_with_route_and_source() -> None:
    command = _command("_name_")
    root = GroupDescriptor("tool", children=(command,))

    with pytest.raises(DefinitionError, match="_name_") as captured:
        resolve_bindings(root, {})

    assert captured.value.route == ("tool", "_name_")
    assert captured.value.source == command.source


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("", "空文字"),
        ("two words", "空白"),
        ("line\nbreak", "空白"),
        ("bad\x00value", "NUL"),
        ("--option", "開始"),
        (123, "文字列"),
    ],
)
def test_invalid_binding_values_are_rejected(
    value: object,
    reason: str,
) -> None:
    root = GroupDescriptor("tool", children=(_command("_name_"),))

    with pytest.raises(DefinitionError, match=reason):
        resolve_bindings(root, {"_name_": value})  # type: ignore[dict-item]


def test_collision_between_binding_and_fixed_command_is_rejected() -> None:
    root = GroupDescriptor(
        "tool",
        children=(_command("_name_"), _command("build")),
    )

    with pytest.raises(DefinitionError, match="衝突") as captured:
        resolve_bindings(root, {"_name_": "build"})

    assert captured.value.route == ("tool", "build")


def test_collision_between_two_bindings_is_rejected() -> None:
    root = GroupDescriptor(
        "tool",
        children=(_command("_first_"), GroupDescriptor("_second_")),
    )

    with pytest.raises(DefinitionError, match="衝突"):
        resolve_bindings(
            root,
            {"_first_": "same", "_second_": "same"},
        )

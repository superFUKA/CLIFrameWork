"""公開factoryでCLI構築処理を統合する。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import ModuleType

import click

from .bindings import resolve_bindings
from .click_group import build_click_group
from .discovery import scan_package
from .errors import DefinitionError
from .model import GroupDescriptor
from .routes import build_route_tree


def create_cli(
    command_package: ModuleType,
    *,
    name: str | None = None,
    bindings: Mapping[str, str] | None = None,
    debug: bool = False,
) -> click.Command:
    """import済みcommandパッケージからClick互換CLIを構築する。"""

    try:
        active_bindings = dict(bindings or {})
    except (TypeError, ValueError) as error:
        raise DefinitionError("bindingsには文字列mappingが必要です") from error

    scans = scan_package(command_package)
    package_name = command_package.__name__
    root = build_route_tree(package_name, scans)
    if name is not None:
        _validate_cli_name(name)
        root = _rename_root(root, name)
    root = resolve_bindings(root, active_bindings)
    return build_click_group(root, debug=debug, bindings=active_bindings)


def _rename_root(root: GroupDescriptor, name: str) -> GroupDescriptor:
    command = root.command
    if command is not None:
        command = replace(command, name=name)
    return replace(root, name=name, command=command)


def _validate_cli_name(name: str) -> None:
    if not name:
        reason = "空文字にはできません"
    elif name.startswith("-"):
        reason = "「-」で開始できません"
    elif "\x00" in name:
        reason = "NULを含められません"
    elif any(character.isspace() for character in name):
        reason = "空白を含められません"
    else:
        return
    raise DefinitionError(f"CLI名は{reason}")

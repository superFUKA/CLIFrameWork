"""公開factoryでCLI構築処理を統合する。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from types import ModuleType
from typing import Union

import click

from .bindings import resolve_bindings
from .click_group import build_click_group
from .discovery import scan_package
from .errors import DefinitionError
from .model import GroupDescriptor
from .routes import RouteSource, build_route_tree


Extensions = Union[Mapping[str, ModuleType], Iterable[tuple[str, ModuleType]]]

def create_cli(
    command_package: ModuleType,
    *,
    name: str | None = None,
    bindings: Mapping[str, str] | None = None,
    extensions: Extensions | None = None,
    debug: bool = False,
) -> click.Command:
    """import済みcommandパッケージからClick互換CLIを構築する。"""

    try:
        active_bindings = dict(bindings or {})
    except (TypeError, ValueError) as error:
        raise DefinitionError("bindingsには文字列mappingが必要です") from error

    scans = scan_package(command_package)
    package_name = command_package.__name__
    sources = _extension_sources(package_name, extensions)
    root = build_route_tree(package_name, scans, sources)
    if name is not None:
        _validate_cli_name(name)
        root = _rename_root(root, name)
    root = resolve_bindings(root, active_bindings)
    return build_click_group(root, debug=debug, bindings=active_bindings)


def _extension_sources(
    package_name: str,
    extensions: Extensions | None,
) -> tuple[RouteSource, ...]:
    if isinstance(extensions, Mapping):
        extensions = extensions.items()
    try:
        if isinstance(extensions, (str, bytes)):
            raise TypeError
        items = [tuple(item) for item in extensions or ()]
    except TypeError as error:
        raise DefinitionError(
            "extensionsには(拡張先パス, パッケージ)の組の列が必要です"
        ) from error

    package_names = [package_name]
    sources: list[RouteSource] = []
    for item in items:
        if len(item) != 2 or not isinstance(item[0], str):
            raise DefinitionError(
                "extensionsには(拡張先パス, パッケージ)の組の列が必要です"
            )
        mount_path, package = item
        mount = _parse_mount(mount_path)
        scans = scan_package(package)
        extension_name = package.__name__
        for other in package_names:
            if _packages_overlap(extension_name, other):
                raise DefinitionError(
                    f"拡張パッケージ {extension_name!r} が {other!r} と重複しています",
                    route=(package_name, *mount),
                )
        package_names.append(extension_name)
        sources.append(RouteSource(extension_name, scans, mount))
    return tuple(sources)


def _parse_mount(mount_path: str) -> tuple[str, ...]:
    if mount_path == "":
        return ()
    parts = tuple(mount_path.split("/"))
    for part in parts:
        if not part:
            reason = "空の区間を含められません"
        elif part.startswith("-"):
            reason = "「-」で開始する区間を含められません"
        elif "\x00" in part:
            reason = "NULを含められません"
        elif any(character.isspace() for character in part):
            reason = "空白を含められません"
        else:
            continue
        raise DefinitionError(f"拡張先パス {mount_path!r} は{reason}")
    return parts


def _packages_overlap(first: str, second: str) -> bool:
    return (
        first == second
        or first.startswith(f"{second}.")
        or second.startswith(f"{first}.")
    )


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

"""ルートツリーのbindingプレースホルダーを解決する。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace

from .errors import DefinitionError
from .model import GroupDescriptor, RouteDescriptor, SourceDescriptor


_PLACEHOLDER = re.compile(r"^_[A-Za-z][A-Za-z0-9_]*_$")


def resolve_bindings(
    root: GroupDescriptor,
    bindings: Mapping[str, str],
) -> GroupDescriptor:
    """プレースホルダーを置換し、解決後の名前を検証する。"""

    resolved = _resolve_group(root, bindings, ())
    return resolved


def _resolve_group(
    group: GroupDescriptor,
    bindings: Mapping[str, str],
    parent_route: tuple[str, ...],
) -> GroupDescriptor:
    name = _resolve_name(group.name, bindings, group.source, parent_route)
    route = (*parent_route, name)
    children = tuple(
        _resolve_route(child, bindings, route)
        for child in group.children
    )
    _validate_unique_children(children, route)
    children = tuple(sorted(children, key=lambda child: child.name))

    default_command = group.command
    if default_command is not None:
        default_command = replace(default_command, name=name)
    return replace(
        group,
        name=name,
        command=default_command,
        children=children,
    )


def _resolve_route(
    route: RouteDescriptor,
    bindings: Mapping[str, str],
    parent_route: tuple[str, ...],
) -> RouteDescriptor:
    if isinstance(route, GroupDescriptor):
        return _resolve_group(route, bindings, parent_route)
    name = _resolve_name(route.name, bindings, route.source, parent_route)
    return replace(route, name=name)


def _resolve_name(
    name: str,
    bindings: Mapping[str, str],
    source: SourceDescriptor | None,
    parent_route: tuple[str, ...],
) -> str:
    if _PLACEHOLDER.fullmatch(name) is None:
        return name
    if name not in bindings:
        raise DefinitionError(
            f"binding {name!r} が不足しています",
            route=(*parent_route, name),
            source=source,
        )

    value = bindings[name]
    if not isinstance(value, str):
        raise DefinitionError(
            f"binding {name!r} の値は文字列である必要があります",
            route=(*parent_route, name),
            source=source,
        )
    if not value:
        reason = "空文字にはできません"
    elif value.startswith("-"):
        reason = "「-」で開始できません"
    elif "\x00" in value:
        reason = "NULを含められません"
    elif any(character.isspace() for character in value):
        reason = "空白を含められません"
    else:
        return value
    raise DefinitionError(
        f"binding {name!r} の値は{reason}",
        route=(*parent_route, name),
        source=source,
    )


def _validate_unique_children(
    children: tuple[RouteDescriptor, ...],
    parent_route: tuple[str, ...],
) -> None:
    seen: dict[str, RouteDescriptor] = {}
    for child in children:
        previous = seen.get(child.name)
        if previous is not None:
            raise DefinitionError(
                f"binding解決後の名前 {child.name!r} が同じ階層で衝突しています",
                route=(*parent_route, child.name),
                source=child.source,
            )
        seen[child.name] = child

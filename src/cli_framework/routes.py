"""静的探索結果からフレームワーク中立のルートツリーを構築する。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .discovery import ModuleScan
from .errors import DefinitionError
from .model import CommandDescriptor, GroupDescriptor


@dataclass(frozen=True, slots=True)
class RouteSource:
    """拡張先グループへ重ねるパッケージの探索結果。"""

    package_name: str
    scans: tuple[ModuleScan, ...]
    mount: tuple[str, ...] = ()


@dataclass(slots=True)
class _GroupNode:
    name: str
    scans: list[tuple[int, ModuleScan]] = field(default_factory=list)
    groups: dict[str, _GroupNode] = field(default_factory=dict)
    commands: dict[str, CommandDescriptor] = field(default_factory=dict)


def build_route_tree(
    package_name: str,
    scans: Iterable[ModuleScan],
    extensions: Iterable[RouteSource] = (),
) -> GroupDescriptor:
    """探索結果をネストした未解決ルートへ変換する。

    拡張パッケージの内容は、本体の拡張先グループ配下にあるかのように統合する。
    """

    if not package_name:
        raise DefinitionError("ルートパッケージ名が空です")

    root = _GroupNode(package_name.rsplit(".", 1)[-1])
    sources = (RouteSource(package_name, tuple(scans)), *extensions)
    for index, source in enumerate(sources):
        _add_source(root, index, source)
    return _freeze_group(root, (root.name,), keep_empty=True)


def _add_source(root: _GroupNode, index: int, source: RouteSource) -> None:
    for scan in source.scans:
        parts = (*source.mount, *_relative_module_parts(source.package_name, scan))
        if scan.is_package:
            node = _ensure_group(root, parts)
            if any(previous == index for previous, _ in node.scans):
                raise DefinitionError(
                    "同じパッケージの定義が複数あります",
                    route=(root.name, *parts),
                    source=scan.source,
                )
            node.scans.append((index, scan))
        elif scan.command is not None:
            if not parts:
                raise DefinitionError(
                    "末端コマンドのモジュール名が不正です",
                    route=(root.name,),
                    source=scan.source,
                )
            parent = _ensure_group(root, parts[:-1])
            name = parts[-1]
            if name in parent.commands:
                raise DefinitionError(
                    "同じルート名のコマンドが複数あります",
                    route=(root.name, *parts),
                    source=scan.source,
                )
            parent.commands[name] = CommandDescriptor(
                name=name,
                source=scan.command,
                help_text=scan.command_docstring or scan.docstring,
            )


def _relative_module_parts(
    package_name: str,
    scan: ModuleScan,
) -> tuple[str, ...]:
    module_name = scan.source.module_name
    if module_name == package_name:
        return ()
    prefix = f"{package_name}."
    if not module_name.startswith(prefix):
        raise DefinitionError(
            "探索結果がルートパッケージの外側を参照しています",
            route=(package_name,),
            source=scan.source,
        )
    parts = tuple(module_name[len(prefix) :].split("."))
    if any(not part for part in parts):
        raise DefinitionError(
            "探索結果のモジュール名が不正です",
            route=(package_name,),
            source=scan.source,
        )
    return parts


def _ensure_group(root: _GroupNode, parts: tuple[str, ...]) -> _GroupNode:
    node = root
    for part in parts:
        node = node.groups.setdefault(part, _GroupNode(part))
    return node


def _freeze_group(
    node: _GroupNode,
    route: tuple[str, ...],
    *,
    keep_empty: bool = False,
) -> GroupDescriptor:
    duplicate_names = node.groups.keys() & node.commands.keys()
    if duplicate_names:
        name = sorted(duplicate_names)[0]
        command = node.commands[name]
        raise DefinitionError(
            "同じ階層にグループとコマンドの名前が重複しています",
            route=(*route, name),
            source=command.source,
        )

    children: list[CommandDescriptor | GroupDescriptor] = list(node.commands.values())
    for name, child_node in node.groups.items():
        child = _freeze_group(child_node, (*route, name))
        if child.children or child.command is not None:
            children.append(child)
    children.sort(key=lambda child: child.name)

    scans = tuple(scan for _, scan in node.scans)
    command = None
    command_scan = _single_definition(scans, "command", route)
    if command_scan is not None and command_scan.command is not None:
        command = CommandDescriptor(
            name=node.name,
            source=command_scan.command,
            help_text=command_scan.command_docstring or command_scan.docstring,
        )
    setup_scan = _single_definition(scans, "setup", route)
    teardown_scan = _single_definition(scans, "teardown", route)

    if not keep_empty and not children and command is None:
        return GroupDescriptor(name=node.name)
    return GroupDescriptor(
        name=node.name,
        source=scans[0].source if scans else None,
        help_text=next(
            (scan.docstring for scan in scans if scan.docstring is not None),
            None,
        ),
        setup=setup_scan.setup if setup_scan is not None else None,
        teardown=teardown_scan.teardown if teardown_scan is not None else None,
        command=command,
        children=tuple(children),
    )


def _single_definition(
    scans: tuple[ModuleScan, ...],
    function_name: str,
    route: tuple[str, ...],
) -> ModuleScan | None:
    defining = [scan for scan in scans if getattr(scan, function_name) is not None]
    if len(defining) > 1:
        raise DefinitionError(
            f"同じグループの{function_name}関数が複数のパッケージで定義されています",
            route=route,
            source=getattr(defining[1], function_name),
        )
    return defining[0] if defining else None

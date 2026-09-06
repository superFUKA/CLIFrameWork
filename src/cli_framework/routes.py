"""静的探索結果からフレームワーク中立のルートツリーを構築する。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .discovery import ModuleScan
from .errors import DefinitionError
from .model import CommandDescriptor, GroupDescriptor


@dataclass(slots=True)
class _GroupNode:
    name: str
    scan: ModuleScan | None = None
    groups: dict[str, _GroupNode] = field(default_factory=dict)
    commands: dict[str, CommandDescriptor] = field(default_factory=dict)


def build_route_tree(
    package_name: str,
    scans: Iterable[ModuleScan],
) -> GroupDescriptor:
    """探索結果をネストした未解決ルートへ変換する。"""

    if not package_name:
        raise DefinitionError("ルートパッケージ名が空です")

    root = _GroupNode(package_name.rsplit(".", 1)[-1])
    for scan in scans:
        parts = _relative_module_parts(package_name, scan)
        if scan.is_package:
            node = _ensure_group(root, parts)
            if node.scan is not None:
                raise DefinitionError(
                    "同じパッケージの定義が複数あります",
                    route=(root.name, *parts),
                    source=scan.source,
                )
            node.scan = scan
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

    return _freeze_group(root, (root.name,), keep_empty=True)


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

    scan = node.scan
    command = None
    if scan is not None and scan.command is not None:
        command = CommandDescriptor(
            name=node.name,
            source=scan.command,
            help_text=scan.command_docstring or scan.docstring,
        )

    if not keep_empty and not children and command is None:
        return GroupDescriptor(name=node.name)
    return GroupDescriptor(
        name=node.name,
        source=scan.source if scan is not None else None,
        help_text=scan.docstring if scan is not None else None,
        setup=scan.setup if scan is not None else None,
        teardown=scan.teardown if scan is not None else None,
        command=command,
        children=tuple(children),
    )

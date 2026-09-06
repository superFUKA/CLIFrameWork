"""commandパッケージをimportせずに解析する。"""

from __future__ import annotations

import ast
import tokenize
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from .errors import DefinitionError
from .model import SourceDescriptor


_SPECIAL_FUNCTIONS = frozenset({"command", "setup", "teardown"})


@dataclass(frozen=True, slots=True)
class ModuleScan:
    """1つのPythonソースから静的に取得したCLI定義候補。"""

    source: SourceDescriptor
    is_package: bool
    docstring: str | None
    command: SourceDescriptor | None = None
    setup: SourceDescriptor | None = None
    teardown: SourceDescriptor | None = None
    command_docstring: str | None = None


def scan_package(command_package: ModuleType) -> tuple[ModuleScan, ...]:
    """import済みパッケージ配下のPythonソースを再帰的に解析する。"""

    package_name = getattr(command_package, "__name__", None)
    package_paths = getattr(command_package, "__path__", None)
    if not isinstance(package_name, str) or not package_name or package_paths is None:
        raise DefinitionError("探索対象にはimport済みのPythonパッケージが必要です")

    roots = _package_roots(package_name, package_paths)
    scans: list[ModuleScan] = []
    for root in roots:
        for path in sorted(root.rglob("*.py"), key=lambda item: item.as_posix()):
            scans.append(_scan_file(package_name, root, path))
    return tuple(
        sorted(scans, key=lambda scan: (scan.source.module_name, scan.source.path.as_posix()))
    )


def _package_roots(package_name: str, package_paths: Iterable[str]) -> tuple[Path, ...]:
    try:
        roots = tuple(Path(item) for item in package_paths)
    except (TypeError, ValueError) as error:
        raise DefinitionError(
            "パッケージの__path__を読み取れません",
            route=(package_name,),
        ) from error

    if not roots:
        raise DefinitionError(
            "パッケージの__path__が空です",
            route=(package_name,),
        )
    for root in roots:
        if not root.is_dir():
            raise DefinitionError(
                "パッケージの探索パスがディレクトリではありません",
                route=(package_name,),
                source=SourceDescriptor(package_name, root),
            )
    return roots


def _scan_file(package_name: str, root: Path, path: Path) -> ModuleScan:
    module_name, is_package = _module_identity(package_name, root, path)
    module_source = SourceDescriptor(module_name, path)
    try:
        with tokenize.open(path) as source_file:
            source_text = source_file.read()
    except (OSError, UnicodeError, SyntaxError) as error:
        raise DefinitionError(
            "Pythonソースを読み取れません",
            source=module_source,
        ) from error

    try:
        tree = ast.parse(source_text, filename=str(path))
    except SyntaxError as error:
        raise DefinitionError(
            "Pythonソースに構文エラーがあります",
            source=SourceDescriptor(
                module_name,
                path,
                line=error.lineno,
                column=error.offset,
            ),
        ) from error

    definitions: dict[str, SourceDescriptor] = {}
    command_docstring = None
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in _SPECIAL_FUNCTIONS:
            continue
        function_source = SourceDescriptor(
            module_name,
            path,
            line=node.lineno,
            column=node.col_offset + 1,
        )
        if isinstance(node, ast.AsyncFunctionDef):
            raise DefinitionError(
                f"非同期{node.name}関数には対応していません",
                source=function_source,
            )
        definitions[node.name] = function_source
        if node.name == "command":
            command_docstring = ast.get_docstring(node, clean=True)

    return ModuleScan(
        source=module_source,
        is_package=is_package,
        docstring=ast.get_docstring(tree, clean=False),
        command=definitions.get("command"),
        setup=definitions.get("setup"),
        teardown=definitions.get("teardown"),
        command_docstring=command_docstring,
    )


def _module_identity(package_name: str, root: Path, path: Path) -> tuple[str, bool]:
    relative = path.relative_to(root)
    is_package = relative.name == "__init__.py"
    parts = relative.parent.parts if is_package else relative.with_suffix("").parts
    suffix = ".".join(parts)
    if not suffix:
        return package_name, is_package
    return f"{package_name}.{suffix}", is_package

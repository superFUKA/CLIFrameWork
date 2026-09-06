"""探索済みの利用者関数を必要時にimportする。"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from types import ModuleType

from .errors import DefinitionError
from .model import CommandDescriptor, SourceDescriptor


def load_command(descriptor: CommandDescriptor) -> Callable[..., object]:
    """記述子に対応する同期command関数を遅延読み込みする。"""

    return _load_function(
        descriptor.source,
        "command",
        route=(descriptor.name,),
    )


def load_function(
    source: SourceDescriptor,
    function_name: str,
) -> Callable[..., object]:
    """探索済みの同期関数を遅延読み込みする。"""

    return _load_function(source, function_name)


def _load_function(
    source: SourceDescriptor,
    function_name: str,
    *,
    route: tuple[str, ...] = (),
) -> Callable[..., object]:
    module = _import_module(source, route)
    try:
        function = getattr(module, function_name)
    except AttributeError as error:
        raise DefinitionError(
            f"探索済みの{function_name}関数が実行時に見つかりません",
            route=route,
            source=source,
        ) from error

    if not inspect.isfunction(function):
        raise DefinitionError(
            f"{function_name}はPython関数である必要があります",
            route=route,
            source=source,
        )
    if function.__module__ != source.module_name or function.__name__ != function_name:
        raise DefinitionError(
            f"実行時の{function_name}関数が探索結果と一致しません",
            route=route,
            source=source,
        )
    if inspect.iscoroutinefunction(function):
        raise DefinitionError(
            f"非同期{function_name}関数には対応していません",
            route=route,
            source=source,
        )
    return function


def _import_module(
    source: SourceDescriptor,
    route: tuple[str, ...],
) -> ModuleType:
    try:
        return importlib.import_module(source.module_name)
    except Exception as error:
        raise DefinitionError(
            "探索済みモジュールをimportできません",
            route=route,
            source=source,
        ) from error

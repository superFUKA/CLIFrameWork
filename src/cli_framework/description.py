"""構築済みCLIの記述を、Clickの型を含まない読み取り専用データとして公開する。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .click_command import _validate_option_names
from .loading import load_command
from .model import CommandDescriptor, GroupDescriptor, RouteDescriptor
from .parameters import ParameterDescriptor, SupportedValue, inspect_parameters

_TYPE_NAMES = {str: "str", int: "int", float: "float", bool: "bool"}


@dataclass(frozen=True, slots=True)
class ParameterInfo:
    """1つのcommand引数。"""

    name: str
    type: str
    kind: str
    required: bool
    variadic: bool
    default: SupportedValue | None
    help: str | None
    option: str | None
    negative: str | None


@dataclass(frozen=True, slots=True)
class RouteInfo:
    """1つのグループまたは末端コマンド。"""

    name: str
    path: tuple[str, ...]
    help: str | None
    command_help: str | None
    module: str | None
    file: Path | None
    runnable: bool
    children: tuple[RouteInfo, ...] = ()
    _command: CommandDescriptor | None = field(
        default=None, repr=False, compare=False
    )

    def parameters(self) -> tuple[ParameterInfo, ...]:
        """command関数の引数を宣言順に返す。commandモジュールはここで読み込む。"""

        if self._command is None:
            return ()
        command = load_command(self._command)
        parameters = inspect_parameters(
            command, self._command.source, route=(self._command.name,)
        )
        _validate_option_names(parameters, self._command)
        return tuple(_parameter_info(parameter) for parameter in parameters)


def describe_route(
    route: RouteDescriptor,
    path: tuple[str, ...] = (),
) -> RouteInfo:
    """ルート記述子を公開用の記述へ変換する。commandモジュールは読み込まない。"""

    if isinstance(route, GroupDescriptor):
        command = route.command
        source = route.source if route.source is not None else (
            command.source if command is not None else None
        )
        children = tuple(
            describe_route(child, (*path, child.name))
            for child in sorted(route.children, key=lambda child: child.name)
        )
        return RouteInfo(
            name=route.name,
            path=path,
            help=route.help_text,
            command_help=command.help_text if command is not None else None,
            module=source.module_name if source is not None else None,
            file=source.path if source is not None else None,
            runnable=command is not None,
            children=children,
            _command=command,
        )
    return RouteInfo(
        name=route.name,
        path=path,
        help=route.help_text,
        command_help=route.help_text,
        module=route.source.module_name,
        file=route.source.path,
        runnable=True,
        _command=route,
    )


def _parameter_info(parameter: ParameterDescriptor) -> ParameterInfo:
    option: str | None = None
    negative: str | None = None
    if not parameter.is_argument:
        name = parameter.name.replace("_", "-")
        option = f"--{name}"
        if parameter.parameter_type is bool:
            negative = f"--no-{name}"
    return ParameterInfo(
        name=parameter.name,
        type=_TYPE_NAMES[parameter.parameter_type],
        kind="argument" if parameter.is_argument else "option",
        required=parameter.required,
        variadic=parameter.variadic,
        default=parameter.default,
        help=parameter.help_text,
        option=option,
        negative=negative,
    )

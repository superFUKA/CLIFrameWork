"""末端のルート記述子をClickコマンドへ変換する。"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import click

from .loading import load_command
from .errors import DefinitionError
from .model import CommandDescriptor, GroupDescriptor
from .parameters import ParameterDescriptor, inspect_parameters
from .runtime import run_with_lifecycle


class _DocumentedArgument(click.Argument):
    def __init__(self, *args: Any, help_text: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.help_text = help_text


class LeafCommand(click.Command):
    """説明付き位置引数を表示できる末端Clickコマンド。"""

    def format_options(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        arguments = [
            item
            for item in self.params
            if isinstance(item, _DocumentedArgument) and item.help_text is not None
        ]
        if arguments:
            with formatter.section("Arguments"):
                formatter.write_dl(
                    [(item.human_readable_name, item.help_text or "") for item in arguments]
                )
        super().format_options(ctx, formatter)


def build_click_command(
    descriptor: CommandDescriptor,
    *,
    debug: bool = False,
    scopes: Sequence[GroupDescriptor] = (),
    bindings: Mapping[str, str] | None = None,
) -> click.Command:
    """記述子を、元のPython関数を呼び出すClickコマンドへ変換する。"""

    command = load_command(descriptor)
    parameters = inspect_parameters(
        command, descriptor.source, route=(descriptor.name,)
    )
    active_bindings = {} if bindings is None else bindings

    def callback(**values: object) -> None:
        _invoke_command(
            command,
            values,
            debug=debug,
            scopes=scopes,
            bindings=active_bindings,
        )

    return LeafCommand(
        name=descriptor.name,
        callback=callback,
        params=_click_parameters(parameters),
        help=descriptor.help_text,
    )


def _invoke_command(
    command: Callable[..., object],
    values: dict[str, object],
    *,
    debug: bool,
    scopes: Sequence[GroupDescriptor],
    bindings: Mapping[str, str],
) -> None:
    try:
        result = run_with_lifecycle(command, values, scopes, bindings)
        if result is None:
            return
        if type(result) is int:
            if result != 0:
                raise click.exceptions.Exit(result)
            return
        raise TypeError(
            "commandの戻り値はNoneまたはintである必要があります"
            f"（実際: {type(result).__name__}）"
        )
    except (click.exceptions.Exit, DefinitionError):
        raise
    except Exception as error:
        _report_application_error(error, debug=debug)


def _report_application_error(error: Exception, *, debug: bool) -> None:
    if debug:
        traceback.print_exception(
            type(error), error, error.__traceback__, file=sys.stderr
        )
    else:
        message = str(error) or type(error).__name__
        click.echo(f"Error: {message}", err=True)
    raise click.exceptions.Exit(1) from error


def _click_parameters(
    parameters: Sequence[ParameterDescriptor],
) -> list[click.Parameter]:
    return [_click_parameter(parameter) for parameter in parameters]


def _click_parameter(parameter: ParameterDescriptor) -> click.Parameter:
    if parameter.required:
        argument = _DocumentedArgument(
            [parameter.name],
            type=parameter.parameter_type,
            required=True,
            help_text=parameter.help_text,
        )
        argument.name = parameter.name
        return argument
    option_name = parameter.name.replace("_", "-")
    declarations = [f"--{option_name}"]
    kwargs: dict[str, object] = {
        "default": parameter.default,
        "show_default": True,
        "help": parameter.help_text,
    }
    if parameter.parameter_type is bool:
        declarations = [f"--{option_name}/--no-{option_name}"]
    else:
        kwargs["type"] = parameter.parameter_type
    return click.Option([*declarations, parameter.name], **kwargs)

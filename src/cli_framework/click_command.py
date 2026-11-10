"""末端のルート記述子をClickコマンドへ変換する。"""

from __future__ import annotations

import inspect
import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import click

from .click_localization import JapaneseCommandMixin, JapaneseOption
from .description import catalog_node, describe_route
from .loading import load_command, load_function
from .errors import CommandError, DefinitionError
from .model import CommandDescriptor, GroupDescriptor
from .parameters import ParameterDescriptor, inspect_parameters, validate_option_names
from .runtime import run_with_lifecycle
from .structured import (
    JSON_OPTION,
    encode,
    failure_document,
    success_document,
    tokens_before_separator,
)


class _DocumentedArgument(click.Argument):
    def __init__(self, *args: Any, help_text: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.help_text = help_text


class LeafCommand(JapaneseCommandMixin, click.Command):
    """説明付き位置引数を表示できる末端Clickコマンド。"""

    # 構造化出力のCLIでだけ設定する。
    structured_descriptor: CommandDescriptor | None = None
    json_parameter: str = "json"

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        descriptor = self.structured_descriptor
        if descriptor is not None and self._asks_for_catalog(ctx, args):
            path = route_path(ctx)
            info = describe_route(descriptor, path, structured=True)
            click.echo(encode(success_document(help_command(path), catalog_node(info))))
            ctx.exit(0)
        return super().parse_args(ctx, args)

    def _asks_for_catalog(self, ctx: click.Context, args: list[str]) -> bool:
        tokens = tokens_before_separator(args)
        help_names = set(self.get_help_option_names(ctx))
        if JSON_OPTION not in tokens or not help_names & set(tokens):
            return False
        # Clickの解析器で確かめる（Optionの値として渡された同じ文字を除く）。
        help_option = self.get_help_option(ctx)
        try:
            options, _, _ = self.make_parser(ctx).parse_args(list(args))
        except click.UsageError:
            return False
        return (
            help_option is not None
            and bool(options.get(help_option.name))
            and bool(options.get(self.json_parameter))
        )

    def get_help_option(self, ctx: click.Context) -> click.Option | None:
        option = super().get_help_option(ctx)
        if option is not None:
            names = {parameter.name for parameter in self.params}
            name = "help"
            while name in names:
                name = "_" + name
            option.name = name
        return option

    def format_options(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        arguments = [
            item
            for item in self.params
            if isinstance(item, _DocumentedArgument) and item.help_text is not None
        ]
        if arguments:
            with formatter.section("引数"):
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
    structured: bool = False,
) -> click.Command:
    """記述子を、元のPython関数を呼び出すClickコマンドへ変換する。"""

    command = load_command(descriptor)
    parameters = inspect_parameters(
        command, descriptor.source, route=(descriptor.name,)
    )
    validate_option_names(parameters, descriptor, structured=structured)
    active_bindings = {} if bindings is None else bindings
    invoke = (
        _bind_variadic_command(command)
        if any(parameter.variadic for parameter in parameters)
        else command
    )
    click_parameters = _click_parameters(parameters)
    render = None
    json_parameter = "json"
    if structured:
        if descriptor.render is not None:
            render = _load_render(descriptor)
        names = {parameter.name for parameter in parameters}
        while json_parameter in names:  # `json`という位置引数は利用者が使える
            json_parameter = "_" + json_parameter
        click_parameters.append(
            click.Option(
                [JSON_OPTION, json_parameter],
                is_flag=True,
                default=False,
                help="結果をJSONで出力します。",
            )
        )

    def callback(**values: object) -> None:
        as_json = bool(values.pop(json_parameter, False)) if structured else False
        _invoke_command(
            invoke,
            values,
            debug=debug,
            scopes=scopes,
            bindings=active_bindings,
            structured=structured,
            as_json=as_json,
            render=render,
        )

    leaf = LeafCommand(
        name=descriptor.name,
        callback=callback,
        params=click_parameters,
        help=descriptor.help_text,
        options_metavar="[オプション]",
    )
    if structured:
        leaf.structured_descriptor = descriptor
        leaf.json_parameter = json_parameter
    return leaf


def route_path(ctx: click.Context) -> tuple[str, ...]:
    """実行Contextから、ルートCLI名を除く経路を返す。"""

    names: list[str] = []
    current: click.Context | None = ctx
    while current is not None and current.parent is not None:
        names.append(current.info_name or "")
        current = current.parent
    return tuple(reversed(names))


def help_command(path: Sequence[str]) -> str:
    return " ".join(("help", *path))


def _load_render(descriptor: CommandDescriptor) -> Callable[[object], object]:
    assert descriptor.render is not None
    render = load_function(descriptor.render, "render")
    try:
        inspect.signature(render).bind(None)
    except TypeError as error:
        raise DefinitionError(
            "render関数は、結果を1つの位置引数で受け取る必要があります",
            route=(descriptor.name,),
            source=descriptor.render,
        ) from error
    return render


def _with_render(
    command: Callable[..., object],
    render: Callable[[object], object] | None,
    as_json: bool,
) -> Callable[..., object]:
    """人向けの表示（render）を、commandの直後・teardownの前に行う。"""

    if render is None or as_json:
        return command

    def invoke(**values: object) -> object:
        result = command(**values)
        if type(result) is not int:
            text = render(result)
            if text is not None and not isinstance(text, str):
                raise TypeError(
                    "renderの戻り値はstrまたはNoneである必要があります"
                    f"（実際: {type(text).__name__}）"
                )
            if text:
                click.echo(text)
        return result

    return invoke


def _bind_variadic_command(command: Callable[..., object]) -> Callable[..., object]:
    """名前付きの解析値を、通常引数・*args・キーワード専用引数へ戻す。"""
    signature = inspect.signature(command)

    def invoke(**values: object) -> object:
        bound = inspect.BoundArguments(signature, values)
        return command(*bound.args, **bound.kwargs)

    return invoke


def _invoke_command(
    command: Callable[..., object],
    values: dict[str, object],
    *,
    debug: bool,
    scopes: Sequence[GroupDescriptor],
    bindings: Mapping[str, str],
    structured: bool = False,
    as_json: bool = False,
    render: Callable[[object], object] | None = None,
) -> None:
    if structured:
        _invoke_structured(
            _with_render(command, render, as_json),
            values,
            debug=debug,
            scopes=scopes,
            bindings=bindings,
            as_json=as_json,
        )
        return
    try:
        result = run_with_lifecycle(command, values, scopes, bindings)
        if result is None:
            return
        if type(result) is int:
            if result != 0:
                raise click.exceptions.Exit(result)
            return
    except (click.exceptions.Exit, DefinitionError):
        raise
    except Exception as error:
        _report_application_error(error, debug=debug)


def _invoke_structured(
    command: Callable[..., object],
    values: dict[str, object],
    *,
    debug: bool,
    scopes: Sequence[GroupDescriptor],
    bindings: Mapping[str, str],
    as_json: bool,
) -> None:
    """構造化出力のcommandを実行する。`--json`なら、必ずJSONを1つ標準出力へ出す。"""

    context = click.get_current_context(silent=True)
    path = " ".join(route_path(context)) if context is not None else ""
    try:
        result = run_with_lifecycle(
            command, values, scopes, bindings, allow_data=True, json=as_json
        )
    except click.exceptions.Exit:
        raise
    except CommandError as error:
        _fail(path, as_json, error.code, error.message, error.hint)
    except DefinitionError as error:
        if not as_json:
            raise
        _fail(path, True, "definition_error", str(error), None)
    except Exception as error:
        if not as_json:
            _report_application_error(error, debug=debug)
        if debug:
            traceback.print_exception(
                type(error), error, error.__traceback__, file=sys.stderr
            )
            sys.stderr.flush()
        _fail(path, True, "unexpected", str(error) or type(error).__name__, None)
    code = result if type(result) is int else 0
    if as_json:
        document = (
            failure_document(path, "exit_code", f"終了コード {code}")
            if code != 0
            else success_document(path, None if type(result) is int else result)
        )
        try:
            text = encode(document)
        except (TypeError, ValueError) as error:
            _fail(path, True, "unexpected", f"結果をJSONへ変換できません: {error}", None)
        click.echo(text)
    if code != 0:
        raise click.exceptions.Exit(code)


def _fail(
    path: str,
    as_json: bool,
    code: str,
    message: str,
    hint: str | None,
) -> None:
    if as_json:
        click.echo(encode(failure_document(path, code, message, hint)))
    else:
        click.echo(f"エラー: {message}", err=True)
        if hint:
            click.echo(hint, err=True)
    raise click.exceptions.Exit(1)


def _report_application_error(error: Exception, *, debug: bool) -> None:
    if debug:
        traceback.print_exception(
            type(error), error, error.__traceback__, file=sys.stderr
        )
        sys.stderr.flush()
    else:
        message = str(error) or type(error).__name__
        click.echo(f"エラー: {message}", err=True)
    raise click.exceptions.Exit(1) from error


def _click_parameters(
    parameters: Sequence[ParameterDescriptor],
) -> list[click.Parameter]:
    return [_click_parameter(parameter) for parameter in parameters]


def _click_parameter(parameter: ParameterDescriptor) -> click.Parameter:
    if parameter.is_argument:
        argument = _DocumentedArgument(
            [parameter.name],
            type=parameter.parameter_type,
            required=parameter.required,
            nargs=-1 if parameter.variadic else 1,
            help_text=parameter.help_text,
        )
        argument.name = parameter.name
        return argument
    option_name = parameter.name.replace("_", "-")
    declarations = [f"--{option_name}"]
    kwargs: dict[str, object] = {
        "default": parameter.default,
        "show_default": False,
        "help": parameter.help_text,
    }
    if parameter.parameter_type is bool:
        declarations = [f"--{option_name}/--no-{option_name}"]
    else:
        kwargs["type"] = parameter.parameter_type
        kwargs["metavar"] = {str: "文字列", int: "整数", float: "数値"}[parameter.parameter_type]
    return JapaneseOption([*declarations, parameter.name], **kwargs)

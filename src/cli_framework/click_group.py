"""ルート記述子を遅延読み込み対応のClickグループへ変換する。"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from typing import Any

import click

from .click_command import (
    _report_application_error,
    build_click_command,
    help_command,
    route_path,
)
from .click_localization import JapaneseCommandMixin, error_message
from .description import catalog_node, describe_route
from .errors import DefinitionError
from .model import CommandDescriptor, GroupDescriptor, RouteDescriptor
from .structured import (
    JSON_OPTION,
    encode,
    failure_document,
    success_document,
    tokens_before_separator,
)


class LazyLeafCommand(JapaneseCommandMixin, click.Command):
    """パラメーターが必要になるまで利用者モジュールを読み込まない末端。"""

    def __init__(
        self,
        descriptor: CommandDescriptor,
        *,
        debug: bool,
        scopes: Sequence[GroupDescriptor],
        bindings: Mapping[str, str],
        structured: bool = False,
    ) -> None:
        super().__init__(name=descriptor.name, help=descriptor.help_text)
        self.descriptor = descriptor
        self.structured = structured
        self.debug = debug
        self.scopes = tuple(scopes)
        self.bindings = bindings
        self._loaded_command: click.Command | None = None

    def _load(self) -> click.Command:
        if self._loaded_command is None:
            self._loaded_command = build_click_command(
                self.descriptor,
                debug=self.debug,
                scopes=self.scopes,
                bindings=self.bindings,
                structured=self.structured,
            )
        return self._loaded_command

    def get_params(self, ctx: click.Context) -> list[click.Parameter]:
        return self._load().get_params(ctx)

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        return self._load().parse_args(ctx, args)

    def invoke(self, ctx: click.Context) -> Any:
        return self._load().invoke(ctx)

    def get_help(self, ctx: click.Context) -> str:
        return self._load().get_help(ctx)

    def get_usage(self, ctx: click.Context) -> str:
        return self._load().get_usage(ctx)


class RouteGroup(JapaneseCommandMixin, click.Group):
    """対応する中立ルート記述子と任意の既定commandを持つグループ。"""

    def __init__(
        self,
        descriptor: GroupDescriptor,
        *,
        commands: dict[str, click.Command],
        debug: bool,
        scopes: Sequence[GroupDescriptor],
        bindings: Mapping[str, str],
        structured: bool = False,
    ) -> None:
        self.descriptor = descriptor
        self.structured = structured
        self._json_requested = False
        self.default_command = (
            LazyLeafCommand(
                descriptor.command,
                debug=debug,
                scopes=scopes,
                bindings=bindings,
                structured=structured,
            )
            if descriptor.command is not None
            else None
        )
        self._invoke_default = False
        self.debug = debug
        super().__init__(
            name=descriptor.name, help=descriptor.help_text, commands=commands,
            options_metavar="[オプション]", subcommand_metavar="コマンド [引数]...",
        )

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted(super().list_commands(ctx))

    def main(self, *args: Any, **kwargs: Any) -> Any:
        if self.structured:
            given = kwargs.get("args", args[0] if args else None)
            tokens = tokens_before_separator(sys.argv[1:] if given is None else given)
            self._json_requested = JSON_OPTION in tokens
        try:
            return super().main(*args, **kwargs)
        except DefinitionError as error:
            if not kwargs.get("standalone_mode", True):
                raise
            if self._json_requested:
                click.echo(encode(failure_document("", "definition_error", str(error))))
                raise SystemExit(1) from error
            try:
                _report_application_error(error, debug=self.debug)
            except click.exceptions.Exit as exit_error:
                raise SystemExit(exit_error.exit_code) from error

    def show_error(self, error: click.ClickException) -> None:
        if not self._json_requested:
            super().show_error(error)
            return
        # `--json`の実行では、用法エラーもJSONを1つ標準出力へ出す。
        context = getattr(error, "ctx", None)
        path = " ".join(route_path(context)) if context is not None else ""
        click.echo(encode(failure_document(path, "usage_error", error_message(error))))

    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        super().format_usage(ctx, formatter)
        if self.default_command is not None:
            command = self.default_command._load()
            formatter.write_usage(
                ctx.command_path,
                " ".join(command.collect_usage_pieces(ctx)),
                prefix="直接実行の使い方: ",
            )

    def format_options(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        if self.default_command is None:
            super().format_options(ctx, formatter)
            return
        command = self.default_command._load()
        if command.help and command.help != self.help:
            with formatter.section("既定のコマンド"):
                formatter.write_text(command.help)
        command.format_options(ctx, formatter)
        self.format_commands(ctx, formatter)

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if self.structured and self._asks_for_catalog(ctx, args):
            path = route_path(ctx)
            info = describe_route(self.descriptor, path, structured=True)
            click.echo(encode(success_document(help_command(path), catalog_node(info))))
            ctx.exit(0)
        if not args and self.default_command is None and not ctx.resilient_parsing:
            raise click.UsageError("コマンドを指定してください。", ctx)
        if self.default_command is not None and self._uses_default(args):
            self._invoke_default = True
            # 既定コマンド自身が、位置引数の後にあるオプションも解析する。
            # Groupの既定動作では、それらを位置引数の値として消費してしまう。
            ctx.allow_interspersed_args = self.default_command.allow_interspersed_args
            return self.default_command.parse_args(ctx, args)
        self._invoke_default = False
        return super().parse_args(ctx, args)

    def invoke(self, ctx: click.Context) -> Any:
        if self._invoke_default and self.default_command is not None:
            return self.default_command.invoke(ctx)
        return super().invoke(ctx)

    def _asks_for_catalog(self, ctx: click.Context, args: list[str]) -> bool:
        """このグループ自身への`--help --json`か（先頭に並ぶOptionだけを見る）。"""

        leading: list[str] = []
        for token in args:
            if token == "--" or not token.startswith("-"):
                break
            leading.append(token)
        return JSON_OPTION in leading and bool(
            set(leading) & set(self.get_help_option_names(ctx))
        )

    def _uses_default(self, args: list[str]) -> bool:
        if args and args[0] in self.commands:
            return False
        if args and args[0] in self.get_help_option_names(click.Context(self)):
            return False
        return True


def build_click_group(
    descriptor: GroupDescriptor,
    *,
    debug: bool = False,
    bindings: Mapping[str, str] | None = None,
    structured: bool = False,
    _scopes: Sequence[GroupDescriptor] = (),
) -> click.Group:
    """グループ記述子を再帰的なClickコマンドツリーへ変換する。"""

    active_bindings = {} if bindings is None else bindings
    scopes = (*_scopes, descriptor)
    commands = {
        child.name: _build_route(
            child,
            debug=debug,
            bindings=active_bindings,
            scopes=scopes,
            structured=structured,
        )
        for child in sorted(descriptor.children, key=lambda route: route.name)
    }
    return RouteGroup(
        descriptor,
        commands=commands,
        debug=debug,
        scopes=scopes,
        bindings=active_bindings,
        structured=structured,
    )


def _build_route(
    route: RouteDescriptor,
    *,
    debug: bool,
    bindings: Mapping[str, str],
    scopes: Sequence[GroupDescriptor],
    structured: bool = False,
) -> click.Command:
    if isinstance(route, GroupDescriptor):
        return build_click_group(
            route,
            debug=debug,
            bindings=bindings,
            structured=structured,
            _scopes=scopes,
        )
    return LazyLeafCommand(
        route,
        debug=debug,
        scopes=scopes,
        bindings=bindings,
        structured=structured,
    )

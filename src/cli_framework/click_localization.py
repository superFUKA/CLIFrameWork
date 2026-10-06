"""Clickの解析処理を維持し、フレームワークのCLI表示を日本語にする。"""

from __future__ import annotations

from collections.abc import Sequence
import re
from typing import Any

import click


class JapaneseHelpFormatter(click.HelpFormatter):
    def write_usage(self, prog: str, args: str = "", prefix: str | None = None) -> None:
        super().write_usage(prog, args, prefix=prefix or "使い方: ")

    def write_heading(self, heading: str) -> None:
        super().write_heading({"Options": "オプション", "Commands": "コマンド"}.get(heading, heading))


class JapaneseContext(click.Context):
    formatter_class = JapaneseHelpFormatter


class JapaneseOption(click.Option):
    """既定値のラベルだけを変更し、利用者の説明と値を維持する。"""

    def get_help_record(self, ctx: click.Context) -> tuple[str, str] | None:
        record = super().get_help_record(ctx)
        if record is None:
            return None
        options, description = record
        # show_defaultはこのクラスの生成時に無効化している。
        default = self.get_default(ctx, call=False)
        if self.is_bool_flag:
            default = (self.opts if default else self.secondary_opts)[0].lstrip("-")
        return options, f"{description}  [既定値: {default}]".strip()


def _usage_message(error: click.UsageError) -> str:
    if isinstance(error, click.NoSuchOption):
        message = f"不明なオプションです: {error.option_name}"
        if error.possibilities:
            message += f"（候補: {', '.join(error.possibilities)}）"
        return message
    if isinstance(error, click.BadParameter):
        hint = error.param_hint
        if hint is None and error.param is not None:
            hint = error.param.get_error_hint(error.ctx)
        if isinstance(hint, (tuple, list)):
            hint = " / ".join(hint)
        if isinstance(error, click.MissingParameter):
            return f"必須の引数がありません: {hint or ''}"
        detail = error.message
        for english, japanese in (
            ("integer", "整数"), ("float", "数値"), ("boolean", "真偽値"),
        ):
            match = re.fullmatch(
                r"(.+) is not a valid " + english + r"\.(?: Recognized values: (.*))?",
                detail, re.DOTALL,
            )
            if match:
                detail = f"{match[1]} は有効な{japanese}ではありません"
                if match[2] is not None:
                    detail += f"（指定できる値: {match[2]}）"
                break
        return f"無効な値です ({hint or '引数'}): {detail}"
    for pattern, template in (
        (r"No such command (.+)\.", "不明なコマンドです: {}"),
        (r"Got unexpected extra argument[s]? \((.*)\)", "余分な引数があります: {}"),
        (r"Option (.+) requires an argument\.", "オプション {} には値が必要です"),
    ):
        match = re.fullmatch(pattern, error.message, re.DOTALL)
        if match:
            return template.format(match[1])
    return error.format_message()


def _show_error(error: click.ClickException) -> None:
    if isinstance(error, click.UsageError):
        ctx = error.ctx
        if ctx is not None:
            click.echo(ctx.get_usage(), err=True, color=ctx.color)
            if ctx.command.get_help_option(ctx) is not None:
                click.echo(f"詳しくは '{ctx.command_path} {ctx.help_option_names[0]}' を参照してください。", err=True)
            click.echo(err=True)
        message = _usage_message(error)
    else:
        message = error.format_message()
    click.echo(f"エラー: {message}", err=True)


class JapaneseCommandMixin:
    """グローバルな翻訳状態を変更せず、CLI実行時だけエラーを表示する。"""

    context_class = JapaneseContext

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        try:
            return super().parse_args(ctx, args)
        except click.UsageError as error:
            # Clickの版によって、値不足の例外にはContextが付かない。
            if error.ctx is None:
                error.ctx = ctx
            raise

    def get_help_option(self, ctx: click.Context) -> click.Option | None:
        option = super().get_help_option(ctx)
        if option is not None:
            option.help = "ヘルプを表示して終了します。"
        return option

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        try:
            result = super().main(
                args, prog_name, complete_var, False, windows_expand_args, **extra,
            )
        except click.ClickException as error:
            if not standalone_mode:
                raise
            _show_error(error)
            raise SystemExit(error.exit_code) from error
        except click.Abort:
            if not standalone_mode:
                raise
            click.echo("中断しました。", err=True)
            raise SystemExit(1) from None
        if standalone_mode:
            raise SystemExit(result if isinstance(result, int) else 0)
        return result

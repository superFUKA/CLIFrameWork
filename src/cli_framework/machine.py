"""機械（スクリプト・AI・GUI）からCLIを使うための任意の層。

本体（create_cliと実行）の動作は変えない。使うcommandだけが、通常の引数として`json`を宣言し、
`respond`で結果を返す。コマンド一覧のJSONは`main`が`--help --json`を受けて出力する。
"""

from __future__ import annotations

import ast
import functools
import json as _json
import sys
from collections.abc import Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click

from .description import ParameterInfo, RouteInfo
from .errors import CliFrameworkError, DefinitionError
from .factory import describe_cli
from .model import SourceDescriptor

EFFECTS = ("read", "change", "confirm")
FAILURE_EXIT_CODE = 1
USAGE_EXIT_CODE = 2


class CommandError(Exception):
    """commandが利用者へ報告する失敗。codeは機械向け、messageは人向け。"""

    def __init__(self, code: str, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


@dataclass(slots=True)
class _Response:
    json: bool
    notices: list[str] = field(default_factory=list)


_RESPONSE: ContextVar[_Response | None] = ContextVar(
    "cli_framework_machine_response", default=None
)


def respond(
    action: Callable[[], object],
    *,
    json: bool = False,
    render: Callable[[Any], str | None] | None = None,
) -> int:
    """actionを実行し、結果を出力して終了コードを返す。

    jsonが真なら、標準出力へJSONを1つだけ出力する。偽なら、renderが返した文字列を出力する。
    actionがCommandErrorを送出した場合は失敗として報告し、1を返す。
    """

    response = _Response(json=bool(json))
    token = _RESPONSE.set(response)
    try:
        try:
            result = action()
        except CommandError as error:
            if response.json:
                _print_document(_document(None, response.notices, error))
            else:
                click.echo(f"エラー: {error.message}", err=True)
                if error.hint:
                    click.echo(error.hint, err=True)
            return FAILURE_EXIT_CODE
        if response.json:
            _print_document(_document(result, response.notices, None))
        elif render is not None:
            text = render(result)
            if text:
                click.echo(text)
        return 0
    finally:
        _RESPONSE.reset(token)


def progress(text: str, *, ratio: float | None = None) -> None:
    """経過（今していること）を標準エラーへ出力する。"""

    _emit("progress", text, ratio=ratio)


def warning(text: str) -> None:
    """注意（続けるが確かめてほしいこと）を標準エラーへ出力する。"""

    _emit("warning", text)


def notice(text: str) -> None:
    """知らせ（成功したが伝えておくこと）を出力し、JSONの結果にも含める。"""

    response = _RESPONSE.get()
    if response is not None:
        response.notices.append(text)
    _emit("notice", text, human=f"お知らせ: {text}")


def catalog(cli: click.Command) -> dict[str, Any]:
    """CLIのコマンド一覧を、JSONへ変換できるdictで返す。全commandを読み込む。"""

    return _node(describe_cli(cli))


def main(cli: click.Command, argv: Sequence[str] | None = None) -> None:
    """CLIを実行する。`--help`と`--json`の両方があれば、コマンド一覧のJSONを出力する。"""

    arguments = list(sys.argv[1:] if argv is None else argv)
    head = arguments[: arguments.index("--")] if "--" in arguments else arguments
    if "--help" in head and "--json" in head:
        raise SystemExit(_print_catalog(cli, [item for item in head if not item.startswith("-")]))
    cli.main(args=arguments)


def _emit(kind: str, text: str, *, human: str | None = None, ratio: float | None = None) -> None:
    response = _RESPONSE.get()
    if response is not None and response.json:
        event: dict[str, Any] = {"kind": kind, "text": text}
        if ratio is not None:
            event["ratio"] = ratio
        click.echo(_json.dumps(event, ensure_ascii=False), err=True)
    else:
        click.echo(human if human is not None else text, err=True)


def _command_path() -> str:
    context = click.get_current_context(silent=True)
    names: list[str] = []
    while context is not None and context.parent is not None:
        names.append(context.info_name or "")
        context = context.parent
    return " ".join(reversed(names))


def _document(
    result: object, notices: list[str], error: CommandError | None
) -> dict[str, Any]:
    return {
        "ok": error is None,
        "command": _command_path(),
        "result": None if error is not None else result,
        "notices": list(notices),
        "error": None if error is None else {
            "code": error.code, "message": error.message, "hint": error.hint,
        },
    }


def _print_document(document: dict[str, Any]) -> None:
    click.echo(_json.dumps(document, ensure_ascii=False))


def _print_catalog(cli: click.Command, tokens: list[str]) -> int:
    try:
        route = describe_cli(cli)
        for token in tokens:
            child = next((item for item in route.children if item.name == token), None)
            if child is None:
                break  # 残りはcommandの引数
            route = child
        result = _node(route)
    except CliFrameworkError as error:
        _print_document({
            "ok": False, "command": "help", "result": None, "notices": [],
            "error": {"code": "definition_error", "message": str(error), "hint": None},
        })
        return FAILURE_EXIT_CODE
    _print_document({
        "ok": True, "command": "help", "result": result, "notices": [], "error": None,
    })
    return 0


def _node(route: RouteInfo) -> dict[str, Any]:
    help_text = route.command_help or route.help or ""
    node: dict[str, Any] = {
        "name": route.name,
        "path": " ".join(route.path),
        "summary": help_text.strip().splitlines()[0] if help_text.strip() else "",
        "help": (route.help or route.command_help or "").strip(),
        "runnable": route.runnable,
    }
    if route.runnable:
        parameters = route.parameters()
        node["effect"] = _effect(route)
        node["arguments"] = [
            _argument(parameter) for parameter in parameters if parameter.kind == "argument"
        ]
        node["options"] = [
            _option(parameter) for parameter in parameters if parameter.kind == "option"
        ]
    node["commands"] = [_node(child) for child in route.children]
    return node


def _argument(parameter: ParameterInfo) -> dict[str, Any]:
    return {
        "name": parameter.name.upper(),
        "param": parameter.name,
        "help": parameter.help or "",
        "required": parameter.required,
        "multiple": parameter.variadic,
        "type": parameter.type,
    }


def _option(parameter: ParameterInfo) -> dict[str, Any]:
    return {
        "names": [parameter.option],
        "param": parameter.name,
        "help": parameter.help or "",
        "flag": parameter.type == "bool",
        "required": False,
        "multiple": False,
        "type": parameter.type,
        "negative": parameter.negative,
        "default": parameter.default,
    }


def _effect(route: RouteInfo) -> str:
    assert route.file is not None and route.module is not None
    source = SourceDescriptor(route.module, route.file)
    effect = _effect_constant(route.file)
    if effect is None:
        raise DefinitionError(
            f"commandの重さがありません。モジュールの先頭に EFFECT = {' / '.join(map(repr, EFFECTS))}"
            " のいずれかを書いてください",
            route=route.path,
            source=source,
        )
    if effect not in EFFECTS:
        raise DefinitionError(
            f"EFFECT {effect!r} は使えません。{'、'.join(EFFECTS)}のいずれかです",
            route=route.path,
            source=source,
        )
    return effect


@functools.lru_cache(maxsize=None)
def _effect_constant(path: Path) -> str | None:
    """commandモジュールのトップレベルの`EFFECT = "..."`を、importせずに読む。"""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "EFFECT" for target in statement.targets)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            return statement.value.value
    return None

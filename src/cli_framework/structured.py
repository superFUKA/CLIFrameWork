"""構造化出力（`create_cli(..., structured=True)`）の、Clickに依存しない共通処理。"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence

from .errors import DefinitionError
from .model import CommandDescriptor, GroupDescriptor

EFFECTS = ("read", "change", "confirm")
JSON_OPTION = "--json"


def validate_structured(root: GroupDescriptor) -> None:
    """直接実行できる全commandの、重さ（EFFECT）とrenderの定義を検証する。"""

    for route, command in _commands(root, ()):
        if command.effect_source is None:
            raise DefinitionError(
                "commandの重さがありません。モジュールのトップレベルに"
                f" EFFECT = {' / '.join(repr(effect) for effect in EFFECTS)} のいずれかを書いてください",
                route=route,
                source=command.source,
            )
        if command.effect is None:
            raise DefinitionError(
                "EFFECTは文字列リテラルで書く必要があります",
                route=route,
                source=command.effect_source,
            )
        if command.effect not in EFFECTS:
            raise DefinitionError(
                f"EFFECT {command.effect!r} は使えません。"
                f"{'、'.join(EFFECTS)}のいずれかです",
                route=route,
                source=command.effect_source,
            )
        if command.render is not None and command.render_async:
            raise DefinitionError(
                "非同期render関数には対応していません",
                route=route,
                source=command.render,
            )


def _commands(
    group: GroupDescriptor,
    route: tuple[str, ...],
) -> Iterator[tuple[tuple[str, ...], CommandDescriptor]]:
    if group.command is not None:
        yield route, group.command
    for child in group.children:
        child_route = (*route, child.name)
        if isinstance(child, GroupDescriptor):
            yield from _commands(child, child_route)
        else:
            yield child_route, child


def tokens_before_separator(arguments: Sequence[str]) -> list[str]:
    """`--`より前の引数を返す。`--`より後ろは値であり、Optionとして扱わない。"""

    tokens = list(arguments)
    return tokens[: tokens.index("--")] if "--" in tokens else tokens


def success_document(command: str, result: object) -> dict[str, object]:
    return {"ok": True, "command": command, "result": result, "error": None}


def failure_document(
    command: str,
    code: str,
    message: str,
    hint: str | None = None,
) -> dict[str, object]:
    return {
        "ok": False,
        "command": command,
        "result": None,
        "error": {"code": code, "message": message, "hint": hint},
    }


def encode(document: dict[str, object]) -> str:
    """標準出力へ出す1行のJSONへ変換する。変換できない値はTypeErrorになる。"""

    return json.dumps(document, ensure_ascii=False)


def default_text(result: object) -> str | None:
    """render関数のないcommandの結果を、人向けの文字にする。"""

    if result is None or isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, indent=2)

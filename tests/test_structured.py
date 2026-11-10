from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest
from fixtures.packages import write_package
from fixtures.runner import CliRunner

import cli_framework
from cli_framework import CommandError, DefinitionError, create_cli, describe_cli

LIST = '''"""ファイルを一覧します。"""
from typing import Annotated

EFFECT = "read"


def command(folder: Annotated[str, "フォルダー"]) -> dict:
    return {"folder": folder, "files": ["a.txt", "b.txt"]}


def render(result) -> str:
    return "\\n".join(result["files"])
'''

ADD = '''"""ファイルを作ります。"""
from typing import Annotated

from cli_framework import CommandError, current_context

EFFECT = "change"


def command(
    name: Annotated[str, "ファイル名"],
    *tags: Annotated[str, "印"],
    count: Annotated[int, "作る数"] = 1,
) -> dict:
    if name == "bad":
        raise CommandError("invalid_name", "その名前は使えません", hint="別の名前にしてください")
    if name == "boom":
        raise RuntimeError("壊れました")
    return {"name": name, "tags": list(tags), "count": count, "json": current_context().json}
'''

FILES = {
    "__init__.py": 'def teardown():\n    print("teardown")\n',
    "files/__init__.py": '"""ファイルを扱います。"""\n',
    "files/list.py": LIST,
    "files/add.py": ADD,
    "files/code.py": 'EFFECT = "read"\n\ndef command() -> int:\n    return 3\n',
    "sync/__init__.py": (
        '"""取り込み"""\n\nEFFECT: str = "confirm"\n\n\n'
        'def command(force: bool = False) -> None:\n    """取り込みます。"""\n\n\n'
        'def render(result) -> None:\n    print("done")\n'
    ),
    "sync/abort.py": 'EFFECT = "change"\n\ndef command() -> bool:\n    return True\n',
    "echo.py": 'EFFECT = "read"\n\ndef command(json: str) -> dict:\n    return {"given": json}\n',
}


def _import_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    files: dict[str, str],
) -> ModuleType:
    write_package(monkeypatch, tmp_path, name, files)
    return importlib.import_module(name)


def _cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, files: dict[str, str] = FILES):
    return create_cli(_import_package(monkeypatch, tmp_path, name, files), name="tool", structured=True)


def test_public_api_exports_command_error() -> None:
    assert cli_framework.CommandError is CommandError


def test_command_returns_data_and_json_prints_one_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    cli = _cli(monkeypatch, tmp_path, "structured_json")

    listed = runner.invoke(cli, ["files", "list", "src", "--json"])
    added = runner.invoke(cli, ["files", "add", "c.txt", "x", "y", "--count", "2", "--json"])
    aborted = runner.invoke(cli, ["sync", "abort", "--json"])

    assert (listed.exit_code, listed.stderr) == (0, "")
    before, document = listed.stdout.splitlines()
    assert json.loads(document) == {
        "ok": True, "command": "files list",
        "result": {"folder": "src", "files": ["a.txt", "b.txt"]}, "error": None,
    }
    assert before == "teardown"  # JSONは、teardownまで終わった後の最後の1行
    assert json.loads(added.stdout.splitlines()[-1])["result"] == {
        "name": "c.txt", "tags": ["x", "y"], "count": 2, "json": True,
    }
    assert json.loads(aborted.stdout.splitlines()[-1])["result"] is True


def test_without_json_the_render_function_writes_for_people(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    cli = _cli(monkeypatch, tmp_path, "structured_human")

    listed = runner.invoke(cli, ["files", "list", "src"])
    added = runner.invoke(cli, ["files", "add", "c.txt"])
    synced = runner.invoke(cli, ["sync"])
    helped = runner.invoke(cli, ["files", "list", "--help"])

    assert (listed.exit_code, listed.stdout) == (0, "a.txt\nb.txt\nteardown\n")
    assert (added.exit_code, added.stdout) == (0, "teardown\n")  # renderがなければ何も出さない
    assert (synced.exit_code, synced.stdout) == (0, "done\nteardown\n")
    assert "--json" in helped.stdout and "結果をJSONで出力します。" in helped.stdout
    assert "--no-json" not in helped.stdout


def test_command_error_and_unexpected_errors_in_both_forms(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    cli = _cli(monkeypatch, tmp_path, "structured_errors")

    bad_json = runner.invoke(cli, ["files", "add", "bad", "--json"])
    bad_text = runner.invoke(cli, ["files", "add", "bad"])
    boom_json = runner.invoke(cli, ["files", "add", "boom", "--json"])
    boom_text = runner.invoke(cli, ["files", "add", "boom"])

    assert (bad_json.exit_code, bad_json.stderr) == (1, "")
    assert json.loads(bad_json.stdout.splitlines()[-1]) == {
        "ok": False, "command": "files add", "result": None,
        "error": {"code": "invalid_name", "message": "その名前は使えません", "hint": "別の名前にしてください"},
    }
    assert (bad_text.exit_code, bad_text.stdout) == (1, "teardown\n")
    assert bad_text.stderr == "エラー: その名前は使えません\n別の名前にしてください\n"
    assert (boom_json.exit_code, boom_json.stderr) == (1, "")
    assert json.loads(boom_json.stdout.splitlines()[-1])["error"] == {
        "code": "unexpected", "message": "壊れました", "hint": None,
    }
    assert (boom_text.exit_code, boom_text.stderr) == (1, "エラー: 壊れました\n")


def test_integer_return_is_still_the_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    cli = _cli(monkeypatch, tmp_path, "structured_code")

    as_json = runner.invoke(cli, ["files", "code", "--json"])
    as_text = runner.invoke(cli, ["files", "code"])

    assert as_json.exit_code == 3
    assert json.loads(as_json.stdout.splitlines()[-1]) == {
        "ok": False, "command": "files code", "result": None,
        "error": {"code": "exit_code", "message": "終了コード 3", "hint": None},
    }
    assert (as_text.exit_code, as_text.stdout) == (3, "teardown\n")


def test_usage_errors_are_json_when_json_is_requested(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    cli = _cli(monkeypatch, tmp_path, "structured_usage")

    missing = runner.invoke(cli, ["files", "add", "--json"])
    unknown = runner.invoke(cli, ["files", "nope", "--json"])
    negated = runner.invoke(cli, ["files", "list", "src", "--no-json"])
    as_text = runner.invoke(cli, ["files", "add"])

    assert (missing.exit_code, missing.stderr) == (2, "")
    document = json.loads(missing.stdout)
    assert (document["ok"], document["command"], document["error"]["code"]) == (False, "files add", "usage_error")
    assert "必須の引数" in document["error"]["message"]
    assert (unknown.exit_code, json.loads(unknown.stdout)["command"]) == (2, "files")
    assert (negated.exit_code, negated.stdout) == (2, "")  # 否定形は作らない
    assert (as_text.exit_code, as_text.stdout) == (2, "")
    assert "エラー:" in as_text.stderr and "使い方:" in as_text.stderr


def test_help_json_prints_the_catalog_of_the_addressed_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    cli = _cli(monkeypatch, tmp_path, "structured_catalog")

    whole = json.loads(runner.invoke(cli, ["--help", "--json"]).stdout)
    group = json.loads(runner.invoke(cli, ["files", "--json", "--help"]).stdout)
    leaf = json.loads(runner.invoke(cli, ["files", "add", "--help", "--json"]).stdout)
    runnable_group = json.loads(runner.invoke(cli, ["sync", "--help", "--json"]).stdout)
    as_values = runner.invoke(cli, ["files", "add", "--", "--help", "--json"])

    assert (whole["ok"], whole["command"], whole["error"]) == (True, "help", None)
    root = whole["result"]
    assert (root["name"], root["path"], root["runnable"], root["effect"], root["parameters"]) == ("tool", "", False, None, [])
    assert [node["path"] for node in root["commands"]] == ["echo", "files", "sync"]
    assert (group["command"], group["result"]["path"], group["result"]["help"]) == ("help files", "files", "ファイルを扱います。")
    assert [node["path"] for node in group["result"]["commands"]] == ["files add", "files code", "files list"]
    assert leaf["command"] == "help files add"
    assert leaf["result"] == {
        "name": "add", "path": "files add", "help": "ファイルを作ります。", "command_help": "ファイルを作ります。",
        "runnable": True, "effect": "change",
        "parameters": [
            {"name": "name", "type": "str", "kind": "argument", "required": True, "variadic": False,
             "default": None, "help": "ファイル名", "option": None, "negative": None},
            {"name": "tags", "type": "str", "kind": "argument", "required": False, "variadic": True,
             "default": None, "help": "印", "option": None, "negative": None},
            {"name": "count", "type": "int", "kind": "option", "required": False, "variadic": False,
             "default": 1, "help": "作る数", "option": "--count", "negative": None},
        ],
        "commands": [],
    }
    assert leaf["result"] == next(node for node in group["result"]["commands"] if node["name"] == "add")
    sync = runnable_group["result"]
    assert (sync["runnable"], sync["effect"], sync["help"], sync["command_help"]) == (True, "confirm", "取り込み", "取り込みます。")
    assert [p["option"] for p in sync["parameters"]] == ["--force"]
    assert [node["path"] for node in sync["commands"]] == ["sync abort"]
    # `--`より後ろは値：一覧ではなく、ふつうに実行する
    assert (as_values.exit_code, as_values.stdout) == (0, "teardown\n")


def test_json_is_reserved_only_as_an_option_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    cli = _cli(monkeypatch, tmp_path, "structured_reserved", {
        **FILES,
        "clash.py": 'EFFECT = "read"\n\ndef command(json: bool = False) -> None:\n    pass\n',
    })

    echoed = runner.invoke(cli, ["echo", "hello", "--json"])
    clashed = runner.invoke(cli, ["clash"])
    clashed_json = runner.invoke(cli, ["clash", "--json"])

    assert json.loads(echoed.stdout.splitlines()[-1])["result"] == {"given": "hello"}  # 位置引数のjsonは使える
    assert clashed.exit_code == 1 and "--json" in clashed.stderr and "構造化出力" in clashed.stderr
    assert clashed_json.exit_code == 1  # 定義エラーも、--jsonならJSONで返す
    assert json.loads(clashed_json.stdout)["error"]["code"] == "definition_error"
    with pytest.raises(DefinitionError, match="--json"):
        next(route for route in describe_cli(cli).children if route.name == "clash").parameters()


@pytest.mark.parametrize(("source", "message"), [
    ("def command():\n    pass\n", "重さがありません"),
    ('EFFECT = "maybe"\n\ndef command():\n    pass\n', "maybe"),
    ('KIND = "read"\nEFFECT = KIND\n\ndef command():\n    pass\n', "文字列リテラル"),
    ('EFFECT = "read"\n\ndef command():\n    pass\n\nasync def render(result):\n    pass\n', "非同期render"),
])
def test_static_definition_errors_are_raised_by_create_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    source: str,
    message: str,
) -> None:
    package = _import_package(monkeypatch, tmp_path, "structured_static", {"run.py": source})

    with pytest.raises(DefinitionError, match=message) as error:
        create_cli(package, name="tool", structured=True)

    assert "structured_static.run" in str(error.value)
    create_cli(package, name="tool")  # 構造化出力を使わないCLIは、これらの定義を検証しない


def test_render_must_accept_the_result_and_return_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    cli = _cli(monkeypatch, tmp_path, "structured_render", {
        "noargs.py": 'EFFECT = "read"\n\ndef command() -> None:\n    pass\n\ndef render():\n    return ""\n',
        "number.py": 'EFFECT = "read"\n\ndef command() -> None:\n    pass\n\ndef render(result):\n    return 1\n',
    })

    noargs = runner.invoke(cli, ["noargs"])
    number = runner.invoke(cli, ["number"])
    number_json = runner.invoke(cli, ["number", "--json"])

    assert noargs.exit_code == 1 and "render関数は、結果を1つの位置引数で" in noargs.stderr
    assert number.exit_code == 1 and "renderの戻り値はstrまたはNone" in number.stderr
    assert number_json.exit_code == 0  # --jsonではrenderを呼ばない


def test_results_that_cannot_be_encoded_are_reported_as_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cli = _cli(monkeypatch, tmp_path, "structured_encode", {
        "odd.py": 'EFFECT = "read"\n\ndef command() -> object:\n    return {1, 2}\n',
    })

    result = CliRunner().invoke(cli, ["odd", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "unexpected"


def test_cli_without_structured_output_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    cli = create_cli(_import_package(monkeypatch, tmp_path, "structured_off", FILES), name="tool")

    data = runner.invoke(cli, ["files", "list", "src"])
    option = runner.invoke(cli, ["files", "code", "--json"])
    helped = runner.invoke(cli, ["files", "code", "--help"])
    echoed = runner.invoke(cli, ["echo", "x"])

    assert data.exit_code == 1 and "commandの戻り値はNoneまたはint" in data.stderr
    assert option.exit_code == 2 and "--json" in option.stderr
    assert "--json" not in helped.stdout
    assert echoed.exit_code == 1  # dictの戻り値は、従来どおり誤り
    assert describe_cli(cli).children[0].effect == "read"  # 記述には、書いてあるEFFECTが出る


def test_description_includes_the_effect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = describe_cli(_cli(monkeypatch, tmp_path, "structured_describe"))

    effects = {
        " ".join(route.path): route.effect
        for group in root.children for route in (group, *group.children)
    }

    assert effects == {
        "echo": "read", "files": None, "files add": "change", "files code": "read",
        "files list": "read", "sync": "confirm", "sync abort": "change",
    }

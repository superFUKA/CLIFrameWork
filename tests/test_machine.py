from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest
from fixtures.packages import write_package
from fixtures.runner import CliRunner

import cli_framework
from cli_framework import DefinitionError, create_cli
from cli_framework.machine import CommandError, catalog, main, respond

LIST = '''"""ファイルを一覧します。

フォルダーの中のファイルの名前を出します。
"""
from typing import Annotated

from cli_framework.machine import respond

EFFECT = "read"


def command(
    folder: Annotated[str, "フォルダー"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    return respond(
        lambda: {"folder": folder, "files": ["a.txt", "b.txt"]},
        json=json,
        render=lambda result: "\\n".join(result["files"]),
    )
'''

ADD = '''"""ファイルを作ります。"""
from typing import Annotated

from cli_framework.machine import CommandError, notice, progress, respond, warning

EFFECT = "change"


def command(
    name: Annotated[str, "ファイル名"],
    *tags: Annotated[str, "印"],
    count: Annotated[int, "作る数"] = 1,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    def action():
        if name == "bad":
            raise CommandError("invalid_name", "その名前は使えません", hint="別の名前にしてください")
        progress("作っています", ratio=0.5)
        warning("上書きしました")
        notice("1つ作りました")
        return None

    return respond(action, json=json, render=lambda result: f"{name} を作りました")
'''

FILES = {
    "files/__init__.py": '"""ファイルを扱います。"""\n',
    "files/list.py": LIST,
    "files/add.py": ADD,
}


def _import_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    files: dict[str, str],
) -> ModuleType:
    write_package(monkeypatch, tmp_path, name, files)
    return importlib.import_module(name)


def test_machine_layer_is_optional() -> None:
    assert not hasattr(cli_framework, "respond")
    assert "machine" not in cli_framework.__all__


def test_json_output_is_one_document_on_stdout_and_events_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cli = create_cli(_import_package(monkeypatch, tmp_path, "machine_json", FILES), name="tool")
    runner = CliRunner()

    listed = runner.invoke(cli, ["files", "list", "src", "--json"])
    added = runner.invoke(cli, ["files", "add", "c.txt", "--json"])

    assert listed.exit_code == 0 and listed.stderr == ""
    assert json.loads(listed.stdout) == {
        "ok": True, "command": "files list",
        "result": {"folder": "src", "files": ["a.txt", "b.txt"]},
        "notices": [], "error": None,
    }
    assert added.exit_code == 0
    assert json.loads(added.stdout) == {
        "ok": True, "command": "files add", "result": None,
        "notices": ["1つ作りました"], "error": None,
    }
    assert [json.loads(line) for line in added.stderr.splitlines()] == [
        {"kind": "progress", "text": "作っています", "ratio": 0.5},
        {"kind": "warning", "text": "上書きしました"},
        {"kind": "notice", "text": "1つ作りました"},
    ]


def test_human_output_uses_render_and_plain_messages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cli = create_cli(_import_package(monkeypatch, tmp_path, "machine_human", FILES), name="tool")
    runner = CliRunner()

    listed = runner.invoke(cli, ["files", "list", "src"])
    added = runner.invoke(cli, ["files", "add", "c.txt"])

    assert (listed.exit_code, listed.stdout, listed.stderr) == (0, "a.txt\nb.txt\n", "")
    assert (added.exit_code, added.stdout) == (0, "c.txt を作りました\n")
    assert added.stderr == "作っています\n上書きしました\nお知らせ: 1つ作りました\n"


def test_command_error_is_reported_in_both_forms(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cli = create_cli(_import_package(monkeypatch, tmp_path, "machine_error", FILES), name="tool")
    runner = CliRunner()

    as_json = runner.invoke(cli, ["files", "add", "bad", "--json"])
    as_text = runner.invoke(cli, ["files", "add", "bad"])

    assert as_json.exit_code == 1 and as_json.stderr == ""
    assert json.loads(as_json.stdout) == {
        "ok": False, "command": "files add", "result": None, "notices": [],
        "error": {"code": "invalid_name", "message": "その名前は使えません", "hint": "別の名前にしてください"},
    }
    assert (as_text.exit_code, as_text.stdout) == (1, "")
    assert as_text.stderr == "エラー: その名前は使えません\n別の名前にしてください\n"


def test_respond_works_outside_a_cli_run(capsys: pytest.CaptureFixture[str]) -> None:
    def fail() -> None:
        raise CommandError("nope", "できません")

    assert respond(lambda: [1, 2], json=True) == 0
    assert respond(fail, json=True) == 1
    first, second = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert (first["ok"], first["command"], first["result"]) == (True, "", [1, 2])
    assert second["error"] == {"code": "nope", "message": "できません", "hint": None}


def test_catalog_describes_commands_arguments_options_and_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cli = create_cli(_import_package(monkeypatch, tmp_path, "machine_catalog", FILES), name="tool")

    root = catalog(cli)

    assert (root["name"], root["path"], root["runnable"]) == ("tool", "", False)
    (files,) = root["commands"]
    assert (files["path"], files["summary"], files["runnable"]) == ("files", "ファイルを扱います。", False)
    assert "effect" not in files
    add, listed = files["commands"]
    assert (listed["path"], listed["effect"], listed["summary"]) == ("files list", "read", "ファイルを一覧します。")
    assert "フォルダーの中のファイルの名前を出します。" in listed["help"]
    assert listed["arguments"] == [{
        "name": "FOLDER", "param": "folder", "help": "フォルダー",
        "required": True, "multiple": False, "type": "str",
    }]
    assert listed["options"] == [{
        "names": ["--json"], "param": "json", "help": "結果をJSONで出力する", "flag": True,
        "required": False, "multiple": False, "type": "bool", "negative": "--no-json", "default": False,
    }]
    assert (add["effect"], [a["param"] for a in add["arguments"]]) == ("change", ["name", "tags"])
    assert add["arguments"][1]["multiple"] is True and add["arguments"][1]["required"] is False
    assert add["options"][0] == {
        "names": ["--count"], "param": "count", "help": "作る数", "flag": False,
        "required": False, "multiple": False, "type": "int", "negative": None, "default": 1,
    }
    json.dumps(root)  # JSONへ変換できる


def test_main_prints_the_catalog_for_help_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = create_cli(_import_package(monkeypatch, tmp_path, "machine_main", FILES), name="tool")

    with pytest.raises(SystemExit) as whole:
        main(cli, ["--help", "--json"])
    everything = json.loads(capsys.readouterr().out)
    with pytest.raises(SystemExit) as one:
        main(cli, ["files", "add", "c.txt", "--json", "--help"])
    single = json.loads(capsys.readouterr().out)
    with pytest.raises(SystemExit) as ordinary:
        main(cli, ["files", "list", "src"])
    listed = capsys.readouterr().out
    with pytest.raises(SystemExit) as after_separator:
        main(cli, ["files", "add", "--json", "--", "--help"])
    literal = json.loads(capsys.readouterr().out)

    assert (whole.value.code, one.value.code, ordinary.value.code) == (0, 0, 0)
    assert everything["ok"] is True and everything["command"] == "help"
    assert [node["path"] for node in everything["result"]["commands"]] == ["files"]
    assert (single["result"]["path"], single["result"]["effect"]) == ("files add", "change")
    assert listed == "a.txt\nb.txt\n"
    assert after_separator.value.code == 0 and literal["command"] == "files add"  # `--`の後は値


def test_commands_without_a_valid_effect_are_definition_errors_in_the_catalog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = create_cli(_import_package(monkeypatch, tmp_path, "machine_missing", {
        "plain.py": "def command():\n    print('ok')\n",
    }), name="tool")
    invalid = create_cli(_import_package(monkeypatch, tmp_path, "machine_invalid", {
        "odd.py": 'EFFECT = "maybe"\n\ndef command():\n    pass\n',
    }), name="tool")

    with pytest.raises(DefinitionError, match="重さがありません") as error:
        catalog(missing)
    with pytest.raises(DefinitionError, match="maybe"):
        catalog(invalid)
    with pytest.raises(SystemExit) as stopped:
        main(missing, ["--help", "--json"])
    document = json.loads(capsys.readouterr().out)
    ran = CliRunner().invoke(missing, ["plain"])

    assert "machine_missing.plain" in str(error.value)
    assert stopped.value.code == 1
    assert (document["ok"], document["error"]["code"]) == (False, "definition_error")
    assert (ran.exit_code, ran.stdout) == (0, "ok\n")  # 一覧を使わない限り、通常の実行は変わらない

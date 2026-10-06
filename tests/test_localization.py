from __future__ import annotations

import importlib

import click
import pytest
from fixtures.packages import write_package
from fixtures.runner import CliRunner

from cli_framework import create_cli


@pytest.fixture
def cli(monkeypatch, tmp_path):
    package = write_package(monkeypatch, tmp_path, "japanese_commands", {
        "__init__.py": '"""日本語ツール。"""\n',
        "run.py": (
            "from typing import Annotated\n"
            "def command(入力: Annotated[str, '入力元のパス'], "
            "jobs: Annotated[int, 'Options / default: を含む説明'] = 1, "
            "ratio: float = 0.5, clean: bool = False):\n"
            "    print(入力)\n"
        ),
        "flag.py": "def command(value: bool): print(value)\n",
        "project/__init__.py": '"""プロジェクト。"""\ndef command():\n    """概要を表示。"""\n',
        "project/status.py": "def command(): pass\n",
        "fail.py": "def command(): raise ValueError('Error: 元のメッセージ')\n",
        "abort.py": "def command(): raise KeyboardInterrupt\n",
    })
    return create_cli(importlib.import_module(package.name), name="道具")


def test_help_is_japanese_and_preserves_user_text(cli):
    runner = CliRunner()
    for args, expected in (
        (["--help"], ["使い方:", "コマンド:", "オプション:", "コマンド [引数]..."]),
        (["run", "--help"], ["引数:", "入力元のパス", "--jobs 整数", "--ratio 数値",
                             "既定値: 1", "既定値: no-clean", "Options / default: を含む説明"]),
        (["project", "--help"], ["直接実行の使い方:", "既定のコマンド:", "概要を表示。"]),
    ):
        result = runner.invoke(cli, args)
        assert result.exit_code == 0, result.output
        assert result.stderr == ""
        assert "ヘルプを表示して終了します。" in result.stdout
        for fragment in expected:
            assert fragment in result.stdout


@pytest.mark.parametrize("args, fragments", [
    ([], ["コマンドを指定"]),
    (["存在しない"], ["不明なコマンド", "存在しない"]),
    (["run"], ["必須の引数", "入力"]),
    (["run", "資料", "余分"], ["余分な引数", "余分"]),
    (["run", "資料", "--jobs"], ["--jobs", "値が必要"]),
    (["run", "資料", "--job", "2"], ["不明なオプション", "--job", "候補: --jobs"]),
    (["run", "資料", "--jobs", "整数でない"], ["無効な値", "--jobs", "有効な整数ではありません"]),
    (["run", "資料", "--ratio", "数値でない"], ["--ratio", "有効な数値ではありません"]),
    (["flag", "真偽値でない"], ["VALUE", "有効な真偽値ではありません"]),
])
def test_usage_errors_are_japanese(cli, args, fragments):
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "使い方:" in result.stderr
    assert "エラー:" in result.stderr
    assert "--help' を参照してください。" in result.stderr
    for fragment in fragments:
        assert fragment in result.stderr


def test_japanese_path_and_original_exception_are_preserved(cli):
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "資料/日本語のフォルダー"])
    assert result.exit_code == 0
    assert result.stdout == "資料/日本語のフォルダー\n"
    assert result.stderr == ""
    result = runner.invoke(cli, ["fail"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "エラー: Error: 元のメッセージ\n"


def test_standalone_false_preserves_click_exception(cli):
    with pytest.raises(click.BadParameter) as caught:
        cli.main(["run", "資料", "--jobs", "不正"], standalone_mode=False)
    assert caught.value.param.name == "jobs"
    assert cli.main(["project"], standalone_mode=False) is None


def test_abort_is_japanese(cli):
    result = CliRunner().invoke(cli, ["abort"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "中断しました。"


def test_other_click_commands_are_unaffected(cli):
    runner = CliRunner()
    plain = click.Command("plain")
    before = runner.invoke(plain, ["--help"])
    runner.invoke(cli, ["run", "--help"])
    runner.invoke(cli, ["存在しない"])
    after = runner.invoke(plain, ["--help"])
    assert before.exit_code == after.exit_code == 0
    assert before.stdout == after.stdout
    assert before.stderr == after.stderr == ""

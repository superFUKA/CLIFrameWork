from __future__ import annotations

import importlib
from pathlib import Path
import sys

import click
from click.shell_completion import BashComplete, CompletionItem
import pytest
from fixtures.packages import write_package
from fixtures.runner import CliRunner

from cli_framework import create_cli


def _cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    files: dict[str, str],
    *,
    debug: bool = False,
) -> click.Command:
    package = write_package(monkeypatch, tmp_path, "variadic_commands", files)
    return create_cli(importlib.import_module(package.name), name="tool", debug=debug)


@pytest.mark.parametrize(
    ("signature", "expression", "args", "expected"),
    [
        ("*targets: str", "targets", [], "()"),
        ("*targets: str", "targets", ["a"], "('a',)"),
        ("*targets: str", "targets", ["a", "b"], "('a', 'b')"),
        ("*targets: int", "targets", ["1", "2"], "(1, 2)"),
        ("*targets: float", "targets", ["1.5", "2"], "(1.5, 2.0)"),
        ("*targets: bool", "targets", ["true", "false"], "(True, False)"),
        ("first: str, *targets: str", "(first, targets)", ["a"], "('a', ())"),
        ("first: str, *targets: str", "(first, targets)",
         ["a", "b", "c"], "('a', ('b', 'c'))"),
        ("jobs: int = 1, *targets: str", "(jobs, targets)",
         ["a", "b"], "(1, ('a', 'b'))"),
        ("first: str, jobs: int = 1, *targets: str", "(first, jobs, targets)",
         ["a", "b", "--jobs", "3", "c"], "('a', 3, ('b', 'c'))"),
        ("*targets: str, jobs: int = 1, clean: bool = False",
         "(targets, jobs, clean)", ["a", "--jobs", "3", "b", "--clean"],
         "(('a', 'b'), 3, True)"),
        ("*targets: str, output: str", "(targets, output)",
         ["dest"], "((), 'dest')"),
        ("*targets: str, output: str, count: int", "(targets, output, count)",
         ["a", "b", "dest", "2"], "(('a', 'b'), 'dest', 2)"),
        ("*targets: str", "targets", ["--", "--help", "-x"], "('--help', '-x')"),
        ("*targets: int", "targets", ["--", "-1", "-2"], "(-1, -2)"),
        ("*Target_Names: str", "Target_Names", ["a", "b"], "('a', 'b')"),
        ("*no_clean: str, clean: bool = False", "(no_clean, clean)",
         ["a", "--clean"], "(('a',), True)"),
    ],
)
def test_variadic_arguments_bind_to_the_python_signature(
    monkeypatch, tmp_path, signature, expression, args, expected,
) -> None:
    cli = _cli(monkeypatch, tmp_path, {
        "run.py": f"def command({signature}): print(repr({expression}))\n",
    })
    result = CliRunner().invoke(cli, ["run", *args])
    assert result.exit_code == 0, result.output
    assert result.stdout == expected + "\n"
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("signature", "args", "fragment"),
    [
        ("*targets: int", ["1", "bad"], "Invalid value"),
        ("*targets: str", ["--unknown"], "No such option"),
        ("first: str, *targets: str", [], "Missing argument"),
        ("*targets: str, output: str", [], "Missing argument"),
    ],
)
def test_variadic_usage_errors_do_not_run_lifecycle(
    monkeypatch, tmp_path, signature, args, fragment,
) -> None:
    cli = _cli(monkeypatch, tmp_path, {
        "__init__.py": "def setup(): print('SETUP')\n"
        "def teardown(): print('TEARDOWN')\n",
        "run.py": f"def command({signature}): print('COMMAND')\n",
    })
    result = CliRunner().invoke(cli, ["run", *args])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert fragment in result.stderr


@pytest.mark.parametrize("group_default", [False, True])
def test_variadic_help_preserves_lazy_loading_and_skips_lifecycle(
    monkeypatch, tmp_path, group_default,
) -> None:
    command = "from typing import Annotated\n"
    command += "def command(*targets: Annotated[str, 'Target description'], jobs: int = 1):\n"
    command += "    print('COMMAND')\n"
    root = "def setup(): print('SETUP')\ndef teardown(): print('TEARDOWN')\n"
    cli = _cli(monkeypatch, tmp_path, {
        "__init__.py": root + (command if group_default else ""),
        "run.py": command,
    })
    assert "variadic_commands.run" not in sys.modules
    root_help = CliRunner().invoke(cli, ["--help"])
    assert root_help.exit_code == 0
    assert root_help.stderr == ""
    assert "variadic_commands.run" not in sys.modules
    result = root_help if group_default else CliRunner().invoke(cli, ["run", "--help"])
    assert result.exit_code == 0
    assert "[TARGETS]..." in result.stdout
    assert "Target description" in result.stdout
    assert "--jobs INTEGER" in result.stdout
    assert result.stderr == ""
    assert not {"SETUP", "COMMAND", "TEARDOWN"}.intersection(result.stdout.splitlines())


@pytest.mark.parametrize("group_default", [False, True])
def test_variadic_help_name_does_not_collide_with_standard_help(
    monkeypatch, tmp_path, group_default,
) -> None:
    source = "def command(_help: str, *help: str, __help: str = 'default'):\n"
    source += "    print(repr((_help, help, __help)))\n"
    cli = _cli(monkeypatch, tmp_path, {
        "__init__.py": source if group_default else "",
        "run.py": source,
    })
    prefix = [] if group_default else ["run"]
    runner = CliRunner()
    result = runner.invoke(cli, [*prefix, "first", "a", "b"])
    assert result.exit_code == 0, result.output
    assert result.stdout == "('first', ('a', 'b'), 'default')\n"
    assert result.stderr == ""
    for args in ([*prefix, "--help"], [*prefix, "first", "a", "--help"]):
        help_result = runner.invoke(cli, args)
        assert help_result.exit_code == 0, help_result.output
        assert "[HELP]..." in help_result.stdout
        assert "--help" in help_result.stdout
        assert "('first'" not in help_result.stdout
        assert help_result.stderr == ""


@pytest.mark.parametrize(
    ("args", "exit_code", "expected"),
    [
        ([], 0, "default:()\n"),
        (["a", "b"], 0, "default:('a', 'b')\n"),
        (["build", "a"], 0, "child:('a', ())\n"),
        (["build"], 2, ""),
        (["--", "build", "a"], 0, "default:('build', 'a')\n"),
        (["a", "build"], 0, "default:('a', 'build')\n"),
    ],
)
def test_variadic_group_keeps_child_precedence(monkeypatch, tmp_path, args, exit_code, expected):
    cli = _cli(monkeypatch, tmp_path, {
        "project/__init__.py": "def command(*targets: str): print('default:' + repr(targets))\n",
        "project/build.py": "def command(first: str, *targets: str):\n"
        "    print('child:' + repr((first, targets)))\n",
    })
    result = CliRunner().invoke(cli, ["project", *args])
    assert result.exit_code == exit_code, result.output
    assert result.stdout == expected
    if exit_code:
        assert "Missing argument" in result.stderr
    else:
        assert result.stderr == ""


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["a", "--jobs", "3", "b"], "(('a', 'b'), 3)\n"),
        (["--jobs", "3", "a", "b"], "(('a', 'b'), 3)\n"),
        (["a", "--", "--jobs", "3"], "(('a', '--jobs', '3'), 1)\n"),
    ],
)
def test_variadic_group_parses_options_among_values(monkeypatch, tmp_path, args, expected):
    cli = _cli(monkeypatch, tmp_path, {
        "__init__.py": "def command(*targets: str, jobs: int = 1):\n"
        "    print(repr((targets, jobs)))\n",
    })
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert result.stdout == expected
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("return_value", "exit_code", "exception"),
    [("None", 0, "None"), ("7", 7, "None"), ("True", 1, "TypeError")],
)
def test_variadic_returns_keep_lifecycle_and_exit_behavior(
    monkeypatch, tmp_path, return_value, exit_code, exception,
) -> None:
    cli = _cli(monkeypatch, tmp_path, {
        "__init__.py": "from cli_framework import current_context\n"
        "def setup(): print('setup')\n"
        "def teardown():\n"
        "    error = current_context().exception\n"
        "    print(type(error).__name__ if error else 'None')\n",
        "run.py": "def command(*targets: str):\n"
        "    print(repr(targets))\n"
        f"    return {return_value}\n",
    })
    result = CliRunner().invoke(cli, ["run", "a", "b"])
    assert result.exit_code == exit_code
    assert result.stdout == f"setup\n('a', 'b')\n{exception}\n"
    if exception == "None":
        assert result.stderr == ""
    else:
        assert "戻り値はNoneまたはint" in result.stderr


@pytest.mark.parametrize("debug", [False, True])
def test_variadic_failure_keeps_original_exception_when_teardown_fails(
    monkeypatch, tmp_path, debug,
) -> None:
    cli = _cli(monkeypatch, tmp_path, {
        "__init__.py": "from cli_framework import current_context\n"
        "def setup(): print('setup')\n"
        "def teardown():\n"
        "    print(str(current_context().exception))\n"
        "    raise OSError('cleanup failed')\n",
        "run.py": "def command(*targets: str):\n"
        "    print(repr(targets))\n"
        "    raise RuntimeError('command failed')\n",
    }, debug=debug)
    result = CliRunner().invoke(cli, ["run", "a", "b"])
    assert result.exit_code == 1
    assert result.stdout == "setup\n('a', 'b')\ncommand failed\n"
    if debug:
        assert "Traceback" in result.stderr
        assert "RuntimeError: command failed" in result.stderr
    else:
        assert result.stderr == "Error: command failed\n"


def test_variadic_completion_still_targets_argument_after_multiple_values(
    monkeypatch, tmp_path,
) -> None:
    cli = _cli(monkeypatch, tmp_path, {
        "__init__.py": "def setup(): raise AssertionError('setup ran')\n"
        "def teardown(): raise AssertionError('teardown ran')\n",
        "run.py": "def command(*targets: str, jobs: int = 1):\n"
        "    raise AssertionError('command ran')\n",
    })
    seen = []

    def complete(argument, ctx, incomplete):
        seen.append((argument.name, ctx.params[argument.name], incomplete))
        return [CompletionItem("candidate")]

    monkeypatch.setattr(click.Argument, "shell_complete", complete)
    completion = BashComplete(cli, {}, "tool", "_TOOL_COMPLETE")
    assert [item.value for item in completion.get_completions(["run", "a", "b"], "c")] == [
        "candidate",
    ]
    assert seen == [("targets", ("a", "b"), "c")]
    assert [item.value for item in completion.get_completions(["run", "a"], "--j")] == [
        "--jobs",
    ]


def test_variadic_group_completion_does_not_run_lifecycle(monkeypatch, tmp_path) -> None:
    cli = _cli(monkeypatch, tmp_path, {
        "__init__.py": "def setup(): raise AssertionError('setup ran')\n"
        "def teardown(): raise AssertionError('teardown ran')\n"
        "def command(*targets: str): raise AssertionError('command ran')\n",
    })
    completion = BashComplete(cli, {}, "tool", "_TOOL_COMPLETE")
    assert completion.get_completions(["a", "b"], "c") == []

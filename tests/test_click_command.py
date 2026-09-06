from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.packages import write_package
from fixtures.runner import CliRunner

from cli_framework.click_command import build_click_command
from cli_framework.model import CommandDescriptor, SourceDescriptor


def _build(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    package_name: str,
    source_text: str,
    *,
    help_text: str | None = None,
    debug: bool = False,
):
    package_path = write_package(monkeypatch, tmp_path, package_name, {"build.py": source_text})
    module_path = package_path / "build.py"
    descriptor = CommandDescriptor(
        "build",
        SourceDescriptor(f"{package_name}.build", module_path, line=1),
        help_text=help_text,
    )
    return build_click_command(descriptor, debug=debug)


def test_argument_is_required_typed_and_passed_by_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    command = _build(
        monkeypatch, tmp_path, "argument_commands",
        "def command(*, count: int):\n"
        "    print(f'{count}:{type(count).__name__}')\n",
    )
    missing = CliRunner().invoke(command, [])
    result = CliRunner().invoke(command, ["4"])
    assert missing.exit_code == 2
    assert "Missing argument" in missing.stderr
    assert missing.stdout == ""
    assert result.exit_code == 0
    assert result.output == "4:int\n"


def test_python_parameter_names_preserve_case_and_underscores(monkeypatch, tmp_path):
    command = _build(
        monkeypatch, tmp_path, "case_sensitive_parameters",
        "def command(Source: str, source: str, User_Name: str = 'guest', Clean_All: bool = False):\n"
        "    print(Source, source, User_Name, Clean_All)\n",
    )
    for flags, expected in [([], "A b guest False\n"),
                            (["--User-Name", "alice", "--Clean-All"], "A b alice True\n"),
                            (["--no-Clean-All"], "A b guest False\n")]:
        result = CliRunner().invoke(command, ["A", "b", *flags])
        assert result.exit_code == 0
        assert result.stdout == expected
        assert result.stderr == ""


def test_option_is_hyphenated_typed_and_uses_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    command = _build(
        monkeypatch, tmp_path, "option_commands",
        "def command(output_path: str = 'dist', jobs_count: int = 2):\n"
        "    print(f'{output_path}:{jobs_count}')\n",
    )
    runner = CliRunner()
    default_result = runner.invoke(command, [])
    explicit_result = runner.invoke(
        command, ["--output-path", "target", "--jobs-count", "5"]
    )
    assert default_result.exit_code == 0
    assert default_result.output == "dist:2\n"
    assert explicit_result.exit_code == 0
    assert explicit_result.output == "target:5\n"


@pytest.mark.parametrize(
    ("default", "flag", "expected"),
    [
        (False, "--clean", "True"),
        (False, "--no-clean", "False"),
        (True, "--clean", "True"),
        (True, "--no-clean", "False"),
    ],
)
def test_bool_option_has_positive_and_negative_flags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    default: bool,
    flag: str,
    expected: str,
) -> None:
    package_name = f"bool_{str(default).lower()}_{flag[2:].replace('-', '_')}"
    command = _build(
        monkeypatch, tmp_path, package_name,
        f"def command(clean: bool = {default!r}):\n"
        "    print(clean)\n",
    )
    result = CliRunner().invoke(command, [flag])
    assert result.exit_code == 0
    assert result.output == f"{expected}\n"


def test_bool_option_preserves_true_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    command = _build(
        monkeypatch, tmp_path, "bool_default_commands",
        "def command(clean: bool = True):\n"
        "    print(clean)\n",
    )
    result = CliRunner().invoke(command, [])
    assert result.exit_code == 0
    assert result.output == "True\n"


def test_help_uses_docstring_and_parameter_descriptions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    command = _build(
        monkeypatch, tmp_path, "help_commands",
        "from typing import Annotated\n"
        "def command(\n"
        "    source: Annotated[str, '入力元'],\n"
        "    jobs: Annotated[int, '並列数'] = 1,\n"
        "    clean: Annotated[bool, '先に削除する'] = False,\n"
        "): pass\n",
        help_text="プロジェクトをビルドします。",
    )
    result = CliRunner().invoke(command, ["--help"])
    assert result.exit_code == 0
    assert "プロジェクトをビルドします。" in result.output
    assert "SOURCE" in result.output
    assert "入力元" in result.output
    assert "--jobs INTEGER" in result.output
    assert "並列数" in result.output
    assert "--clean / --no-clean" in result.output
    assert "先に削除する" in result.output


def test_help_allows_omitted_descriptions_without_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    command = _build(
        monkeypatch, tmp_path, "plain_help_commands",
        "def command(source: str, jobs: int = 1): pass\n",
    )
    result = CliRunner().invoke(command, ["--help"])
    assert result.exit_code == 0
    assert "warning" not in result.output.lower()
    assert "--jobs INTEGER" in result.output


@pytest.mark.parametrize(("return_value", "exit_code"), [("None", 0), ("0", 0), ("7", 7)])
def test_exit_code_is_derived_from_none_or_integer_return(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    return_value: str,
    exit_code: int,
) -> None:
    command = _build(
        monkeypatch, tmp_path, f"exit_{return_value.lower()}_commands",
        f"def command(): return {return_value}\n",
    )
    result = CliRunner().invoke(command, [])
    assert result.exit_code == exit_code
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize(("expression", "type_name"), [("'bad'", "str"), ("True", "bool")])
def test_exit_rejects_other_return_types_as_application_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    expression: str,
    type_name: str,
) -> None:
    command = _build(
        monkeypatch, tmp_path, f"exit_invalid_{type_name}_commands",
        f"def command(): return {expression}\n",
    )
    result = CliRunner().invoke(command, [])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "戻り値はNoneまたはint" in result.stderr
    assert type_name in result.stderr
    assert "Traceback" not in result.stderr


def test_exception_is_concise_and_written_only_to_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    command = _build(
        monkeypatch, tmp_path, "exception_commands",
        "def command():\n"
        "    print('before')\n"
        "    raise RuntimeError('壊れました')\n",
    )
    result = CliRunner().invoke(command, [])
    assert result.exit_code == 1
    assert result.stdout == "before\n"
    assert result.stderr == "Error: 壊れました\n"
    assert "Traceback" not in result.stderr


def test_debug_exception_writes_full_traceback_to_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    command = _build(
        monkeypatch, tmp_path, "debug_commands",
        "def command():\n"
        "    raise RuntimeError('debug failure')\n",
        debug=True,
    )
    result = CliRunner().invoke(command, [])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Traceback (most recent call last)" in result.stderr
    assert "RuntimeError: debug failure" in result.stderr
    assert "debug_commands" in result.stderr

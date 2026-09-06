from __future__ import annotations

from pathlib import Path

from cli_framework.errors import CliFrameworkError, DefinitionError
from cli_framework.model import SourceDescriptor


def test_definition_error_is_a_framework_error() -> None:
    error = DefinitionError("定義が不正です")

    assert isinstance(error, CliFrameworkError)
    assert str(error) == "定義が不正です"


def test_definition_error_reports_route_and_source() -> None:
    source = SourceDescriptor(
        module_name="my_tool.commands.project.build",
        path=Path("my_tool/commands/project/build.py"),
        line=8,
        column=2,
    )
    error = DefinitionError(
        "command関数が見つかりません",
        route=("project", "build"),
        source=source,
    )

    assert error.message == "command関数が見つかりません"
    assert error.route == ("project", "build")
    assert error.source is source
    assert str(error) == (
        "command関数が見つかりません "
        "[ルート: project build ; ソース: my_tool.commands.project.build "
        "(my_tool/commands/project/build.py:8:2)]"
    )


def test_definition_error_accepts_a_one_shot_route_iterable() -> None:
    error = DefinitionError("失敗", route=(part for part in ("project", "build")))

    assert error.route == ("project", "build")

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pytest

from cli_framework.errors import DefinitionError
from cli_framework.model import SourceDescriptor
from cli_framework.parameters import ParameterDescriptor, inspect_parameters


SOURCE = SourceDescriptor(
    "sample.commands.build",
    Path("sample/commands/build.py"),
    line=3,
)


def test_signature_supports_the_four_concrete_types() -> None:
    def command(text: str, count: int, ratio: float, enabled: bool) -> None:
        pass

    parameters = inspect_parameters(command, SOURCE, route=("build",))

    assert parameters == (
        ParameterDescriptor("text", str, True),
        ParameterDescriptor("count", int, True),
        ParameterDescriptor("ratio", float, True),
        ParameterDescriptor("enabled", bool, True),
    )


def test_signature_preserves_defaults_and_parameter_order() -> None:
    def command(
        target: str,
        count: int = 3,
        ratio: float = 0.5,
        enabled: bool = False,
    ) -> None:
        pass

    parameters = inspect_parameters(command, SOURCE)

    assert [parameter.name for parameter in parameters] == [
        "target",
        "count",
        "ratio",
        "enabled",
    ]
    assert parameters[0].required is True
    assert [(item.required, item.default) for item in parameters[1:]] == [
        (False, 3),
        (False, 0.5),
        (False, False),
    ]


def test_annotated_string_becomes_parameter_help() -> None:
    def command(
        target: Annotated[str, "対象名"],
        count: Annotated[int, "回数"] = 2,
    ) -> None:
        pass

    parameters = inspect_parameters(command, SOURCE)

    assert parameters[0].parameter_type is str
    assert parameters[0].help_text == "対象名"
    assert parameters[1].parameter_type is int
    assert parameters[1].help_text == "回数"


def test_signature_accepts_required_keyword_only_parameter() -> None:
    def command(*, target: str) -> None:
        pass

    assert inspect_parameters(command, SOURCE) == (
        ParameterDescriptor("target", str, True),
    )


def test_invalid_missing_annotation_reports_parameter_and_source() -> None:
    def command(target) -> None:  # type: ignore[no-untyped-def]
        pass

    with pytest.raises(DefinitionError, match="target") as captured:
        inspect_parameters(command, SOURCE, route=("build",))

    assert captured.value.route == ("build",)
    assert captured.value.source == SOURCE
    assert "型注釈" in str(captured.value)


@pytest.mark.parametrize(
    "annotation",
    [bytes, Path, list[str], str | None],
)
def test_invalid_unsupported_parameter_type(annotation: object) -> None:
    def command(target: str) -> None:
        pass

    command.__annotations__["target"] = annotation

    with pytest.raises(DefinitionError, match="対応型"):
        inspect_parameters(command, SOURCE)


@pytest.mark.parametrize(
    "default",
    [1, False, None],
)
def test_invalid_default_must_exactly_match_annotation(default: object) -> None:
    def command(target: int = 1) -> None:
        pass

    command.__defaults__ = (default,)

    if type(default) is int:
        assert inspect_parameters(command, SOURCE)[0].default == 1
    else:
        with pytest.raises(DefinitionError, match="既定値"):
            inspect_parameters(command, SOURCE)


def test_invalid_variadic_positional_parameter() -> None:
    def command(*targets: str) -> None:
        pass

    with pytest.raises(DefinitionError, match="可変長"):
        inspect_parameters(command, SOURCE)


def test_invalid_variadic_keyword_parameter() -> None:
    def command(**options: str) -> None:
        pass

    with pytest.raises(DefinitionError, match="可変長"):
        inspect_parameters(command, SOURCE)


def test_invalid_positional_only_parameter() -> None:
    def command(target: str, /) -> None:
        pass

    with pytest.raises(DefinitionError, match="位置専用"):
        inspect_parameters(command, SOURCE)


def test_invalid_non_string_annotated_metadata() -> None:
    def command(target: Annotated[str, 123]) -> None:
        pass

    with pytest.raises(DefinitionError, match="メタデータ"):
        inspect_parameters(command, SOURCE)


def test_invalid_multiple_annotated_descriptions() -> None:
    def command(target: Annotated[str, "対象", "追加"]) -> None:
        pass

    with pytest.raises(DefinitionError, match="1つ"):
        inspect_parameters(command, SOURCE)


def test_invalid_unresolved_forward_reference() -> None:
    def command(target: MissingType) -> None:  # type: ignore[name-defined]  # noqa: F821
        pass

    with pytest.raises(DefinitionError, match="解決できません"):
        inspect_parameters(command, SOURCE)


@pytest.mark.parametrize("keyword_only", [False, True])
def test_none_default_preserves_annotation_and_function(keyword_only: bool) -> None:
    namespace = {"Annotated": Annotated}
    prefix = "*, " if keyword_only else ""
    exec(
        f"def command({prefix}target: Annotated[int, 'target'] = None): pass",
        namespace,
    )
    command = namespace["command"]
    defaults = command.__defaults__
    kwdefaults = command.__kwdefaults__
    annotations = command.__annotations__.copy()
    with pytest.raises(DefinitionError, match="既定値"):
        inspect_parameters(command, SOURCE)
    assert command.__defaults__ is defaults
    assert command.__kwdefaults__ is kwdefaults
    assert command.__annotations__ == annotations


def test_explicit_optional_is_still_an_unsupported_type() -> None:
    def command(target: int | None = None) -> None:
        pass

    with pytest.raises(DefinitionError, match="対応型"):
        inspect_parameters(command, SOURCE)

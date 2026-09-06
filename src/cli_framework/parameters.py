"""command関数のシグネチャを中立な引数記述へ変換する。"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Annotated, get_args, get_origin, get_type_hints

from .errors import DefinitionError
from .model import SourceDescriptor


SupportedValue = str | int | float | bool
SupportedType = type[str] | type[int] | type[float] | type[bool]
_SUPPORTED_TYPES: frozenset[SupportedType] = frozenset({str, int, float, bool})


@dataclass(frozen=True, slots=True)
class ParameterDescriptor:
    """Clickへ依存しない1つのcommand引数。"""

    name: str
    parameter_type: SupportedType
    required: bool
    default: SupportedValue | None = None
    help_text: str | None = None


def inspect_parameters(
    command: Callable[..., object],
    source: SourceDescriptor,
    *,
    route: tuple[str, ...] = (),
) -> tuple[ParameterDescriptor, ...]:
    """同期commandの引数を検査し、中立な記述子として返す。"""

    try:
        signature = inspect.signature(command)
        # Resolve annotations without function defaults: Python 3.10 otherwise
        # implicitly wraps annotations in Optional when their default is None.
        annotations = SimpleNamespace(__annotations__=command.__annotations__)
        type_hints = get_type_hints(
            annotations, globalns=command.__globals__, include_extras=True
        )
    except (NameError, TypeError, ValueError) as error:
        raise DefinitionError(
            "commandの型注釈を解決できません",
            route=route,
            source=source,
        ) from error

    descriptors: list[ParameterDescriptor] = []
    for parameter in signature.parameters.values():
        descriptors.append(
            _inspect_parameter(parameter, type_hints, source, route)
        )
    return tuple(descriptors)


def _inspect_parameter(
    parameter: inspect.Parameter,
    type_hints: dict[str, object],
    source: SourceDescriptor,
    route: tuple[str, ...],
) -> ParameterDescriptor:
    if parameter.kind in {
        inspect.Parameter.VAR_POSITIONAL,
        inspect.Parameter.VAR_KEYWORD,
    }:
        _invalid(parameter, "可変長引数には対応していません", source, route)
    if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
        _invalid(parameter, "位置専用引数には対応していません", source, route)
    if parameter.name not in type_hints:
        _invalid(parameter, "型注釈が必要です", source, route)

    parameter_type, help_text = _unwrap_annotation(
        parameter,
        type_hints[parameter.name],
        source,
        route,
    )
    required = parameter.default is inspect.Parameter.empty
    default: SupportedValue | None = None
    if not required:
        if type(parameter.default) is not parameter_type:
            _invalid(
                parameter,
                "既定値が型注釈と一致しません",
                source,
                route,
            )
        default = parameter.default

    return ParameterDescriptor(
        name=parameter.name,
        parameter_type=parameter_type,
        required=required,
        default=default,
        help_text=help_text,
    )


def _unwrap_annotation(
    parameter: inspect.Parameter,
    annotation: object,
    source: SourceDescriptor,
    route: tuple[str, ...],
) -> tuple[SupportedType, str | None]:
    help_text: str | None = None
    if get_origin(annotation) is Annotated:
        arguments = get_args(annotation)
        annotation = arguments[0]
        metadata = arguments[1:]
        if any(not isinstance(item, str) for item in metadata):
            _invalid(
                parameter,
                "Annotatedのメタデータは文字列である必要があります",
                source,
                route,
            )
        if len(metadata) > 1:
            _invalid(
                parameter,
                "Annotatedの引数説明は1つだけ指定できます",
                source,
                route,
            )
        if metadata:
            help_text = metadata[0]

    if annotation not in _SUPPORTED_TYPES:
        _invalid(
            parameter,
            "対応型はstr、int、float、boolだけです",
            source,
            route,
        )
    return annotation, help_text  # type: ignore[return-value]


def _invalid(
    parameter: inspect.Parameter,
    message: str,
    source: SourceDescriptor,
    route: tuple[str, ...],
) -> None:
    raise DefinitionError(
        f"引数 {parameter.name!r}: {message}",
        route=route,
        source=source,
    )

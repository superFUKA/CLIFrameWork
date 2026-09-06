"""Contextとsetup・teardownを伴うcommand実行を制御する。"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence

from .context import Context, _activate_context
from .errors import DefinitionError
from .loading import load_function
from .model import GroupDescriptor, SourceDescriptor


def run_with_lifecycle(
    command: Callable[..., object],
    values: dict[str, object],
    scopes: Sequence[GroupDescriptor],
    bindings: Mapping[str, str],
) -> object:
    """setup、command、teardownをContext内で規定順に実行する。"""

    with _activate_context(bindings) as context:
        completed: list[GroupDescriptor] = []
        result: object = None
        primary: BaseException | None = None
        try:
            for scope in scopes:
                if scope.setup is not None:
                    setup = _load_lifecycle(scope.setup, "setup")
                    setup()
                completed.append(scope)
            result = command(**values)
        except BaseException as error:
            primary = error

        context._set_exception(primary)
        primary = _run_teardowns(completed, context, primary)
        if primary is not None:
            raise primary
        return result


def _load_lifecycle(
    source: SourceDescriptor,
    function_name: str,
) -> Callable[..., object]:
    function = load_function(source, function_name)
    if inspect.signature(function).parameters:
        raise DefinitionError(
            f"{function_name}関数は引数を取れません",
            source=source,
        )
    return function


def _run_teardowns(
    completed: Sequence[GroupDescriptor],
    context: Context,
    primary: BaseException | None,
) -> BaseException | None:
    for scope in reversed(completed):
        if scope.teardown is None:
            continue
        try:
            teardown = _load_lifecycle(scope.teardown, "teardown")
            teardown()
        except BaseException as error:
            if primary is None:
                primary = error
                context._set_exception(primary)
            else:
                _attach_teardown_failure(primary, error)
    return primary


def _attach_teardown_failure(
    primary: BaseException,
    teardown_error: BaseException,
) -> None:
    note = (
        "teardownも失敗しました: "
        f"{type(teardown_error).__name__}: {teardown_error}"
    )
    add_note = getattr(primary, "add_note", None)
    if add_note is not None:
        add_note(note)
    else:
        # A separate diagnostic avoids cycles through teardown_error.__context__.
        diagnostic = RuntimeError(note).with_traceback(teardown_error.__traceback__)
        diagnostic.__cause__ = primary.__cause__ or primary.__context__
        primary.__cause__ = diagnostic

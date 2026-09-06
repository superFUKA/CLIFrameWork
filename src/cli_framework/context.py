"""実行ごとに分離されたCLI Contextを提供する。"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType

from .errors import CliFrameworkError


class Context:
    """現在のCLI実行に属するbindings、state、例外を保持する。"""

    __slots__ = ("_bindings", "_state", "_exception")

    def __init__(self, bindings: Mapping[str, str]) -> None:
        self._bindings = MappingProxyType(dict(bindings))
        self._state: dict[str, object] = {}
        self._exception: BaseException | None = None

    @property
    def bindings(self) -> Mapping[str, str]:
        """作成時にコピーされた読み取り専用bindingsを返す。"""

        return self._bindings

    @property
    def state(self) -> MutableMapping[str, object]:
        """この実行中に利用者が共有できる可変stateを返す。"""

        return self._state

    @property
    def exception(self) -> BaseException | None:
        """teardownから参照できる、この実行の主例外を返す。"""

        return self._exception

    def get_binding(self, key: str) -> str:
        """binding値を取得し、存在しないキーを明確に報告する。"""

        try:
            return self._bindings[key]
        except KeyError as error:
            raise CliFrameworkError(
                f"binding {key!r} は現在のContextに存在しません"
            ) from error

    def _set_exception(self, exception: BaseException | None) -> None:
        self._exception = exception


_CURRENT_CONTEXT: ContextVar[Context | None] = ContextVar(
    "cli_framework_current_context",
    default=None,
)


def current_context() -> Context:
    """現在の管理されたCLI実行Contextを返す。"""

    context = _CURRENT_CONTEXT.get()
    if context is None:
        raise CliFrameworkError("管理されたCLI実行の外ではContextを利用できません")
    return context


@contextmanager
def _activate_context(bindings: Mapping[str, str]) -> Iterator[Context]:
    """新しいContextを有効化し、終了時に以前の値を復元する。"""

    context = Context(bindings)
    token = _CURRENT_CONTEXT.set(context)
    try:
        yield context
    finally:
        _CURRENT_CONTEXT.reset(token)

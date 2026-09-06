"""cli-frameworkが公開する例外。"""

from __future__ import annotations

from collections.abc import Iterable

from .model import SourceDescriptor


class CliFrameworkError(Exception):
    """フレームワークが送出する例外の基底型。"""


class DefinitionError(CliFrameworkError):
    """CLI定義の不備を、論理ルートとソース位置付きで報告する。"""

    def __init__(
        self,
        message: str,
        *,
        route: Iterable[str] = (),
        source: SourceDescriptor | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.route = tuple(route)
        self.source = source

    def __str__(self) -> str:
        details: list[str] = []
        if self.route:
            details.append(f"ルート: {' '.join(self.route)}")
        if self.source is not None:
            details.append(
                f"ソース: {self.source.module_name} ({self.source.location()})"
            )
        if not details:
            return self.message
        return f"{self.message} [{' ; '.join(details)}]"

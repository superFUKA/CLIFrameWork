"""Clickに依存しないCLIルートのデータモデル。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    """Pythonモジュールと、その定義位置を表す。"""

    module_name: str
    path: Path
    line: int | None = None
    column: int | None = None

    def location(self) -> str:
        """OSに依存しない表示用のソース位置を返す。"""

        location = self.path.as_posix()
        if self.line is not None:
            location = f"{location}:{self.line}"
            if self.column is not None:
                location = f"{location}:{self.column}"
        return location


@dataclass(frozen=True, slots=True)
class CommandDescriptor:
    """末端またはグループ既定のcommand関数を表す。"""

    name: str
    source: SourceDescriptor
    help_text: str | None = None


@dataclass(frozen=True, slots=True)
class GroupDescriptor:
    """子ルートと任意の既定commandを持つCLIグループを表す。"""

    name: str
    source: SourceDescriptor | None = None
    help_text: str | None = None
    setup: SourceDescriptor | None = None
    teardown: SourceDescriptor | None = None
    command: CommandDescriptor | None = None
    children: tuple[CommandDescriptor | GroupDescriptor, ...] = ()


RouteDescriptor: TypeAlias = CommandDescriptor | GroupDescriptor

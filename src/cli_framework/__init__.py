"""ディレクトリ構造から階層CLIを構築するフレームワーク。"""

from .context import Context, current_context
from .errors import CliFrameworkError, DefinitionError
from .factory import create_cli

__all__ = [
    "CliFrameworkError",
    "Context",
    "DefinitionError",
    "create_cli",
    "current_context",
]

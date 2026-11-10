"""ディレクトリ構造から階層CLIを構築するフレームワーク。"""

from .context import Context, current_context
from .description import ParameterInfo, RouteInfo
from .errors import CliFrameworkError, CommandError, DefinitionError
from .factory import create_cli, describe_cli

__all__ = [
    "CliFrameworkError",
    "CommandError",
    "Context",
    "DefinitionError",
    "ParameterInfo",
    "RouteInfo",
    "create_cli",
    "current_context",
    "describe_cli",
]

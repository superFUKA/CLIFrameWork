"""サンプルCLIの組み立て場所。"""

from cli_framework import create_cli

from . import commands


cli = create_cli(
    commands,
    name="example-cli",
    bindings={"_project_": "demo"},
)

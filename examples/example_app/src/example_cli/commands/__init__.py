"""サンプルアプリケーションのルートコマンド。"""

from cli_framework import current_context

from .events import events


def setup() -> None:
    context = current_context()
    context.state["application"] = "example"
    events.append("root:setup")


def teardown() -> None:
    events.append("root:teardown")

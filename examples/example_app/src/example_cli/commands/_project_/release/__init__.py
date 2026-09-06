"""リリース成果物を操作します。"""

from cli_framework import current_context

from ...events import events


def setup() -> None:
    current_context().state["release"] = "active"
    events.append("release:setup")


def teardown() -> None:
    events.append("release:teardown")

"""リリース成果物をビルドします。"""

from typing import Annotated

from cli_framework import current_context

from ...events import events


def command(
    source: Annotated[str, "入力元"],
    jobs: Annotated[int, "並列数"] = 1,
    clean: Annotated[bool, "先に削除する"] = False,
) -> None:
    context = current_context()
    events.append("build:command")
    print(
        f"{context.state['application']}:{context.state['project']}:"
        f"{context.state['release']}:{source}:jobs={jobs}:clean={clean}"
    )

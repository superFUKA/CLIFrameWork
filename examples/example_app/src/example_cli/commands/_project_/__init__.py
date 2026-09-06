"""bindingで選択されるプロジェクトを操作します。"""

from cli_framework import current_context

from ..events import events


def setup() -> None:
    project = current_context().get_binding("_project_")
    current_context().state["project"] = project
    events.append(f"project:setup:{project}")


def command(target: str = "overview") -> None:
    """プロジェクトグループを直接実行します。"""

    context = current_context()
    events.append("project:command")
    print(f"{context.state['application']}:{context.state['project']}:{target}")


def teardown() -> None:
    events.append("project:teardown")

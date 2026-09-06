from __future__ import annotations

import importlib
import traceback
from pathlib import Path

import pytest
from fixtures.runner import CliRunner

from cli_framework import current_context
from cli_framework.click_group import build_click_group
from cli_framework.errors import CliFrameworkError
from cli_framework.model import CommandDescriptor, GroupDescriptor, SourceDescriptor
from cli_framework.runtime import _attach_teardown_failure


def _source(module: str, path: Path) -> SourceDescriptor:
    return SourceDescriptor(module, path, line=1)


def test_teardown_diagnostics_without_add_note_preserve_existing_chain():
    class LegacyError(Exception):
        add_note = None

    original_cause = OSError("original cause")
    primary = LegacyError("command failed")
    primary.__cause__ = original_cause
    for message in ("inner cleanup", "outer cleanup"):
        secondary = ValueError(message)
        secondary.__context__ = primary
        _attach_teardown_failure(primary, secondary)
    formatted = "".join(traceback.format_exception(type(primary), primary, None))
    for text in ("original cause", "command failed", "inner cleanup", "outer cleanup"):
        assert text in formatted
    assert formatted.rstrip().endswith("LegacyError: command failed")


def _make_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    package_name: str,
    *,
    root_code: str,
    child_code: str,
    command_code: str,
) -> tuple[GroupDescriptor, str]:
    package = tmp_path / package_name
    child = package / "project"
    child.mkdir(parents=True)
    (package / "events.py").write_text("events = []\n", encoding="utf-8")
    root_path = package / "__init__.py"
    child_path = child / "__init__.py"
    command_path = child / "build.py"
    root_path.write_text(root_code, encoding="utf-8")
    child_path.write_text(child_code, encoding="utf-8")
    command_path.write_text(command_code, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    root_module = package_name
    child_module = f"{package_name}.project"
    command_module = f"{child_module}.build"
    leaf = CommandDescriptor("build", _source(command_module, command_path))
    child_group = GroupDescriptor(
        "project",
        source=_source(child_module, child_path),
        setup=_source(child_module, child_path),
        teardown=_source(child_module, child_path),
        children=(leaf,),
    )
    root = GroupDescriptor(
        "tool",
        source=_source(root_module, root_path),
        setup=_source(root_module, root_path),
        teardown=_source(root_module, root_path),
        children=(child_group,),
    )
    return root, f"{package_name}.events"


def test_setup_and_teardown_run_in_nested_order_with_shared_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, events_module = _make_tree(
        monkeypatch,
        tmp_path,
        "lifecycle_order",
        root_code=(
            "from cli_framework import current_context\n"
            "from .events import events\n"
            "def setup():\n"
            "    current_context().state['root'] = 'ready'\n"
            "    events.append('root-setup')\n"
            "def teardown():\n"
            "    events.append('root-teardown:' + str(current_context().exception))\n"
        ),
        child_code=(
            "from cli_framework import current_context\n"
            "from ..events import events\n"
            "def setup():\n"
            "    events.append('child-setup:' + current_context().state['root'])\n"
            "def teardown():\n"
            "    events.append('child-teardown:' + str(current_context().exception))\n"
        ),
        command_code=(
            "from cli_framework import current_context\n"
            "from ..events import events\n"
            "def command():\n"
            "    events.append('command:' + current_context().get_binding('_name_'))\n"
        ),
    )

    result = CliRunner().invoke(
        build_click_group(root, bindings={"_name_": "alpha"}),
        ["project", "build"],
    )
    events = importlib.import_module(events_module).events

    assert result.exit_code == 0
    assert events == [
        "root-setup",
        "child-setup:ready",
        "command:alpha",
        "child-teardown:None",
        "root-teardown:None",
    ]


def test_setup_failure_skips_command_and_its_own_teardown_but_unwinds_outer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, events_module = _make_tree(
        monkeypatch,
        tmp_path,
        "lifecycle_setup_failure",
        root_code=(
            "from .events import events\n"
            "def setup(): events.append('root-setup')\n"
            "def teardown(): events.append('root-teardown')\n"
        ),
        child_code=(
            "from ..events import events\n"
            "def setup():\n"
            "    events.append('child-setup')\n"
            "    raise RuntimeError('setup failed')\n"
            "def teardown(): events.append('child-teardown')\n"
        ),
        command_code=(
            "from ..events import events\n"
            "def command(): events.append('command')\n"
        ),
    )

    result = CliRunner().invoke(
        build_click_group(root), ["project", "build"]
    )
    events = importlib.import_module(events_module).events

    assert result.exit_code == 1
    assert "setup failed" in result.stderr
    assert events == ["root-setup", "child-setup", "root-teardown"]


def test_command_exception_is_visible_and_preserved_when_teardowns_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, events_module = _make_tree(
        monkeypatch,
        tmp_path,
        "lifecycle_command_failure",
        root_code=(
            "from cli_framework import current_context\n"
            "from .events import events\n"
            "def setup(): events.append('root-setup')\n"
            "def teardown():\n"
            "    events.append('root-sees:' + str(current_context().exception))\n"
            "    raise OSError('root teardown failed')\n"
        ),
        child_code=(
            "from cli_framework import current_context\n"
            "from ..events import events\n"
            "def setup(): events.append('child-setup')\n"
            "def teardown():\n"
            "    events.append('child-sees:' + str(current_context().exception))\n"
            "    raise ValueError('child teardown failed')\n"
        ),
        command_code="def command(): raise RuntimeError('command failed')\n",
    )

    result = CliRunner().invoke(
        build_click_group(root, debug=True), ["project", "build"]
    )
    events = importlib.import_module(events_module).events

    assert result.exit_code == 1
    assert "RuntimeError: command failed" in result.stderr
    assert "teardownも失敗しました: ValueError: child teardown failed" in result.stderr
    assert "teardownも失敗しました: OSError: root teardown failed" in result.stderr
    assert events == [
        "root-setup",
        "child-setup",
        "child-sees:command failed",
        "root-sees:command failed",
    ]


def test_first_teardown_failure_becomes_primary_and_remaining_teardown_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, events_module = _make_tree(
        monkeypatch,
        tmp_path,
        "lifecycle_teardown_failure",
        root_code=(
            "from cli_framework import current_context\n"
            "from .events import events\n"
            "def setup(): pass\n"
            "def teardown():\n"
            "    events.append('root:' + str(current_context().exception))\n"
        ),
        child_code=(
            "from ..events import events\n"
            "def setup(): pass\n"
            "def teardown():\n"
            "    events.append('child')\n"
            "    raise ValueError('teardown failed')\n"
        ),
        command_code="def command(): pass\n",
    )

    result = CliRunner().invoke(
        build_click_group(root), ["project", "build"]
    )
    events = importlib.import_module(events_module).events

    assert result.exit_code == 1
    assert "teardown failed" in result.stderr
    assert events == ["child", "root:teardown failed"]


def test_lifecycle_function_arguments_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, events_module = _make_tree(
        monkeypatch,
        tmp_path,
        "lifecycle_arguments",
        root_code=(
            "from .events import events\n"
            "def setup(value): pass\n"
            "def teardown(): events.append('teardown')\n"
        ),
        child_code="def setup(): pass\ndef teardown(): pass\n",
        command_code="def command(): pass\n",
    )

    result = CliRunner().invoke(
        build_click_group(root), ["project", "build"]
    )
    events = importlib.import_module(events_module).events

    assert result.exit_code == 1
    assert "setup関数は引数を取れません" in result.stderr
    assert events == []


def test_help_skips_all_lifecycle_processing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, events_module = _make_tree(
        monkeypatch,
        tmp_path,
        "lifecycle_help",
        root_code=(
            "from .events import events\n"
            "def setup(): events.append('root-setup')\n"
            "def teardown(): events.append('root-teardown')\n"
        ),
        child_code=(
            "from ..events import events\n"
            "def setup(): events.append('child-setup')\n"
            "def teardown(): events.append('child-teardown')\n"
        ),
        command_code=(
            "from ..events import events\n"
            "def command(): events.append('command')\n"
        ),
    )
    cli = build_click_group(root)

    root_help = CliRunner().invoke(cli, ["--help"])
    leaf_help = CliRunner().invoke(cli, ["project", "build", "--help"])
    events = importlib.import_module(events_module).events

    assert root_help.exit_code == 0
    assert leaf_help.exit_code == 0
    assert events == []


def test_context_is_restored_after_cli_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _ = _make_tree(
        monkeypatch,
        tmp_path,
        "lifecycle_context_restore",
        root_code="def setup(): pass\ndef teardown(): pass\n",
        child_code="def setup(): pass\ndef teardown(): pass\n",
        command_code="def command(): pass\n",
    )

    result = CliRunner().invoke(
        build_click_group(root), ["project", "build"]
    )

    assert result.exit_code == 0
    with pytest.raises(CliFrameworkError):
        current_context()

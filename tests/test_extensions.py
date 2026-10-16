import importlib
import sys

import pytest

from cli_framework import DefinitionError, create_cli
from tests.fixtures.packages import write_package
from tests.fixtures.runner import CliRunner


def _import(name: str):
    return importlib.import_module(name)


def _main_package(monkeypatch, tmp_path, files=None):
    write_package(monkeypatch, tmp_path, "ext_main", files)
    return _import("ext_main")


def _extension(monkeypatch, tmp_path, name, files=None):
    write_package(monkeypatch, tmp_path, name, files)
    return _import(name)


def test_extension_commands_are_merged_into_existing_group(monkeypatch, tmp_path):
    main = _main_package(monkeypatch, tmp_path, {
        "file/__init__.py": '"""ファイル操作"""\n',
        "file/list.py": "def command():\n    print('list')\n",
    })
    extension = _extension(monkeypatch, tmp_path, "ext_plugin", {
        "copy.py": "def command(source: str):\n    print('copy', source)\n",
        "sub/move.py": "from .._helper import VALUE\n\ndef command():\n    print('move', VALUE)\n",
        "_helper.py": "VALUE = 'ok'\n",
    })

    cli = create_cli(main, name="tool", extensions=[("file", extension)])
    runner = CliRunner()

    copied = runner.invoke(cli, ["file", "copy", "a.txt"])
    moved = runner.invoke(cli, ["file", "sub", "move"])
    listed = runner.invoke(cli, ["file", "list"])
    help_result = runner.invoke(cli, ["file", "--help"])

    assert (copied.exit_code, copied.stdout, copied.stderr) == (0, "copy a.txt\n", "")
    assert (moved.exit_code, moved.stdout) == (0, "move ok\n")
    assert (listed.exit_code, listed.stdout) == (0, "list\n")
    assert help_result.exit_code == 0
    assert "ファイル操作" in help_result.stdout
    for name in ("copy", "list", "sub"):
        assert name in help_result.stdout


def test_missing_mount_groups_are_created(monkeypatch, tmp_path):
    main = _main_package(monkeypatch, tmp_path, {
        "build.py": "def command():\n    pass\n",
    })
    extension = _extension(monkeypatch, tmp_path, "ext_new", {
        "__init__.py": '"""追加ツール"""\n',
        "run.py": "def command():\n    print('run')\n",
    })

    cli = create_cli(main, extensions={"plugins/extra": extension})
    runner = CliRunner()

    result = runner.invoke(cli, ["plugins", "extra", "run"])
    group_help = runner.invoke(cli, ["plugins", "extra", "--help"])

    assert (result.exit_code, result.stdout, result.stderr) == (0, "run\n", "")
    assert "追加ツール" in group_help.stdout


def test_empty_mount_path_merges_into_root(monkeypatch, tmp_path):
    main = _main_package(monkeypatch, tmp_path, {
        "build.py": "def command():\n    print('build')\n",
    })
    extension = _extension(monkeypatch, tmp_path, "ext_root", {
        "deploy.py": "def command():\n    print('deploy')\n",
    })

    cli = create_cli(main, extensions=[("", extension)])
    runner = CliRunner()

    assert runner.invoke(cli, ["deploy"]).stdout == "deploy\n"
    assert runner.invoke(cli, ["build"]).stdout == "build\n"


def test_multiple_extensions_can_share_a_mount(monkeypatch, tmp_path):
    main = _main_package(monkeypatch, tmp_path)
    first = _extension(monkeypatch, tmp_path, "ext_first", {
        "one.py": "def command():\n    print('one')\n",
    })
    second = _extension(monkeypatch, tmp_path, "ext_second", {
        "two.py": "def command():\n    print('two')\n",
    })

    cli = create_cli(main, extensions=[("tools", first), ("tools", second)])
    runner = CliRunner()

    assert runner.invoke(cli, ["tools", "one"]).stdout == "one\n"
    assert runner.invoke(cli, ["tools", "two"]).stdout == "two\n"


def test_main_group_docstring_takes_precedence(monkeypatch, tmp_path):
    main = _main_package(monkeypatch, tmp_path, {
        "file/__init__.py": '"""本体の説明"""\n',
        "file/list.py": "def command():\n    pass\n",
    })
    extension = _extension(monkeypatch, tmp_path, "ext_doc", {
        "__init__.py": '"""拡張の説明"""\n',
        "copy.py": "def command():\n    pass\n",
    })

    cli = create_cli(main, extensions=[("file", extension)])
    result = CliRunner().invoke(cli, ["file", "--help"])

    assert "本体の説明" in result.stdout
    assert "拡張の説明" not in result.stdout


def test_lifecycle_from_main_and_extension_scopes_runs(monkeypatch, tmp_path):
    main = _main_package(monkeypatch, tmp_path, {
        "__init__.py": (
            "def setup():\n    print('root setup')\n\n"
            "def teardown():\n    print('root teardown')\n"
        ),
        "file/__init__.py": "def setup():\n    print('file setup')\n",
    })
    extension = _extension(monkeypatch, tmp_path, "ext_life", {
        "__init__.py": "def teardown():\n    print('ext teardown')\n",
        "copy.py": "def command():\n    print('copy')\n",
    })

    cli = create_cli(main, extensions=[("file", extension)])
    result = CliRunner().invoke(cli, ["file", "copy"])

    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "root setup",
        "file setup",
        "copy",
        "ext teardown",
        "root teardown",
    ]


def test_bindings_apply_to_mount_path_and_extension(monkeypatch, tmp_path):
    main = _main_package(monkeypatch, tmp_path)
    extension = _extension(monkeypatch, tmp_path, "ext_bind", {
        "_target_.py": (
            "from cli_framework import current_context\n\n"
            "def command():\n    print(current_context().get_binding('_target_'))\n"
        ),
    })

    cli = create_cli(
        main,
        bindings={"_project_": "alpha", "_target_": "beta"},
        extensions=[("_project_", extension)],
    )
    result = CliRunner().invoke(cli, ["alpha", "beta"])

    assert (result.exit_code, result.stdout) == (0, "beta\n")


def test_extension_modules_are_not_imported_during_construction(monkeypatch, tmp_path):
    main = _main_package(monkeypatch, tmp_path)
    extension = _extension(monkeypatch, tmp_path, "ext_lazy", {
        "copy.py": "raise RuntimeError('imported')\n\ndef command():\n    pass\n",
    })

    cli = create_cli(main, extensions=[("file", extension)])
    result = CliRunner().invoke(cli, ["file", "--help"])

    assert result.exit_code == 0
    assert "ext_lazy.copy" not in sys.modules


@pytest.mark.parametrize(
    ("main_files", "extension_files", "message"),
    [
        (
            {"file/copy.py": "def command():\n    pass\n"},
            {"copy.py": "def command():\n    pass\n"},
            "同じルート名のコマンドが複数あります",
        ),
        (
            {"file/__init__.py": "def setup():\n    pass\n"},
            {"__init__.py": "def setup():\n    pass\n", "copy.py": "def command():\n    pass\n"},
            "setup関数が複数のパッケージで定義されています",
        ),
        (
            {"file/__init__.py": "def command():\n    pass\n"},
            {"__init__.py": "def command():\n    pass\n"},
            "command関数が複数のパッケージで定義されています",
        ),
        (
            {"file.py": "def command():\n    pass\n"},
            {"copy.py": "def command():\n    pass\n"},
            "グループとコマンドの名前が重複しています",
        ),
    ],
)
def test_conflicting_definitions_are_rejected(
    monkeypatch, tmp_path, main_files, extension_files, message
):
    main = _main_package(monkeypatch, tmp_path, main_files)
    extension = _extension(monkeypatch, tmp_path, "ext_conflict", extension_files)

    with pytest.raises(DefinitionError, match=message):
        create_cli(main, extensions=[("file", extension)])


def test_conflict_diagnostic_names_extension_source(monkeypatch, tmp_path):
    main = _main_package(monkeypatch, tmp_path, {
        "file/copy.py": "def command():\n    pass\n",
    })
    extension = _extension(monkeypatch, tmp_path, "ext_source", {
        "copy.py": "def command():\n    pass\n",
    })

    with pytest.raises(DefinitionError) as raised:
        create_cli(main, extensions=[("file", extension)])

    assert raised.value.route == ("ext_main", "file", "copy")
    assert raised.value.source is not None
    assert raised.value.source.module_name == "ext_source.copy"


@pytest.mark.parametrize("mount", ["file/", "/file", "a//b", "-x", "a b", "a\x00b"])
def test_invalid_mount_paths_are_rejected(monkeypatch, tmp_path, mount):
    main = _main_package(monkeypatch, tmp_path)
    extension = _extension(monkeypatch, tmp_path, "ext_mount", {
        "copy.py": "def command():\n    pass\n",
    })

    with pytest.raises(DefinitionError, match="拡張先パス"):
        create_cli(main, extensions=[(mount, extension)])


def test_overlapping_packages_are_rejected(monkeypatch, tmp_path):
    main = _main_package(monkeypatch, tmp_path, {
        "inner/__init__.py": "",
        "inner/copy.py": "def command():\n    pass\n",
    })
    inner = _import("ext_main.inner")
    extension = _extension(monkeypatch, tmp_path, "ext_twice", {
        "copy.py": "def command():\n    pass\n",
    })

    with pytest.raises(DefinitionError, match="重複しています"):
        create_cli(main, extensions=[("other", inner)])
    with pytest.raises(DefinitionError, match="重複しています"):
        create_cli(main, extensions=[("a", extension), ("b", extension)])


@pytest.mark.parametrize("extensions", ["file", [("file",)], [(1, None)], 3])
def test_malformed_extensions_are_rejected(monkeypatch, tmp_path, extensions):
    main = _main_package(monkeypatch, tmp_path)

    with pytest.raises(DefinitionError, match="extensions"):
        create_cli(main, extensions=extensions)


def test_non_package_extension_is_rejected(monkeypatch, tmp_path):
    main = _main_package(monkeypatch, tmp_path)

    with pytest.raises(DefinitionError, match="パッケージ"):
        create_cli(main, extensions=[("file", sys)])

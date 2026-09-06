# 新規アプリの最小構成

既存アプリではこの構成を強制しない。以下のmy_app/my-toolは利用者の名前へ置き換える。

```text
pyproject.toml
src/my_app/
    __init__.py
    __main__.py
    cli.py
    commands/
        __init__.py
        greet.py
tests/
    test_cli.py
```

`__init__.py`は空でよい。依存は信頼できるcli-frameworkを先にインストールする。以下の依存宣言だけでは入手元は特定されない。

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "my-cli-app"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["cli-framework>=0.1,<1"]

[project.optional-dependencies]
test = ["pytest>=8,<9"]

[project.scripts]
my-tool = "my_app.cli:cli"

[tool.setuptools.packages.find]
where = ["src"]
```

`src/my_app/cli.py`：

```python
from cli_framework import create_cli
from . import commands

cli = create_cli(commands, name="my-tool")
```

`src/my_app/__main__.py`：

```python
from .cli import cli

if __name__ == "__main__":
    cli()
```

`src/my_app/commands/greet.py`：

```python
from typing import Annotated


def command(name: Annotated[str, "相手の名前"], loud: bool = False) -> None:
    """挨拶を表示します。"""
    message = f"Hello, {name}!"
    print(message.upper() if loud else message)
```

`tests/test_cli.py`：

```python
import inspect
from click.testing import CliRunner
from my_app.cli import cli


def runner():
    if "mix_stderr" in inspect.signature(CliRunner).parameters:
        return CliRunner(mix_stderr=False)
    return CliRunner()


def test_greet():
    result = runner().invoke(cli, ["greet", "Ada", "--loud"])
    assert result.exit_code == 0
    assert result.stdout == "HELLO, ADA!\n"
    assert result.stderr == ""


def test_help_does_not_greet():
    result = runner().invoke(cli, ["greet", "--help"])
    assert result.exit_code == 0
    assert "--loud" in result.stdout
    assert "Hello," not in result.stdout
    assert result.stderr == ""


def test_missing_name():
    result = runner().invoke(cli, ["greet"])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Missing argument" in result.stderr
```

対象アプリのvenvで信頼するフレームワークをインストールした後、アプリを`python -m pip install -e ".[test]"`でインストールして`python -m pytest`を実行する。最後に`my-tool greet Ada`と`python -m my_app greet Ada`を確認する。公開パッケージレジストリへのアップロードはこの手順に含めない。

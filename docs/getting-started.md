# 利用ガイド

## 1. コマンドパッケージを作る

import可能なPythonパッケージを1つ、コマンドのルートとして用意します。通常の`.py`ファイルは末端コマンド、サブパッケージはグループになります。トップレベルに`command`関数を持たない補助モジュールはCLIへ公開されません。

```text
commands/
    __init__.py          # ルートグループ
    status.py            # status
    project/
        __init__.py      # projectグループ
        release/
            __init__.py  # project releaseグループ
            build.py     # project release build
```

command関数のdocstringをヘルプに表示します。未指定の場合はモジュールdocstringを使います。グループの説明には`__init__.py`のモジュールdocstringを使います。

## 2. command関数を書く

引数の型注釈には`str`、`int`、`float`、`bool`を使用できます。デフォルト値のない引数は位置引数、デフォルト値のある引数はOptionになります。Python名のunderscoreはOption名でhyphenへ変換され、`bool` Optionには肯定形と否定形が作られます。

```python
from typing import Annotated


def command(
    target: Annotated[str, "対象名"],
    retry_count: Annotated[int, "再試行回数"] = 2,
    threshold: Annotated[float, "閾値"] = 0.8,
    verbose: Annotated[bool, "詳細を表示する"] = False,
) -> int:
    print(target, retry_count, threshold, verbose)
    return 0
```

`Annotated`の文字列は引数やOptionの説明になります。この例は`TARGET`、`--retry-count`、`--threshold`、`--verbose / --no-verbose`を生成します。

## 3. CLIを公開する

```python
from cli_framework import create_cli

from . import commands


cli = create_cli(commands, name="my-tool")
```

戻り値はClick互換のルートコマンドなので、直接呼び出すほか、既存のClick向けテスト・実行環境でも利用できます。

## 動的な経路名

名前全体がunderscoreで囲まれたファイルまたはディレクトリはbindingのプレースホルダーです。

```text
commands/
    _project_/
        show.py
```

```python
cli = create_cli(
    commands,
    bindings={"_project_": "alpha"},
)
```

これにより`alpha show`が公開されます。bindingの不足、不正な値、置換後の同名経路はCLI構築時の定義エラーです。部分文字列は置換されません。

commandから解決値を参照する場合は現在のContextを使います。

```python
from cli_framework import current_context


def command() -> None:
    print(current_context().get_binding("_project_"))
```

## グループの直接実行

グループの`__init__.py`に`command`を書くと、そのグループを直接実行できます。同じ位置に固定名の子コマンドがある場合、固定名が既定commandの位置引数より優先されます。

## setupとteardown

グループの`__init__.py`には、引数を取らない`setup`と`teardown`を定義できます。実行時は外側から内側へsetupを行い、commandの後に内側から外側へteardownを行います。ヘルプ表示では実行されません。

`current_context().state`は1回の実行内で共有できる辞書です。`teardown`では`current_context().exception`により、処理中の主例外を確認できます。

## 終了とエラー

- `command`が`None`または`0`を返すと終了コード0です。
- `int`を返すと、その値が終了コードになります。
- 経路や引数の用法エラーは終了コード2です。
- アプリケーション例外や定義エラーは終了コード1です。
- 通常モードでは簡潔なエラーをstderrへ出し、`debug=True`ではtracebackもstderrへ出します。

より大きな構成は[サンプルアプリ](../examples/example_app)で確認できます。

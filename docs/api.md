# 公開API

公開APIは`cli_framework`パッケージ直下からimportします。内部モジュールは互換性契約の対象外です。

## `create_cli`

```python
create_cli(
    command_package: ModuleType,
    *,
    name: str | None = None,
    bindings: Mapping[str, str] | None = None,
    extensions: Mapping[str, ModuleType]
        | Iterable[tuple[str, ModuleType]]
        | None = None,
    debug: bool = False,
    structured: bool = False,
) -> click.Command
```

import済みのコマンドパッケージを走査し、Click互換のルートコマンドを返します。

静的探索・binding・ルート衝突はこの呼び出しで検証します。commandのimportとシグネチャは詳細ヘルプ取得・引数解析時、setup/teardownの定義は実行時に検証します。通常のCLI呼び出しは定義エラーをstderrと終了コード1で報告します。Pythonから`main(..., standalone_mode=False)`で呼ぶ場合は`DefinitionError`を捕捉できます。

- `command_package`: `__path__`を持つimport済みPythonパッケージ。
- `name`: 表示するルートCLI名。省略時はパッケージ名の最後の区間。
- `bindings`: `_name_`形式の経路区間を具体名へ置換する文字列mapping。構築時にコピーされます。
- `extensions`: 別の場所にあるcommandパッケージを本体のグループ配下へ重ねる`(拡張先パス, パッケージ)`の組の列、またはmapping。拡張先パスは`/`区切りのディレクトリ区間で、空文字はルートです。規則は[製品仕様](product-spec.md#拡張パッケージの振る舞い)を参照してください。
- `debug`: `True`の場合、実行時例外のtracebackをstderrへ表示します。
- `structured`: `True`の場合、構造化出力を有効にします。commandは結果のデータを返し、全commandに`--json`を追加し、各commandに重さ`EFFECT`を要求します。規則は[製品仕様](product-spec.md)の「構造化出力」を参照してください。

```python
from cli_framework import create_cli
from my_app import commands

cli = create_cli(
    commands,
    name="my-tool",
    bindings={"_project_": "alpha"},
    debug=False,
)
```

## `describe_cli`

```python
describe_cli(cli: click.Command) -> RouteInfo
```

`create_cli`が返したCLIの記述を返します。commandモジュールはimportしません。それ以外のClickコマンドを渡すと`CliFrameworkError`を送出します。

```python
root = describe_cli(cli)
for route in root.children:
    print(" ".join(route.path), route.help)
    if route.runnable:
        for parameter in route.parameters():   # ここでcommandモジュールを読み込む
            print(" ", parameter.option or parameter.name, parameter.type)
```

## `RouteInfo`

読み取り専用のグループまたは末端コマンドです。

- `name: str`、`path: tuple[str, ...]`: 名前と、ルートCLI名を除く経路。
- `help: str | None`: グループまたはcommandの説明。
- `command_help: str | None`: 直接実行できる場合のcommandの説明。
- `module: str | None`、`file: Path | None`: ソースモジュール名とファイル。
- `runnable: bool`: 直接実行できるか。
- `effect: str | None`: モジュールのトップレベルに文字列リテラルで書かれた`EFFECT`。なければ`None`。
- `children: tuple[RouteInfo, ...]`: 名前順の子。
- `parameters() -> tuple[ParameterInfo, ...]`: 宣言順の引数。commandモジュールを読み込み、定義の不備は`DefinitionError`を送出します。直接実行できないグループでは空です。

## `ParameterInfo`

読み取り専用の引数です。

- `name: str`: Pythonの引数名。
- `type: str`: `"str"`、`"int"`、`"float"`、`"bool"`のいずれか。
- `kind: str`: 位置引数は`"argument"`、Optionは`"option"`。
- `required: bool`、`variadic: bool`、`default`、`help: str | None`。
- `option: str | None`: Option名（`--jobs`）。`negative: str | None`: bool Optionの否定形（`--no-clean`）。

## `current_context`

```python
current_context() -> Context
```

現在実行中の`Context`を返します。管理されたCLI実行の外で呼ぶと`CliFrameworkError`を送出します。

## `Context`

- `bindings: Mapping[str, str]`: 読み取り専用のbinding。
- `state: MutableMapping[str, object]`: 1回の実行内で共有する可変状態。
- `exception: BaseException | None`: teardownから参照できる主例外。
- `json: bool`: 構造化出力のCLIで、この実行に`--json`が指定されたか。それ以外では`False`。
- `get_binding(key: str) -> str`: bindingを取得し、存在しない場合は`CliFrameworkError`を送出します。

Contextは実行ごとに分離され、実行終了後には現在値が復元されます。

## 例外

### `CliFrameworkError`

フレームワークが報告するエラーの基底クラスです。

### `CommandError`

```python
CommandError(code: str, message: str, *, hint: str | None = None)
```

commandが利用者へ報告する失敗です。`code`は機械向け、`message`は人向けです。構造化出力のCLIでは、`--json`の`error`と終了コード1になります。フレームワークの例外ではないため、`CliFrameworkError`を継承しません。

### `DefinitionError`

コマンド構成、シグネチャ、bindingなどの不正を表します。`CliFrameworkError`を継承します。診断には可能な限りソースモジュールや引数名が含まれます。

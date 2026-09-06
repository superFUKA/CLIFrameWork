# 公開API

公開APIは`cli_framework`パッケージ直下からimportします。内部モジュールは互換性契約の対象外です。

## `create_cli`

```python
create_cli(
    command_package: ModuleType,
    *,
    name: str | None = None,
    bindings: Mapping[str, str] | None = None,
    debug: bool = False,
) -> click.Command
```

import済みのコマンドパッケージを走査し、Click互換のルートコマンドを返します。

静的探索・binding・ルート衝突はこの呼び出しで検証します。commandのimportとシグネチャは詳細ヘルプ取得・引数解析時、setup/teardownの定義は実行時に検証します。通常のCLI呼び出しは定義エラーをstderrと終了コード1で報告します。Pythonから`main(..., standalone_mode=False)`で呼ぶ場合は`DefinitionError`を捕捉できます。

- `command_package`: `__path__`を持つimport済みPythonパッケージ。
- `name`: 表示するルートCLI名。省略時はパッケージ名の最後の区間。
- `bindings`: `_name_`形式の経路区間を具体名へ置換する文字列mapping。構築時にコピーされます。
- `debug`: `True`の場合、実行時例外のtracebackをstderrへ表示します。

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

## `current_context`

```python
current_context() -> Context
```

現在実行中の`Context`を返します。管理されたCLI実行の外で呼ぶと`CliFrameworkError`を送出します。

## `Context`

- `bindings: Mapping[str, str]`: 読み取り専用のbinding。
- `state: MutableMapping[str, object]`: 1回の実行内で共有する可変状態。
- `exception: BaseException | None`: teardownから参照できる主例外。
- `get_binding(key: str) -> str`: bindingを取得し、存在しない場合は`CliFrameworkError`を送出します。

Contextは実行ごとに分離され、実行終了後には現在値が復元されます。

## 例外

### `CliFrameworkError`

フレームワークが報告するエラーの基底クラスです。

### `DefinitionError`

コマンド構成、シグネチャ、bindingなどの不正を表します。`CliFrameworkError`を継承します。診断には可能な限りソースモジュールや引数名が含まれます。

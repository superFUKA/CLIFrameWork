# 製品仕様

## 製品目標

Pythonパッケージ内へcommandモジュールを配置することで、階層CLIを定義できる小さなライブラリを提供します。通常、コマンドの追加や削除は対応するモジュールの追加や削除だけで完結し、中央の登録表は管理しません。

主な利用者としてC++アプリケーション開発用ツールの作成者を想定しますが、振る舞いは特定分野に依存させません。

## 開発者体験

次のパッケージ構造があり、

```text
my_tool/commands/
├── __init__.py
└── project/
    ├── __init__.py
    └── build.py
```

次のcommandを定義すると、

```python
from typing import Annotated

def command(
    source: Annotated[str, "入力元"],
    jobs: Annotated[int, "並列数"] = 1,
    clean: Annotated[bool, "先に削除する"] = False,
) -> int | None:
    """プロジェクトをビルドします。"""
```

ライブラリは次のCLIを公開します。

```console
tool project build SOURCE [--jobs INTEGER] [--clean | --no-clean]
```

アプリケーションの組み立ては1か所だけで行います。

```python
from cli_framework import create_cli
from my_tool import commands

cli = create_cli(commands, name="tool", bindings={"_name_": "aaaa"})
```

## コマンドとグループの規則

- トップレベルに`def command`を持つ`.py`モジュールをコマンドとして扱います。
- commandsパッケージ内には、その他の補助モジュールも同居できます。
- コマンドを含むディレクトリはネストしたグループになります。
- グループの説明は`__init__.py`のモジュールdocstringから取得します。
- `__init__.py`に任意の`command`があれば、グループ自体を直接実行できます。
- 自身のcommandを持たないグループの直接実行は用法エラーになりますが、`--help`は利用できます。
- 登録済みの子コマンド名を、直接実行可能なグループの位置引数より優先します。

## 引数の振る舞い

- 対応型は`str`、`int`、`float`、`bool`です。
- デフォルト値のない引数は、必須の位置引数になります。
- デフォルト値のある引数はOptionになります。
- Option名ではPython名のunderscoreをhyphenへ変換します。
- すべてのbool Optionに`--name`と`--no-name`を用意します。
- `--help`は標準ヘルプ用に予約します。肯定・否定を含む生成Option名の重複は、処理を実行する前に定義エラーとして拒否します。
- `Annotated[T, "説明"]`をヘルプ文として使用します。
- docstringと引数説明は省略可能で、省略時に警告しません。
- commandの説明は関数docstringを優先し、未指定ならモジュールdocstringを使います。グループ説明は`__init__.py`のモジュールdocstringです。
- 未対応または曖昧なシグネチャは、そのコマンドの詳細ヘルプ取得・引数解析時に定義エラーにします。ルート構築と親の一覧表示ではcommandをimportしません。

## Bindingの振る舞い

bindingは1つのプレースホルダー区間を1つの文字列へ置換します。

```text
bindings["_name_"] = "aaaa"
commands/_name_/build.py → tool aaaa build
```

- プレースホルダーには`_name_`形式を使います。
- 完全一致だけを置換し、長い名前の一部は置換しません。
- 値は空でない単一のCLIトークンとし、`-`で開始できません。
- binding不足と、解決後の同階層における名前衝突は定義エラーです。
- commandは`current_context().get_binding("_name_")`で値を取得します。
- binding文字列の取得方法と更新方法はフレームワークの対象外です。

## ライフサイクルの振る舞い

各パッケージの`__init__.py`には、任意の同期`setup`関数と`teardown`関数を定義できます。選択したコマンドに対し、setupをルートから末端へ実行し、正常終了した各setupに対応するteardownを逆順に実行します。

generatorおよびasync generator形式のライフサイクル関数は未対応です。各関数の呼び出し直前に定義エラーとして拒否します。setupの定義エラーではcommandを実行せず、既に成功した外側スコープのteardownは実行します。

ヘルプ表示とシェル補完の探索では、ライフサイクル関数を実行しません。teardownは`current_context().exception`を確認できます。アプリケーションはContextのstate、グローバル変数、独自DIなどを選択でき、フレームワークは共有方法を強制しません。

## 戻り値とエラーの振る舞い

- `None`を返すと終了コード0で成功します。
- 整数を返すと、その整数をプロセス終了コードとして使用します。
- `None`と厳密な`int`以外の戻り値（boolを含む）はTypeErrorです。teardownより前に検証し、`current_context().exception`から参照できます。非ゼロの整数を返すこと自体は例外ではありません。
- CLIの用法とルーティングに関するエラーは終了コード2です。
- 未処理のアプリケーションエラーは終了コード1です。
- 通常モードではtracebackを表示せず、簡潔なエラーをstderrへ出力します。
- debugモードでは完全なtracebackを表示します。

## 初版の対象外

初版では、独自パーサー、プロジェクト生成、設定管理、ロギング、DIコンテナ、非同期command、Rich固有表示、独自変換、コレクション引数、追加の引数型を提供しません。

## 製品の受け入れ基準

サンプルアプリケーションを標準的なproject entry pointからインストールでき、手動登録なしで3階層のコマンドを公開できること。各階層で有用なヘルプを表示し、commandからbindingを解決し、定義した順序でライフサイクル処理を行い、Windows、Linux、macOSで規定の終了コードを返すこと。

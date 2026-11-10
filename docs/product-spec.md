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
tool project build SOURCE [--jobs 整数] [--clean | --no-clean]
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
- 通常の引数は、デフォルト値がなければ必須の位置引数になります。
- デフォルト値のある引数はOptionになります。
- 可変長位置引数`*targets: T`は、同じ型の値を0個以上受け取り、関数内ではtupleになります。型注釈`T`は各要素の型です。通常の引数・Optionと併用できます。
- 可変長位置引数の後にデフォルト値のないキーワード専用引数があれば、末尾の値を宣言順にその必須位置引数へ割り当て、残りを可変長位置引数へ渡します。
- `-`で始まる値は`--`の後へ指定できます。可変長位置引数があっても、`--`より前の未知Optionは用法エラーです。
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

## 拡張パッケージの振る舞い

本体とは別の場所にあるcommandパッケージを、本体の任意のグループ配下へ重ねて1つのCLIにできます。

```python
cli = create_cli(commands, extensions=[("file", file_plugin)])
```

```text
commands/file/list.py       → tool file list
file_plugin/copy.py         → tool file copy
file_plugin/sub/move.py     → tool file sub move
```

- 拡張先パスは本体のディレクトリ区間を`/`で区切って指定します。空文字はルートを表します。存在しない区間はグループとして作成します。
- 拡張パッケージの内容は、拡張先ディレクトリ配下に置いた場合と同じ規則でコマンド・グループになります。bindingも同様に適用します。
- 拡張パッケージ直下の`__init__.py`は拡張先グループの定義に統合されます。同じグループの`command`、`setup`、`teardown`は全体で1つまでです。グループ説明は本体を優先し、本体にない場合は拡張パッケージのものを使います。
- 拡張による同階層の名前衝突、同じ定義の重複、本体・拡張パッケージ同士の包含関係や重複指定は定義エラーです。
- 1つの拡張先に複数の拡張パッケージを指定できます。`extensions`には`(拡張先パス, パッケージ)`の組の列、または拡張先パスからパッケージへのmappingを渡します。

## ライフサイクルの振る舞い

各パッケージの`__init__.py`には、任意の同期`setup`関数と`teardown`関数を定義できます。選択したコマンドに対し、setupをルートから末端へ実行し、正常終了した各setupに対応するteardownを逆順に実行します。

generatorおよびasync generator形式のライフサイクル関数は未対応です。各関数の呼び出し直前に定義エラーとして拒否します。setupの定義エラーではcommandを実行せず、既に成功した外側スコープのteardownは実行します。

ヘルプ表示とシェル補完の探索では、ライフサイクル関数を実行しません。teardownは`current_context().exception`を確認できます。アプリケーションはContextのstate、グローバル変数、独自DIなどを選択でき、フレームワークは共有方法を強制しません。

## 戻り値とエラーの振る舞い

構造化出力を有効にしたCLIの戻り値とエラーは「構造化出力」を参照してください。ここでは既定の動作を示します。

- `None`を返すと終了コード0で成功します。
- 整数を返すと、その整数をプロセス終了コードとして使用します。
- `None`と厳密な`int`以外の戻り値（boolを含む）はTypeErrorです。teardownより前に検証し、`current_context().exception`から参照できます。非ゼロの整数を返すこと自体は例外ではありません。
- CLIの用法とルーティングに関するエラーは終了コード2です。
- 未処理のアプリケーションエラーは終了コード1です。
- 通常モードではtracebackを表示せず、簡潔なエラーをstderrへ出力します。
- debugモードでは完全なtracebackを表示します。

## 表示言語

ヘルプの見出し、使い方、型の表示名、既定値のラベル、標準ヘルプの説明は日本語で表示します。引数不足、余分な引数、未知のコマンド・オプション、オプション値の不足、対応型への変換失敗の案内も日本語です。言語設定やOSのロケールによる切り替えは行いません。

公開API名、コマンド名、オプション名、引数名は変更しません。利用者が記述した説明文、入力値、アプリケーション例外の本文、debug時のtracebackは元の内容を保ちます。通常のエラー出力には「エラー:」を付けます。同じプロセス内にあるフレームワーク外のClickコマンドの表示は変更しません。

## CLIの記述の取得

`describe_cli(cli)`は、`create_cli`が返したCLIの記述を、読み取り専用のデータとして返します。コマンド一覧を別の形式で出力する道具や、文書の生成に使います。出力形式そのもの（JSONなど）は提供しません。

- グループと末端コマンドの名前、ルートCLI名を除く経路、説明、ソースモジュール名とファイル、直接実行できるか、子の一覧を取得できます。子は名前順です。
- bindingと拡張パッケージを反映した、解決後のツリーを返します。
- 記述の取得ではcommandモジュールをimportせず、setup・command・teardownも実行しません。
- 各ルートの`parameters()`を呼ぶと、そのcommandモジュールを読み込み、引数を宣言順に返します。引数名、型名（`str`・`int`・`float`・`bool`）、位置引数かOptionか、必須か、可変長か、既定値、説明、Option名と否定形を取得できます。
- 未対応のシグネチャやOption名の衝突は、`parameters()`の呼び出しで定義エラーになります（詳細ヘルプの取得時と同じ）。
- `create_cli`が返したCLI以外を渡すとフレームワークエラーになります。返却後にClickオブジェクトへ加えた変更は反映しません。

## 構造化出力（任意）

`create_cli(..., structured=True)`で、機械（スクリプト・AI・GUI）からも使えるCLIになります。指定しないCLIの動作は変わりません。

```python
# commands/files/add.py
"""ファイルを作ります。"""
from typing import Annotated

EFFECT = "change"


def command(name: Annotated[str, "ファイル名"]) -> dict:
    return {"name": name}


def render(result) -> str:
    return f"{result['name']} を作りました"
```

```console
tool files add a.txt            # a.txt を作りました
tool files add a.txt --json     # {"ok": true, "command": "files add", "result": {"name": "a.txt"}, "error": null}
tool files add --help --json    # このcommandの記述（引数・重さ）
tool --help --json              # コマンド一覧
```

- commandは結果のデータを返します。`None`は結果なし、厳密な`int`は従来どおり終了コード、それ以外（`bool`を含む）は結果です。
- すべての直接実行できるcommandに、Option`--json`を追加します。否定形（`--no-json`）は作りません。
- `--json`を指定した実行では、標準出力の最後の行にJSONを1つ出力します：`{"ok", "command", "result", "error"}`。`command`はルートCLI名を除く経路です。失敗時の`error`は`{"code", "message", "hint"}`です。
  - `CommandError(code, message, hint=None)`：commandが報告する失敗。終了コード1。
  - 用法エラー（引数の不足、未知のコマンドやOption）：`code`は`usage_error`、終了コード2。
  - 定義エラー：`definition_error`、終了コード1。その他の例外：`unexpected`、終了コード1。
  - 非ゼロの`int`を返した場合：`exit_code`、終了コードはその値。
  - JSONへ変換できない結果は`unexpected`です。
- `--json`を指定しない実行では、同じモジュールのトップレベルに`render(result)`があれば、その戻り値（`str`または`None`）を標準出力へ出力します。`render`はcommandの直後、teardownの前に実行します。`render`がなければ結果を表示しません。`CommandError`は標準エラーへ「エラー: …」（`hint`があれば次の行）を出力します。
- `--json`はOption名として予約します。Option`--json`または`--no-json`になる引数は定義エラーです。`json`という名前の位置引数は利用できます。
- commandは`current_context().json`で、`--json`が指定されたかを確認できます。`--json`の実行では、command自身は標準出力へ書き込まないでください。
- 直接実行できるすべてのcommandは、モジュールのトップレベルに重さ`EFFECT`を文字列リテラルで宣言します：`"read"`（何も変えない）・`"change"`（変える）・`"confirm"`（変える前に人の確認が要る）。グループの既定commandは`__init__.py`に書きます。
- `EFFECT`がない、文字列リテラルでない、値が不正、`render`が非同期、のいずれかは、`create_cli`が定義エラーにします（commandをimportせずに検証します）。`render`が結果を1つの位置引数で受け取れない場合は、そのcommandの読み込み時に定義エラーになります。
- `--help`と`--json`を同時に指定すると、その経路の記述をJSONで出力します：`{"ok": true, "command": "help <経路>", "result": <記述>, "error": null}`。記述は`name`・`path`・`help`・`command_help`・`runnable`・`effect`・`parameters`・`commands`（子）で、`parameters`の各要素は`describe_cli`の`ParameterInfo`と同じ項目です。`--json`自身は`parameters`に含めません。グループでは、`--help`と`--json`をコマンド名より前に指定します。

## 初版の対象外

初版では、独自パーサー、プロジェクト生成、設定管理、ロギング、DIコンテナ、非同期command、Rich固有表示、独自変換、`list[T]`などのコレクション型注釈、可変長キーワード引数`**kwargs`、繰り返しOption、追加の引数型を提供しません。

## 製品の受け入れ基準

サンプルアプリケーションを標準的なproject entry pointからインストールでき、手動登録なしで3階層のコマンドを公開できること。各階層で有用なヘルプを表示し、commandからbindingを解決し、定義した順序でライフサイクル処理を行い、Windows、Linux、macOSで規定の終了コードを返すこと。

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

## 機械向けの出力（任意）

`cli_framework.machine`は、スクリプト・AI・GUIなどの機械からCLIを使うための任意の層です。使わないCLIの動作は変わりません。`cli_framework`直下からは公開せず、使うcommandが`cli_framework.machine`からimportします。

```python
from typing import Annotated

from cli_framework.machine import CommandError, respond

EFFECT = "change"


def command(
    name: Annotated[str, "ファイル名"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルを作ります。"""

    def action():
        if not name:
            raise CommandError("invalid_name", "名前を入れてください")
        return {"name": name}

    return respond(action, json=json, render=lambda result: f"{result['name']} を作りました")
```

- `json`は通常の引数として各commandが宣言します。フレームワークがOptionを自動で追加することはありません。
- `respond`はactionを実行し、`json`が真なら標準出力へJSONを1つだけ出力します：`{"ok", "command", "result", "notices", "error"}`。偽なら`render`が返した文字列を出力します。成功で0、`CommandError`で1を返します。commandは、その値をそのまま返します。
- `CommandError(code, message, hint=None)`は利用者へ報告する失敗です。JSONでは`error`の`{"code", "message", "hint"}`、通常の表示では標準エラーの「エラー: …」になります。それ以外の例外は、通常のアプリケーションエラーとして扱います。
- `progress`・`warning`・`notice`は途中の様子を標準エラーへ出力します。`json`が真の実行では、1行1件のJSON（`{"kind", "text"}`。`progress`は任意で`ratio`）です。`notice`の文は結果の`notices`にも入ります。
- commandの重さは、モジュールのトップレベルの定数`EFFECT`で宣言します。`"read"`（何も変えない）・`"change"`（変える）・`"confirm"`（変える前に人の確認が要る）のいずれかです。
- `catalog(cli)`は、コマンド一覧（名前、経路、説明、重さ、引数とOption）をJSONへ変換できるdictで返します。直接実行できるcommandに`EFFECT`がない、または値が不正な場合は定義エラーです。
- `main(cli)`はCLIを実行します。引数に`--help`と`--json`の両方があれば、指定した経路のコマンド一覧をJSONで出力します（`tool --help --json`、`tool files add --help --json`）。`--`より後ろは値として扱います。
- `EFFECT`の検査は一覧の取得時だけ行います。一覧を使わない限り、`EFFECT`のないcommandの実行は変わりません。

## 初版の対象外

初版では、独自パーサー、プロジェクト生成、設定管理、ロギング、DIコンテナ、非同期command、Rich固有表示、独自変換、`list[T]`などのコレクション型注釈、可変長キーワード引数`**kwargs`、繰り返しOption、追加の引数型を提供しません。

## 製品の受け入れ基準

サンプルアプリケーションを標準的なproject entry pointからインストールでき、手動登録なしで3階層のコマンドを公開できること。各階層で有用なヘルプを表示し、commandからbindingを解決し、定義した順序でライフサイクル処理を行い、Windows、Linux、macOSで規定の終了コードを返すこと。

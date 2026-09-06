# 詳細設計

## 公開インターフェース

```python
def create_cli(
    command_package: ModuleType,
    *,
    name: str | None = None,
    bindings: Mapping[str, str] | None = None,
    debug: bool = False,
) -> click.Command: ...

def current_context() -> Context: ...
```

`Context`は次を公開します。

```python
class Context:
    @property
    def bindings(self) -> Mapping[str, str]: ...

    @property
    def state(self) -> MutableMapping[str, object]: ...

    @property
    def exception(self) -> BaseException | None: ...

    def get_binding(self, key: str) -> str: ...
```

CLI作成時にbindingsをコピーし、読み取り専用のmappingにします。`state`は実行ごとに新しく作ります。管理された実行の外で`current_context()`を呼ぶとフレームワークエラーになります。

## ルート探索

入力が利用可能な`__path__`を持つパッケージであることを検証し、Pythonソースを再帰的に走査します。各ファイルを`ast`で解析し、モジュールdocstringとトップレベルの同期関数名を記録します。

- `__init__.py`はディレクトリを説明し、setup、command、teardownを提供できます。
- command関数docstringもASTで取得し、コマンド説明は関数、モジュールの順で採用します。グループ説明はモジュールdocstringです。
- その他の`.py`ファイルは、`command`を定義する場合だけ末端コマンドになります。
- トップレベルの`async def command`、setup、teardownは未対応の定義エラーです。
- importされた`command`という名前だけでは、モジュールをコマンドとして扱いません。
- 構文エラーとソース読み取り失敗には対象パスを含めます。

Clickオブジェクトを構築する前に、結果をルート記述子として表現します。bindingsの解決後、ルートコマンドを公開する前に衝突を検証します。

## Binding解決

区間全体が`^_[A-Za-z][A-Za-z0-9_]*_$`に一致する場合だけプレースホルダーとして認識します。呼び出し側のmappingでは、前後のunderscoreを含む完全なプレースホルダーをキーにします。

発見した各プレースホルダーに文字列値があることを要求します。空文字、空白、NUL、先頭の`-`を拒否します。同じbindingはすべての出現箇所で同じ値へ解決し、元のキーと値のmappingをContextに保持します。

binding置換による同階層の名前衝突を拒否します。これには固定ファイルや固定ディレクトリとの衝突も含みます。呼び出し側が複数のコマンド部分で1つのmappingを共有できるように、ルートツリーで参照されない余分なbindingsは許可します。

## 引数変換

Clickがコマンドの詳細定義を必要としたとき、またはコマンドを実行するときだけcommandモジュールを読み込みます。import後に`inspect.signature()`と`typing.get_type_hints(..., include_extras=True)`を使用します。

各引数を次のように処理します。

- `Annotated[T, text]`を展開し、文字列の説明を最大1つ受け付けます。
- 初版では具体的な`str`、`int`、`float`、`bool`型だけを受け付けます。
- デフォルト値がなければ、必須のClick argumentを作ります。
- デフォルト値があれば、引数名の`_`を`-`へ変換したClick optionを作ります。
- bool Optionには肯定・否定フラグの対を作り、デフォルト値を維持します。
- Click Optionの構築前に全肯定・否定名を集め、予約名`--help`と重複を検証します。診断には衝突名、引数名、ソースを含めます。
- 可変長位置引数、可変長キーワード引数、文字列以外のAnnotatedメタデータ、型注釈の欠落、型と互換性のないデフォルト値を拒否します。

解析値を引数名で元の関数へ渡します。戻り値は`None`または`int`として検証し、実行時にその他の値が返された場合はアプリケーションエラーにします。

## グループ構築

ルート記述子を保持する独自のClick Groupを使用します。固定子とbinding解決済みの子を、決定的な辞書順で一覧表示します。子のヘルプにはcommand docstringの概要、またはディレクトリdocstringを使用し、ライフサイクル処理は実行しません。

ディレクトリ自身にcommandがある場合は、グループのデフォルトコマンドとして扱います。解析時には、完全一致する登録済み子トークンを優先します。それ以外のトークンはデフォルトコマンドの引数として解析できます。デフォルトコマンドがない場合、直接実行はClickの用法エラーになります。

直接実行可能なグループの詳細ヘルプは、そのデフォルトcommandを読み込んで用法・引数・Optionを子一覧と併せて表示します。親の子一覧表示だけでは子commandを読み込みません。ヘルプ中もsetup・command・teardownは実行しません。

## 実行Contextとライフサイクル

実行中のContextを`ContextVar`へ保存します。最初のsetup直前に設定し、`finally`節で元へ戻すことで、連続実行やネストしたテスト実行の間でstateが漏れないようにします。

解決したルートに対して次の順番で処理します。

1. ルートから末端の親までのパッケージスコープを収集します。
2. 定義済みsetupを実行し、正常終了したものだけを記録します。
3. 選択された末端commandまたはグループのデフォルトcommandを実行します。
   戻り値がNoneまたは厳密なintであることを検証し、それ以外はTypeErrorにします。終了コードへの変換はClick側に残します。
4. 発生中の例外をContextへ保存します。
5. 対応するteardownを逆順に実行します。
6. 以前のContextを復元します。

ライフサイクル関数はフレームワーク定義の引数を取らず、戻り値を無視します。teardownも失敗した場合は、元のsetupまたはcommand例外を優先します。それ以前の失敗がなければ最初のteardown例外を主例外とし、後続のteardown例外をnoteまたは例外チェーンへ追加します。

ライフサイクル関数の呼び出し直前にgenerator / async generatorを拒否します。全スコープの事前importは行わず、既存の遅延読み込みと外側スコープの後処理を維持します。

## エラーモデル

フレームワーク例外の基底型と、定義エラーの派生型を公開します。静的探索・binding・ルート衝突の定義エラーは`create_cli()`から送出します。importとシグネチャの検証は詳細取得・引数解析時、ライフサイクル定義の検証は実行時に行います。判明している場合は論理ルートとソース位置を含めます。

返却ルートの通常CLI実行では遅延した定義エラーもstderrと終了コード1へ変換し、debug時はtracebackを表示します。Pythonからの詳細取得、および`main(..., standalone_mode=False)`では`DefinitionError`をそのまま送出します。

用法表示と終了コード2は引き続きClickが担当します。ランタイムアダプターは予期しないアプリケーション例外を簡潔なstderr出力と終了コード1へ変換します。`debug=True`の場合は完全なtracebackを維持します。`KeyboardInterrupt`やプロセス終了用の例外を通常のアプリケーション失敗として捕捉しません。

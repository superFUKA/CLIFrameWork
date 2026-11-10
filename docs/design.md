# 詳細設計

## 公開インターフェース

```python
def create_cli(
    command_package: ModuleType,
    *,
    name: str | None = None,
    bindings: Mapping[str, str] | None = None,
    extensions: Mapping[str, ModuleType]
        | Iterable[tuple[str, ModuleType]]
        | None = None,
    debug: bool = False,
    structured: bool = False,
) -> click.Command: ...

def current_context() -> Context: ...

def describe_cli(cli: click.Command) -> RouteInfo: ...
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

    @property
    def json(self) -> bool: ...

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

## 拡張パッケージの統合

`extensions`の各組について、拡張先パスを`/`で区切った区間列（空文字は空の列）と、import済みパッケージを受け取ります。区間の空文字、先頭の`-`、空白、NULを拒否します。拡張パッケージは本体と同じく`__path__`から静的に探索し、本体・他の拡張パッケージと同名または包含関係にあれば定義エラーにします。

ルート構築では、拡張パッケージ内モジュールの相対区間の前に拡張先の区間を付け、本体と同じルートツリーへ追加します。各ルートの`SourceDescriptor`は拡張パッケージ側のモジュール名を保持するため、遅延importと相対importは拡張パッケージのまま動作します。

1つのグループに複数パッケージの`__init__.py`が対応する場合、`command`、`setup`、`teardown`はそれぞれ最大1つとし、2つ目を定義エラーにします。グループの説明とソースは本体、拡張の指定順で最初のものを使います。名前衝突の検証とbinding解決は統合後のツリーに対して従来どおり行います。

## Binding解決

区間全体が`^_[A-Za-z][A-Za-z0-9_]*_$`に一致する場合だけプレースホルダーとして認識します。呼び出し側のmappingでは、前後のunderscoreを含む完全なプレースホルダーをキーにします。

発見した各プレースホルダーに文字列値があることを要求します。空文字、空白、NUL、先頭の`-`を拒否します。同じbindingはすべての出現箇所で同じ値へ解決し、元のキーと値のmappingをContextに保持します。

binding置換による同階層の名前衝突を拒否します。これには固定ファイルや固定ディレクトリとの衝突も含みます。呼び出し側が複数のコマンド部分で1つのmappingを共有できるように、ルートツリーで参照されない余分なbindingsは許可します。

## 引数変換

Clickがコマンドの詳細定義を必要としたとき、またはコマンドを実行するときだけcommandモジュールを読み込みます。import後に`inspect.signature()`と`typing.get_type_hints(..., include_extras=True)`を使用します。

各引数を次のように処理します。

- `Annotated[T, text]`を展開し、文字列の説明を最大1つ受け付けます。
- 初版では具体的な`str`、`int`、`float`、`bool`型だけを受け付けます。
- 通常の引数は、デフォルト値がなければ必須のClick argumentを作ります。
- デフォルト値があれば、引数名の`_`を`-`へ変換したClick optionを作ります。
- 可変長位置引数`*targets: T`は、要素型`T`を検証し、`nargs=-1, required=False`のClick argumentを作ります。値がない場合は空tupleです。`Annotated[T, text]`も利用できます。
- 引数記述子は`variadic`を保持し、必須かどうかとArgument/Optionの区別を分離します。可変長位置引数はOption名の衝突検証に含めません。
- Pythonの宣言順でCLIの位置引数を配置します。可変長位置引数より後ろの必須キーワード専用引数も固定位置引数になり、Clickが末尾の値を割り当てます。
- bool Optionには肯定・否定フラグの対を作り、デフォルト値を維持します。
- Click Optionの構築前に全肯定・否定名を集め、予約名`--help`と重複を検証します。診断には衝突名、引数名、ソースを含めます。
- 標準ヘルプOptionの内部名はcommand引数名と重複しない名前にします。これにより`help`という位置引数も利用でき、CLI上の`--help`は引き続きヘルプを表示します。
- 可変長キーワード引数、位置専用引数、文字列以外のAnnotatedメタデータ、型注釈の欠落、型と互換性のないデフォルト値を拒否します。

可変長位置引数のない関数へは解析値を引数名で渡します。可変長位置引数のある関数では、Clickアダプターが読み込み時にシグネチャを保持する呼び出しラッパーを作ります。ラッパーは検証済みの解析値から`inspect.BoundArguments`を作り、通常の位置引数、可変長部分、キーワード専用引数を`args` / `kwargs`へ分けて元の関数を呼び出します。可変長部分より前にあるデフォルト付き引数も、Pythonの宣言順に位置引数として渡します。ラッパーは既存のライフサイクル内で実行し、戻り値と例外をそのままランタイムへ返します。

戻り値は`None`または`int`として検証し、実行時にその他の値が返された場合はアプリケーションエラーにします。

## グループ構築

ルート記述子を保持する独自のClick Groupを使用します。固定子とbinding解決済みの子を、決定的な辞書順で一覧表示します。子のヘルプにはcommand docstringの概要、またはディレクトリdocstringを使用し、ライフサイクル処理は実行しません。

ディレクトリ自身にcommandがある場合は、グループのデフォルトコマンドとして扱います。解析時には、完全一致する登録済み子トークンを優先します。それ以外のトークンはデフォルトコマンドの引数として解析できます。デフォルトコマンドがない場合、直接実行はClickの用法エラーになります。

この選択は先頭トークンで行い、可変長位置引数がある場合も同じです。子名そのものをデフォルトcommandの値にするには、先頭に`--`を置きます。必須位置引数がなく可変長位置引数だけの場合は、引数なしでグループを直接実行すると空tupleが渡ります。

デフォルトcommandの解析へ切り替える際は、位置引数とOptionの混在も通常のClick commandと同じ規則にします。値の後の`--jobs`や`--help`をOptionとして扱い、`--`の後だけを値として扱います。

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

## CLIの記述

```python
@dataclass(frozen=True, slots=True)
class RouteInfo:
    name: str
    path: tuple[str, ...]          # ルートCLI名を除く経路
    help: str | None               # グループまたはcommandの説明
    command_help: str | None       # 直接実行できる場合のcommandの説明
    module: str | None
    file: Path | None
    runnable: bool
    effect: str | None             # トップレベルの EFFECT（文字列リテラルのとき）
    children: tuple[RouteInfo, ...]

    def parameters(self) -> tuple[ParameterInfo, ...]: ...

@dataclass(frozen=True, slots=True)
class ParameterInfo:
    name: str                      # Pythonの引数名
    type: str                      # "str" | "int" | "float" | "bool"
    kind: str                      # "argument" | "option"
    required: bool
    variadic: bool
    default: str | int | float | bool | None
    help: str | None
    option: str | None             # "--name"
    negative: str | None           # "--no-name"（bool Optionだけ）
```

`describe_cli`は、ルートのClickグループが保持する解決済みのルート記述子を`RouteInfo`へ変換します。`create_cli`が構築したグループでなければ`CliFrameworkError`にします。変換は記述子だけを読み、commandモジュールをimportしません。子は名前順（Clickの一覧と同じ）です。

グループの`module`と`file`は`__init__.py`を指し、`__init__.py`を持たないグループでは`None`です。`command_help`は末端コマンドでは`help`と同じ、既定commandのないグループでは`None`です。

`parameters()`は、Clickコマンドの構築時と同じ手順（遅延読み込み、引数の検査、Option名の衝突検証）を実行し、中立な引数記述子を`ParameterInfo`へ変換します。Option名はClickアダプターと同じ規則（underscoreをhyphenへ、boolは否定形を追加）で求めます。直接実行できないグループでは空tupleを返します。

`RouteInfo`と`ParameterInfo`はClickの型を含みません。返却後にClickオブジェクトへ加えた変更（非表示やOption名の書き換え）は反映しません。

## 構造化出力

`structured=True`の処理は、既定の経路と分けて実装します。指定しない場合、追加の検証・Option・出力は行いません。

**探索**：`discovery`は、各モジュールのトップレベルの`EFFECT`への代入（値が文字列リテラルならその値、それ以外は位置だけ）と、`render`関数（位置と、非同期かどうか）を`ModuleScan`へ記録します。この段階では拒否しません。`routes`は、それらを`CommandDescriptor`の`effect`・`effect_source`・`render`・`render_async`へ写します。

**検証**：`create_cli`は、binding解決後のツリーに対して`structured.validate_structured`を実行し、直接実行できる全commandの`EFFECT`と`render`を検証します。commandモジュールはimportしません。

**Option**：`build_click_command`は、引数記述子に`--json`のフラグを追加します。内部の引数名は、利用者の引数名と重複しない名前（`json`、重複すれば`_json`…）にします。Option名の衝突検証（`parameters.validate_option_names`）は、`--help`に加えて`--json`を予約済みとして扱います。

**実行**：`_invoke_structured`は、`run_with_lifecycle(..., allow_data=True, json=…)`でcommandを実行します。`allow_data`は戻り値の型検証を省き、`json`は`Context.json`になります。`render`は、commandを包む関数の中で呼び出し、teardownより前に出力します。`render`がないcommandでは、同じ位置で`structured.default_text`（文字列はそのまま、`None`は出力なし、それ以外は字下げしたJSON）を使います。`--json`の実行では、ライフサイクルの完了後に`{"ok", "command", "result", "error"}`を1行で出力します。`CommandError`・`DefinitionError`・その他の例外・非ゼロの`int`・変換できない結果は、製品仕様の`code`で失敗のJSONにします。`debug=True`では、その他の例外のtracebackを標準エラーへ出力します。

**用法エラー**：ルートの`RouteGroup.main`は、`--`より前の引数に`--json`があるかを記録します。Clickの用法例外を表示する処理（`JapaneseCommandMixin.show_error`）をルートで差し替え、記録があれば日本語の本文を`usage_error`のJSONとして標準出力へ出力します。終了コードはClickの値（2）のままです。ルート実行で捕捉する`DefinitionError`も同様に`definition_error`のJSONにします。

**記述の出力**：末端commandは`parse_args`の先頭で、Clickの解析器を使って`--help`と`--json`の両方が指定されたかを判定します（Optionの値として渡された同じ文字を除くため）。グループは、コマンド名より前に並ぶOptionだけを見ます。該当すれば、`describe_route`の記述を`description.catalog_node`でdictへ変換し、`{"ok": true, "command": "help <経路>", …}`を出力して終了コード0で終了します。

Option名の衝突検証は、Clickへ依存しない`parameters.validate_option_names`へ移しました。Clickアダプターと`RouteInfo.parameters()`が同じ関数を使います。

## エラーモデル

フレームワーク例外の基底型と、定義エラーの派生型を公開します。静的探索・binding・ルート衝突の定義エラーは`create_cli()`から送出します。importとシグネチャの検証は詳細取得・引数解析時、ライフサイクル定義の検証は実行時に行います。判明している場合は論理ルートとソース位置を含めます。

返却ルートの通常CLI実行では遅延した定義エラーもstderrと終了コード1へ変換し、debug時はtracebackを表示します。Pythonからの詳細取得、および`main(..., standalone_mode=False)`では`DefinitionError`をそのまま送出します。

用法表示と終了コード2は引き続きClickが担当します。ランタイムアダプターは予期しないアプリケーション例外を簡潔なstderr出力と終了コード1へ変換します。`debug=True`の場合は完全なtracebackを維持します。`KeyboardInterrupt`やプロセス終了用の例外を通常のアプリケーション失敗として捕捉しません。

## 日本語表示

Clickアダプター内の`click_localization.py`に表示の処理をまとめます。専用ContextとHelpFormatterで見出しと用法を表示し、生成するOptionで型表示名と既定値のラベルを指定します。利用者の説明文全体に対する文字列置換は行いません。

CLIの入口ではClickの非standalone実行を利用し、用法例外の構造化された引数情報から日本語の案内を生成します。構造化情報がない標準診断はメッセージ全体のパターンに一致するときだけ変換し、未知の診断は原文を保ちます。解析・補完・終了コードの判定はClickに委ね、`standalone_mode=False`では元のClick例外を呼び出し側へ送出します。グローバルなgettextやClickのクラスを差し替えません。

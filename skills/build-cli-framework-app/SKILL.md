---
name: build-cli-framework-app
description: cli_framework（CLIFrameWorkリポジトリ）のcreate_cliを使って階層CLIアプリを作成・拡張し、パッケージ化と動作テストを行う。コマンド追加、binding、setup/teardownの利用に適用する。フレームワーク内部の開発や一般的なClickアプリの依頼には適用しない。
---

# CLI Frameworkでアプリを作る

利用者のアプリを実装する。フレームワーク本体の変更や、別のCLIライブラリへの置換は依頼がない限り行わない。

## 開始時の確認

- 対象アプリのAGENTS.md、pyproject.toml、既存CLI入口とテストを確認する。既存の構成・依存管理を優先する。
- 利用する`cli_framework`の入手元とバージョンを確認する。このプロジェクトの配布名は`cli-framework`だが、同名の公開レジストリ製品を同一物と仮定しない。信頼できるチェックアウトまたはwheelからインストールする。入手元がなければ利用者に確認する。
- フレームワークのソースが利用可能なら、その`docs/api.md`、`docs/getting-started.md`を読む。境界条件の変更時だけ`docs/product-spec.md`と`docs/design.md`を参照する。移植先に元リポジトリがあるとは仮定しない。
- 新規アプリの具体例が必要なら[starter.md](references/starter.md)を読む。

## コマンドの実装

- 公開APIは`from cli_framework import create_cli, current_context`などパッケージ直下から使う。内部モジュールをimportしない。
- import可能なcommandsパッケージを作り、1つの組み立て場所で`create_cli(commands, name=...)`を呼ぶ。独自の登録表やClickデコレーターは必要ない。
- 通常のモジュールのトップレベル`def command`が末端コマンド、サブパッケージがグループになる。グループ`__init__.py`のcommandは既定処理。固定名の子コマンドは既定処理の位置引数より優先される。
- commandは同期の通常関数にする。引数は`str`、`int`、`float`、`bool`のみ。Path等が必要なら文字列で受け、関数本体で変換する。Optional、Enum、Literal、コレクション、可変長・位置専用引数は使用しない。
- 既定値なしは必須位置引数、既定値ありはOption。既定値の型は注釈と厳密に合わせる（`int = None`や`int = False`は不可）。説明は`Annotated[T, "説明"]`、コマンド説明は関数docstringへ置く。
- Optionの`_`は`-`に変換される。boolは`--name`と`--no-name`の対になる。`--help`を生成するhelp Optionは作らない。全Optionの肯定・否定名を比較し、`clean`と`no_clean`のような衝突を避ける。位置引数のhelpという名前まで一律に禁止しない。
- 戻り値はNoneまたは厳密なintとする。boolや文字列を返さない。利用者入力エラーや例外の扱いはアプリの契約に合わせる。
- import時にはファイル更新、外部コマンド、通信、Context取得を行わない。詳細ヘルプがcommandモジュールをimportするため、実処理はcommand/setupへ置く。

## 必要な場合だけ使う機能

- Binding：`_project_`等の経路区間全体を、`bindings={"_project_": "alpha"}`で構築時に置換する。実行時の自由な位置引数ではない。空白・NUL・先頭ハイフン・空文字・同階層の名前衝突を避ける。
- Lifecycle：グループのsetup/teardownは引数なしの同期通常関数。generator、async generator、contextmanagerデコレーターは使わない。setupは外から内、teardownは逆順。失敗したsetupのスコープのteardownを当てにせず、そのsetup内で部分取得リソースを片付ける。
- Context：実行中だけ`current_context()`を呼び、共有値はstate、binding参照はget_bindingへ。不正な戻り値も失敗としてteardownからexceptionで観測できる版を用いる。非ゼロintの返却自体は例外ではないので、exceptionだけを終了コードの成否判定に使わない。

## 検証と引き渡し

- pytestとClickのCliRunnerでstdout、stderr、終了コードを個別に検証する。最低Click版も扱う場合はstarterのrunner互換例を使う。
- 正常系・用法エラー・アプリ例外に加え、ルート/グループ/末端の`--help`でsetup・command・teardownが実行されないことをイベント記録等で確かめる。副作用を伴う実処理はテストで差し替える。
- bindingやライフサイクルを追加した場合だけ、それぞれの置換と実行順・失敗時後処理をテストする。
- インストールしたアプリのconsole entry pointと`python -m アプリ名`を確認する。ソースのsys.path追加だけでインストール成功を代用しない。
- 実行環境と成功/未実施のチェックを報告する。最低Python/Click版の検証を現在環境の成功から推定しない。利用者の公開・ライセンス方針を保持し、生成物や秘密情報をコミットへ混ぜない。

# 開発ガイド

## ディレクトリ

| 場所 | 内容 |
| --- | --- |
| `src/cli_framework/` | ライブラリ本体 |
| `tests/` | 単体・結合・受け入れテスト |
| `tests/fixtures/` | テスト用パッケージ生成器とClick互換ヘルパー |
| `examples/example_app/` | インストール可能なサンプル |
| `scripts/` | 配布物の検証スクリプト |
| `docs/` | 利用・開発ガイドと仕様・設計 |
| `.github/workflows/` | CI設定 |
| `.review-work/` | ローカル検証の一時ファイル・配布物（Git対象外） |
| `.review-work/notes/` | 個人的なタスク・調査メモ・作業履歴（Git対象外、再生成できない記録は必要に応じて別途バックアップ） |

## 環境の準備

リポジトリのルートで `python -m venv .venv` を実行します。
Windows PowerShellでは `.\.venv\Scripts\Activate.ps1`、macOS/Linuxでは
`source .venv/bin/activate` で有効にします。

```console
python -m pip install -e ".[dev]"
python scripts/dev.py test
python scripts/dev.py package-check
```

## 検証の入口

ローカルとCIは同じ`python scripts/dev.py`を使います。testは毎回新しい一時領域を使い、既存pytestキャッシュに依存しません。

```console
python scripts/dev.py test
python scripts/dev.py test tests/test_public_api.py -q
python scripts/dev.py lint
python scripts/dev.py check
```

checkはlintと全pytestを順に実行し、失敗した場合は非ゼロで終了します。

## 配布物の検証

```console
python scripts/dev.py package-check
```

新しい作業先でsdistからwheelを生成し、隔離venvへ本体とサンプルをインストールして
console entry pointと`python -m example_cli`を確認します。

成果物は表示された`.review-work/distribution-*/wheels/`へ保存します。
過去の作業ファイルは`.review-work/archive/`へ移して保管できます。
`.venv/`は開発環境、`dist/`は通常のビルド出力であり、一時テスト結果と区別します。

## 作業の進め方

ローカルの`.review-work/notes/tasks.md`へ依頼のタスクを記録し、未完了タスクを1件ずつ扱い、関連テストの成功後に結果を記録します。新しいチェックアウトにはこのファイルはありません。必要になった時点で作成します。
仕様は[製品仕様](product-spec.md)と[詳細設計](design.md)、コンポーネント境界は[アーキテクチャ](../ARCHITECTURE.md)を参照してください。
個人利用のためライセンスは設定していません。

## 情報の置き場所

| 情報 | 正式な置き場所 | 更新のタイミング |
| --- | --- | --- |
| 利用者の振る舞い | `docs/product-spec.md` | 振る舞いを変更するとき |
| API・アルゴリズム | `docs/design.md` | 契約や境界条件を変更するとき |
| コンポーネント境界 | `ARCHITECTURE.md` | 責務や依存方向を変更するとき |
| 個人的な作業・未解決事項 | `.review-work/notes/tasks.md` | 着手時と検証後。Git対象外 |
| 過去の作業結果・計画 | `.review-work/notes/` | ローカルの履歴として保持。Git対象外 |
| AI共通の規約 | `AGENTS.md` | 開発方法を変更するとき |
| 再生成できる成果物 | `.review-work/` | 検証時に生成。Gitへ入れない |

同じ要件を複数の文書へ転載せず、必要な場所へリンクします。検証結果には環境・実行コマンド・成功/未実施を区別して記録します。過去の記録を現在の指示として読み込ませません。

整理の参考：HumanLayerの[Writing a good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md)から、入口を短くして詳細を必要時に参照する方針を採用しました。[IgniteUIの実例](https://github.com/IgniteUI/ai-repo-structure)の役割別分離も参考にし、個人開発に不要な複数ツール用フォルダーは追加していません。

### このプロジェクトで採用する構成

```text
CLIToolTemplate/
  README.md                 利用開始と文書への入口
  AGENTS.md                 AIの共通規約と参照先
  ARCHITECTURE.md            本体の責務・依存方向
  pyproject.toml            配布・依存・検証設定
  MANIFEST.in               sdistへ含めるファイル
  src/cli_framework/        ライブラリ本体
  tests/                   コンポーネント別テスト
    fixtures/              共通生成器・テストヘルパー
  examples/example_app/    独立してインストールするサンプル
  scripts/                 開発・配布の検証入口
  docs/                    現行の仕様・設計・利用/開発ガイド
  .github/workflows/       CI
  .review-work/            ローカル作業領域（Git対象外）
    notes/                 個人的なタスク・調査メモ・履歴
```

[Click向けテンプレート](https://github.com/sgraaf/cookiecutter-python-cli-app)のCLI・テスト・開発自動化の分離を参考にしています。本体は小規模な単一ライブラリなので、新しいpackages/やservices/階層は作りません。testsも現在の規模ではコンポーネント名で探せる平坦な配置を維持します。独立配布を検証するexamplesのpyproject.tomlは重複ではなく必要な設定です。

ルートには入口と設定を置き、継続して管理する仕様・設計・ガイドはdocsへ置きます。個人的なタスク・履歴はGit除外済みの`.review-work/notes/`へ置き、配布処理の入力にしません。恒久的な仕様・設計判断はdocsなどの正式な情報源へ反映します。生成物はソースと別管理にし、notesを含む作業領域全体を一括削除しません。

### コミットへの混入を防ぐ

一時ファイルはルートやdocsへ作らず、`.review-work/`へ集約します。フォルダーを移すだけではGit除外になりません。新しい保存先は`git check-ignore -v -- パス`で確認します。既に追跡されているファイルには.gitignoreは効きません。

コミット前に以下で候補とステージ済み差分を確認します。追加時は対象のファイルやディレクトリを明示し、除外を無視する`git add -f`は使いません。

```console
git status --short --untracked-files=all
git diff
git diff --cached --stat
git diff --cached
```

## トラブルシューティング

- 仮想環境を有効にできないWindows環境では、`python`を`.\.venv\Scripts\python.exe`に置き換えます。
- オフラインでは`python scripts/dev.py package-check --offline`を使えます。現在インストール済みのClickなどを再利用するため、最低依存版の検証ではありません。
- 権限エラーが残る既存`.pytest_cache/`や`dist/`は新しい検証では使いません。所有者・ACLは自動変更しません。

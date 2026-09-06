# CLI Framework

Pythonパッケージのディレクトリ構造から、Click互換の階層CLIを構築するフレームワークです。コマンド一覧を別の設定ファイルへ重複して記述する必要はありません。

## 対応環境

- Python 3.10以上
- Click 8.1以上、9未満
- Windows、macOS、Linux

対応するPythonとOSの組み合わせはCIで継続的に検証します。詳細は[対応方針](docs/compatibility.md)を参照してください。

## インストール

```console
python -m pip install .
```

## 最小例

次のPythonパッケージを用意します。

```text
my_app/
    __init__.py
    cli.py
    commands/
        __init__.py
        status.py
        project/
            __init__.py
            build.py
```

`commands/project/build.py`に通常のPython関数を書きます。

```python
from typing import Annotated


def command(
    source: Annotated[str, "入力元"],
    jobs: Annotated[int, "並列数"] = 1,
    clean: Annotated[bool, "事前に削除する"] = False,
) -> int:
    print(f"build {source}: jobs={jobs}, clean={clean}")
    return 0
```

`my_app/cli.py`でCLIを構築します。

```python
from cli_framework import create_cli

from . import commands


cli = create_cli(commands, name="my-tool")

if __name__ == "__main__":
    cli()
```

ディレクトリ階層がそのままコマンド階層になります。

```console
python -m my_app.cli project build src --jobs 4 --clean
python -m my_app.cli project build --help
```

詳しい作り方は[利用ガイド](docs/getting-started.md)、公開インターフェースは[APIリファレンス](docs/api.md)を参照してください。実行可能な完全例は[`examples/example_app`](examples/example_app)にあります。

## 開発

個人利用を前提とし、公開パッケージレジストリへの配布やライセンス設定は行っていません。
リポジトリのルートで仮想環境を作ります。

```console
python -m venv .venv
```

Windows PowerShellでは `.\.venv\Scripts\Activate.ps1`、macOS/Linuxでは
`source .venv/bin/activate` で有効にしてから実行します。

```console
python -m pip install -e ".[dev]"
python scripts/dev.py test
python scripts/dev.py package-check
```

最後のコマンドは新しい作業領域でsdistとwheelを作り、隔離したvenvへ本体とサンプルをインストールして動作を確認します。
環境の制約がある場合の手順は開発ガイドのトラブルシューティングを参照してください。
生成物と個人的な作業記録はGit対象外の`.review-work/`へ残します。ディレクトリ構成、コミット前の確認方法、既存キャッシュにアクセスできない場合の手順は[開発ガイド](docs/development.md)を参照してください。

製品仕様は[product-spec.md](docs/product-spec.md)、内部構造は[ARCHITECTURE.md](ARCHITECTURE.md)に分離しています。

## CLIアプリ作成用スキル

[build-cli-framework-app](skills/build-cli-framework-app/SKILL.md)は、このフレームワークを使うアプリの実装・テストを支援するCodexスキルです。`skills/`は配布元であり、自動インストール先ではありません。

利用するには`skills/build-cli-framework-app`フォルダー全体を、ユーザー共通の`$CODEX_HOME/skills/`（未設定の場合は`%USERPROFILE%\.codex\skills\`）へコピーします。同名スキルがあれば上書き前に内容を比較してください。Codexを再起動し、`$build-cli-framework-app このフレームワークでCLIツールを作ってください`と依頼します。

# 対応環境

## 公開する範囲

- Python 3.10以上
- Click 8.1以上、9未満
- Windows、macOS、Linux

パッケージメタデータの`requires-python`と依存範囲がインストール時の判定基準です。特定OSだけのシェル機能やパス表現を公開動作には使用しません。

## 継続的な検証

GitHub Actionsの設定はWindows、macOS、Linuxの各OSについて、Python 3.10、3.11、3.12、3.13、3.14の全pytestスイートを対象にしています。Python 3.10とClick 8.1.0の最低依存ジョブも設けています。配布検証ジョブは3つのOSのPython 3.10でsdistからwheelを構築し、隔離venvへ本体とサンプルをインストールしてentry pointを実行します。

これは検証対象の設定であり、リモートCIの成功実績を示すものではありません。各環境の検証結果は対応するCI実行ログで確認してください。個人的な実行結果や未検証項目はローカルの`.review-work/notes/`へ記録し、対応済みという主張と区別します。

Click 8.1のCliRunnerでは`mix_stderr=False`を指定し、引数が廃止された新しいClickでは指定せず、stdout/stderrを個別に検証します。

Pythonの新しい安定版はCI行列へ追加してから検証済みとします。サポート中のPythonで問題が再現した場合は、OS、Python、Clickの各バージョンと最小再現例を添えて報告してください。

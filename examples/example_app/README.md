# cli-framework サンプル

リポジトリのルートでフレームワークをインストールした後、このディレクトリを
インストールします。

```console
python -m pip install -e .
python -m pip install -e examples/example_app
example-cli --help
example-cli demo --target overview
example-cli demo release build src --jobs 2 --clean
```

`commands/_project_/release/build.py`という配置が
`demo release build`という階層へ変換されます。`_project_`には
`example_cli/cli.py`でbindingを与えています。

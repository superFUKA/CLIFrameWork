"""Keep stdout/stderr assertions identical across supported Click versions."""
import inspect

from click.testing import CliRunner as _CliRunner


def CliRunner() -> _CliRunner:
    if "mix_stderr" in inspect.signature(_CliRunner).parameters:
        return _CliRunner(mix_stderr=False)
    return _CliRunner()

from __future__ import annotations

import cli_framework


def test_package_can_be_imported() -> None:
    assert cli_framework.__name__ == "cli_framework"

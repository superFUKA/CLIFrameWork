from __future__ import annotations

from types import MappingProxyType

import pytest

from cli_framework import current_context
from cli_framework.context import _activate_context
from cli_framework.errors import CliFrameworkError


def test_current_context_is_unavailable_outside_managed_execution() -> None:
    with pytest.raises(CliFrameworkError, match="実行の外"):
        current_context()


def test_bindings_are_copied_and_read_only() -> None:
    original = {"_name_": "alpha"}

    with _activate_context(original) as context:
        original["_name_"] = "changed"

        assert context.bindings == {"_name_": "alpha"}
        assert isinstance(context.bindings, MappingProxyType)
        with pytest.raises(TypeError):
            context.bindings["_name_"] = "blocked"  # type: ignore[index]


def test_get_binding_returns_value_and_reports_missing_key() -> None:
    with _activate_context({"_name_": "alpha"}) as context:
        assert context.get_binding("_name_") == "alpha"
        with pytest.raises(CliFrameworkError, match="_missing_"):
            context.get_binding("_missing_")


def test_state_is_mutable_within_one_execution() -> None:
    with _activate_context({}) as context:
        context.state["events"] = ["setup"]
        current_context().state["ready"] = True

        assert context.state == {"events": ["setup"], "ready": True}


def test_exception_reference_is_read_only_to_users() -> None:
    failure = RuntimeError("broken")

    with _activate_context({}) as context:
        assert context.exception is None
        context._set_exception(failure)

        assert current_context().exception is failure
        with pytest.raises(AttributeError):
            context.exception = None  # type: ignore[misc]


def test_sequential_executions_have_isolated_state_and_exception() -> None:
    failure = ValueError("first")
    with _activate_context({}) as first:
        first.state["value"] = 1
        first._set_exception(failure)

    with _activate_context({}) as second:
        assert second is not first
        assert second.state == {}
        assert second.exception is None


def test_nested_execution_restores_previous_context() -> None:
    with _activate_context({"scope": "outer"}) as outer:
        outer.state["value"] = "kept"

        with _activate_context({"scope": "inner"}) as inner:
            assert current_context() is inner
            assert inner.get_binding("scope") == "inner"
            assert inner.state == {}

        assert current_context() is outer
        assert outer.get_binding("scope") == "outer"
        assert outer.state == {"value": "kept"}

    with pytest.raises(CliFrameworkError):
        current_context()


def test_context_is_restored_when_managed_body_fails() -> None:
    with pytest.raises(RuntimeError, match="failure"):
        with _activate_context({}):
            raise RuntimeError("failure")

    with pytest.raises(CliFrameworkError, match="実行の外"):
        current_context()

"""Runbook registry: built-in auto-discovery, entry-point plugins, path loading."""

import sys
import types

import pytest
from pydantic import BaseModel

from junior.runbook import registry
from junior.runbook.base import Runbook


class _Ctx(BaseModel):
    pass


class _Res(BaseModel):
    pass


def _make_runbook(pname: str) -> type[Runbook]:
    class _P(Runbook):
        name = pname
        context_model = _Ctx
        result_model = _Res

        def collect(self, settings):
            return _Ctx()

        def render(self, ctx, settings, *, file_access):
            return ""

        def publish(self, settings, result, usage, *, errors, publish_enabled):
            pass

    return _P


def test_builtin_code_review_is_autodiscovered():
    assert registry.get_runbook("local_review").name == "local_review"


def test_unknown_name_lists_known():
    with pytest.raises(ValueError, match="unknown runbook 'nope'.*local_review"):
        registry.get_runbook("nope")


def test_load_by_module_path():
    mod = types.ModuleType("_ext_pipe_test")
    mod.MyReview = _make_runbook("ext_review")
    sys.modules["_ext_pipe_test"] = mod
    try:
        assert registry.get_runbook("_ext_pipe_test:MyReview").name == "ext_review"
    finally:
        del sys.modules["_ext_pipe_test"]


def test_bad_module_path_raises():
    with pytest.raises(ValueError, match="cannot load runbook"):
        registry.get_runbook("no_such_module:Nope")


def test_path_to_non_runbook_raises():
    mod = types.ModuleType("_ext_bad_test")
    mod.NotARunbook = dict
    sys.modules["_ext_bad_test"] = mod
    try:
        with pytest.raises(ValueError, match="not a Runbook subclass"):
            registry.get_runbook("_ext_bad_test:NotARunbook")
    finally:
        del sys.modules["_ext_bad_test"]


def test_entry_point_plugin_is_registered(monkeypatch):
    # ensure built-ins are present, then work on a copy so the plugin doesn't leak
    import junior.runbooks.code_review  # noqa: F401  (idempotent)

    monkeypatch.setattr(registry, "_RUNBOOKS", dict(registry._RUNBOOKS))
    monkeypatch.setattr(registry, "_discovered", False)

    plugin_cls = _make_runbook("plugin_review")

    class _FakeEP:
        name = "plugin_review"

        def load(self):
            return plugin_cls

    monkeypatch.setattr(registry, "entry_points", lambda group: [_FakeEP()])

    assert registry.get_runbook("plugin_review").name == "plugin_review"

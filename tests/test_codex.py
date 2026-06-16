"""Tests for codex backend helpers."""

import os

import pytest

from junior.config import Settings
from junior.harnesses import codex
from junior.harnesses.codex import HARNESS, _build_output_schema, _parse_token_usage
from junior.runbooks.code_review.models import ReviewOutput


def test_output_schema_is_strict():
    schema = _build_output_schema(ReviewOutput)

    assert schema["type"] == "object"
    assert set(schema["required"]) == {"summary", "recommendation", "comments"}
    assert schema["additionalProperties"] is False


def test_parse_token_usage_reads_count_after_marker():
    stderr = "working...\ntokens used\n22,476\n"

    assert _parse_token_usage(stderr) == 22476


def test_parse_token_usage_ignores_unrelated_trailing_digits():
    stderr = "warning: codex 0.1.15\npid 12345\n"

    assert _parse_token_usage(stderr) == 0


def test_parse_token_usage_rejects_malformed_marker_value():
    stderr = "tokens used\ncodex 0.1.15\n"

    assert _parse_token_usage(stderr) == 0


def test_complete_cleans_up_temp_files_when_schema_build_fails(monkeypatch):
    """A failing schema build must not leak the NamedTemporaryFile on disk."""
    created: list[str] = []
    real_unlink = os.unlink
    unlinked: list[str] = []
    monkeypatch.setattr(codex, "_ensure_codex_auth", lambda settings: None)

    def boom(_schema):
        raise RuntimeError("openai not installed")

    monkeypatch.setattr(codex, "_build_output_schema", boom)

    real_ntf = codex.tempfile.NamedTemporaryFile

    def tracking_ntf(*args, **kwargs):
        handle = real_ntf(*args, **kwargs)
        created.append(handle.name)
        return handle

    monkeypatch.setattr(codex.tempfile, "NamedTemporaryFile", tracking_ntf)
    monkeypatch.setattr(codex.os, "unlink", lambda p: (unlinked.append(p), real_unlink(p)))

    with pytest.raises(RuntimeError, match="openai not installed"):
        HARNESS.complete(
            system_prompt="sys",
            user_message="msg",
            output_schema=ReviewOutput,
            settings=Settings(),
        )

    # The one temp file that was opened got unlinked — nothing left behind.
    assert created
    for name in created:
        assert name in unlinked
        assert not os.path.exists(name)

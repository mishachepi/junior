"""Tests for codex backend helpers."""

from junior.harnesses.codex import _build_output_schema, _parse_token_usage
from junior.models import LLMReviewOutput


def test_output_schema_is_strict():
    schema = _build_output_schema(LLMReviewOutput)

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

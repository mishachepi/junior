"""Tests for prompt_loader: inline texts + file:// URI resolution."""

import tempfile
from pathlib import Path

import pytest

from junior.prompt_loader import Prompt, load_prompts, parse_prompt_file


def test_load_prompts_wraps_inline_texts():
    prompts = load_prompts(["Check security", "Look at logic"])
    assert len(prompts) == 2
    assert prompts[0].name == "inline_1"
    assert prompts[0].body == "Check security"
    assert prompts[1].name == "inline_2"
    assert prompts[1].body == "Look at logic"


def test_load_prompts_skips_blank_inline():
    prompts = load_prompts(["", "  ", "real one"])
    assert len(prompts) == 1
    assert prompts[0].body == "real one"


def test_load_prompts_reads_file_uri(tmp_path):
    f = tmp_path / "custom.md"
    f.write_text("---\nname: custom\ndescription: X\n---\nBody here\n")
    prompts = load_prompts([f"file://{f}"])
    assert len(prompts) == 1
    assert prompts[0].name == "custom"
    assert prompts[0].body == "Body here"


def test_load_prompts_mixed_inline_and_file(tmp_path):
    f = tmp_path / "sec.md"
    f.write_text("Security body")
    prompts = load_prompts(["Inline first", f"file://{f}"])
    assert [p.name for p in prompts] == ["inline_1", "sec"]
    assert prompts[1].body == "Security body"


def test_load_prompts_rejects_missing_uri():
    with pytest.raises(ValueError, match="not found"):
        load_prompts(["file:///nonexistent/path.md"])


def test_load_prompts_rejects_non_md(tmp_path):
    f = tmp_path / "not_markdown.txt"
    f.write_text("body")
    with pytest.raises(ValueError, match="must be .md"):
        load_prompts([f"file://{f}"])


def test_parse_prompt_file_with_frontmatter():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\nname: test_prompt\ndescription: A test\n---\n\nHello body\n")
        f.flush()
        prompt = parse_prompt_file(Path(f.name))

    assert isinstance(prompt, Prompt)
    assert prompt.name == "test_prompt"
    assert prompt.description == "A test"
    assert prompt.body == "Hello body"


def test_parse_prompt_file_without_frontmatter():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("Just a plain prompt body\n")
        f.flush()
        prompt = parse_prompt_file(Path(f.name))

    assert prompt.name == f.name.split("/")[-1].replace(".md", "")
    assert prompt.body == "Just a plain prompt body"
    assert prompt.description == ""

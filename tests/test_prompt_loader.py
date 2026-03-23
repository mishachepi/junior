"""Tests for prompt_loader: discover, load, parse."""

import tempfile
from pathlib import Path

import pytest

from junior.prompt_loader import Prompt, discover_prompts, load_prompts, parse_prompt_file


def test_discover_finds_all_builtin_prompts():
    prompts = discover_prompts()
    assert "security" in prompts
    assert "logic" in prompts
    assert "design" in prompts
    assert "common" in prompts


def test_discover_returns_prompt_objects():
    prompts = discover_prompts()
    p = prompts["security"]
    assert isinstance(p, Prompt)
    assert p.name == "security"
    assert len(p.body) > 0
    assert len(p.description) > 0


def test_load_prompts_by_name():
    prompts = load_prompts(["security", "logic"])
    assert len(prompts) == 2
    assert prompts[0].name == "security"
    assert prompts[1].name == "logic"


def test_load_prompts_strips_whitespace():
    prompts = load_prompts([" security ", "logic"])
    assert prompts[0].name == "security"


def test_load_prompts_unknown_raises():
    with pytest.raises(ValueError, match="Unknown prompt 'nonexistent'"):
        load_prompts(["nonexistent"])


def test_parse_prompt_file_with_frontmatter():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\nname: test_prompt\ndescription: A test\n---\n\nHello body\n")
        f.flush()
        prompt = parse_prompt_file(Path(f.name))

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

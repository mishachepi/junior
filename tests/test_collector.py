"""Tests for collector: diff parsing, file status."""

from pathlib import Path

from junior.collect.core.diff import (
    _detect_file_status,
    _parse_diff_header,
    _split_diff_by_file,
)
from junior.models import FileStatus


# --- _parse_diff_header ---


def test_parse_diff_header_standard():
    assert _parse_diff_header("diff --git a/src/foo.py b/src/foo.py") == "src/foo.py"


def test_parse_diff_header_noprefix():
    assert _parse_diff_header("diff --git foo.py foo.py") == "foo.py"


def test_parse_diff_header_noprefix_nested():
    assert _parse_diff_header("diff --git src/bar/baz.py src/bar/baz.py") == "src/bar/baz.py"


def test_parse_diff_header_rename_standard():
    assert _parse_diff_header("diff --git a/old.py b/new.py") == "new.py"


# --- _split_diff_by_file ---

SAMPLE_DIFF_STANDARD = """\
diff --git a/hello.py b/hello.py
index abc..def 100644
--- a/hello.py
+++ b/hello.py
@@ -1,3 +1,4 @@
 line1
+added
diff --git a/world.py b/world.py
new file mode 100644
--- /dev/null
+++ b/world.py
@@ -0,0 +1 @@
+new file
"""

SAMPLE_DIFF_NOPREFIX = """\
diff --git hello.py hello.py
index abc..def 100644
--- hello.py
+++ hello.py
@@ -1,3 +1,4 @@
 line1
+added
diff --git world.py world.py
new file mode 100644
--- /dev/null
+++ world.py
@@ -0,0 +1 @@
+new file
"""


def test_split_diff_standard():
    chunks = _split_diff_by_file(SAMPLE_DIFF_STANDARD)
    assert set(chunks.keys()) == {"hello.py", "world.py"}
    assert "+added" in chunks["hello.py"]
    assert "+new file" in chunks["world.py"]


def test_split_diff_noprefix():
    chunks = _split_diff_by_file(SAMPLE_DIFF_NOPREFIX)
    assert set(chunks.keys()) == {"hello.py", "world.py"}
    assert "+added" in chunks["hello.py"]


def test_split_diff_empty():
    assert _split_diff_by_file("") == {}
    assert _split_diff_by_file("   \n  ") == {}


# --- _detect_file_status ---


def test_detect_status_added():
    diff = "--- /dev/null\n+++ b/new.py\n"
    assert _detect_file_status(diff, Path("/nonexistent")) == FileStatus.ADDED


def test_detect_status_deleted():
    diff = "--- a/old.py\n+++ /dev/null\n"
    assert _detect_file_status(diff, Path("/nonexistent")) == FileStatus.DELETED


def test_detect_status_renamed():
    diff = "rename from old.py\nrename to new.py\n"
    assert _detect_file_status(diff, Path("/nonexistent")) == FileStatus.RENAMED


def test_detect_status_modified(tmp_path):
    (tmp_path / "exists.py").write_text("content")
    diff = "--- a/exists.py\n+++ b/exists.py\n"
    assert _detect_file_status(diff, tmp_path / "exists.py") == FileStatus.MODIFIED

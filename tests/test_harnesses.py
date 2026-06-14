"""Cross-harness contract tests — a cheap safety net over every harness.

These don't call a model; they assert each harness module is well-formed and
self-checks cleanly. The pydantic-ai ``RunContext`` regression (a harness that
imported fine but blew up building its agent) showed why the registry-import
path alone isn't enough — but a broad net here still catches a harness that
fails to expose ``HARNESS``, mislabels its ``name``, or whose ``is_ready()``
crashes. Per-harness deep paths live in ``test_pydantic_harness`` / ``test_codex``
/ ``test_deepagents``.
"""

import pytest

from junior.config import HarnessKind
from junior.runbook.base import Harness
from junior.runbook.registry import get_harness


@pytest.mark.parametrize("kind", list(HarnessKind))
def test_harness_resolves_and_is_well_formed(kind):
    """Every HarnessKind resolves to a Harness whose name matches the enum and
    whose `complete` is callable — without importing the (lazy) SDK."""
    harness = get_harness(kind)
    assert isinstance(harness, Harness)
    assert harness.name == kind.name.lower()
    assert callable(harness.complete)


@pytest.mark.parametrize("kind", list(HarnessKind))
def test_harness_is_ready_returns_str_or_none(kind):
    """`is_ready()` is run for every installed harness on a plain `junior list`,
    so it must never raise and must return a short status (or None)."""
    status = get_harness(kind).is_ready()
    assert status is None or isinstance(status, str)

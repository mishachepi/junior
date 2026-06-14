"""Suite-wide test isolation.

Junior reads ambient config from `~/.config/junior/settings.yaml` and the repo's
`.junior.yaml`, plus shorthand env vars. Without isolation, a developer's local
config (e.g. `publish: true` or a non-default runbook) leaks into CLI tests and
makes them pass/fail depending on the machine. This autouse fixture neutralizes
both sources for every test — mirroring the local fixture in test_config.py
(which empties the same candidate lists). Tests that want config inject it
explicitly via `--config` or by re-setting the candidates themselves.
"""

import pytest


# These manage their own config paths (the wizard writes to CANDIDATES[0], and
# test_config re-sets the candidate lists per test), so the blanket isolation
# below would interfere with them.
_SELF_MANAGED = {"test_init.py", "test_config.py"}


@pytest.fixture(autouse=True)
def _reset_structlog_config():
    """CLI tests call setup_logging(), which binds structlog's global config to
    the *current* sys.stderr — under pytest that's a capture stream, closed when
    the test ends. Any later test that logs then dies with 'I/O operation on
    closed file' (which test depends on collection order). Resetting structlog
    after every test makes each one start from the lazy default logger.
    """
    yield
    import structlog

    structlog.reset_defaults()


@pytest.fixture(autouse=True)
def _hermetic_ambient_config(request, monkeypatch):
    # Scalar CLI flags are --env aliases (build_settings exports them into
    # os.environ), so a flag used in one test would leak into every later test
    # without this per-test cleanup — including the self-managed files, which
    # set the env they need explicitly.
    for var in (
        "HARNESS", "MODEL", "PUBLISH", "RUNBOOK", "BACKEND", "OUTPUT_FILE",
        "LOCAL_RUNBOOKS", "SOURCE", "TARGET_BRANCH", "LOG_LEVEL",
        "BASE_SHA", "PROJECT_DIR", "RECORD",
    ):
        monkeypatch.delenv(var, raising=False)

    if request.node.fspath.basename in _SELF_MANAGED:
        return
    import junior.config as cfg

    monkeypatch.setattr(cfg, "GLOBAL_CONFIG_CANDIDATES", (), raising=False)
    monkeypatch.setattr(cfg, "LOCAL_CONFIG_CANDIDATES", (), raising=False)

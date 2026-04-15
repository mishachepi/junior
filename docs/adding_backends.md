# Adding and Removing Backends

Junior has three pluggable backend types. Each follows the same pattern:
enum member + module with a known export. No interfaces, no ABCs, no registry.

## How It Works

```
config.py          __init__.py (dispatch)         your_module.py
-----------        ----------------------         ---------------
enum value    -->  importlib.import_module(value)  -->  exported function
```

Each backend type has:
1. An **enum** in `config.py` — value is a Python module path
2. A **dispatcher** in `__init__.py` — calls `importlib.import_module(enum.value)`
3. A **module** — must export the required function signature

## Backend Types at a Glance

| Type | Enum | Dispatcher | Required export |
|------|------|------------|-----------------|
| Collector | `CollectorBackend` | `collect/__init__.py` | `collect(settings: Settings) -> CollectedContext` |
| Agent | `AgentBackend` | `agent/__init__.py` | `review(context, settings, prompts) -> ReviewResult` |
| Publisher | `PublishBackend` | `publish/__init__.py` | `post_review(settings, result) -> None` |

---

## Adding a Collector Backend

Collectors gather context: git diff, changed files, lint findings, and optionally
platform-specific metadata (MR description, labels).

### Step 1: Create the module

```
src/junior/collect/stash.py
```

```python
"""Bitbucket Stash collector backend."""

import structlog

from junior.collect.core import collect_base, enrich_with_metadata
from junior.config import Settings
from junior.models import CollectedContext

logger = structlog.get_logger()


def collect(settings: Settings) -> CollectedContext:
    """Collect context with Stash PR metadata enrichment."""
    context = collect_base(settings)  # shared pipeline: git diff + changed files + commits + extra context
    description, labels = _fetch_stash_metadata(settings)
    return enrich_with_metadata(context, description, labels)


def _fetch_stash_metadata(settings: Settings) -> tuple[str, list[str]]:
    """Fetch PR description and labels from Stash API."""
    try:
        # your API calls here
        ...
        return description, labels
    except Exception as e:
        logger.warning("failed to fetch Stash metadata", error=str(e))
        return "", []
```

Key points:
- Call `collect_base(settings)` for the shared pipeline (diff, changed files, commits, extra context)
- Call `enrich_with_metadata(context, description, labels)` to merge API data
- Handle API errors gracefully — return `("", [])` on failure

### Step 2: Add enum member

```python
# config.py
class CollectorBackend(_ModulePathEnum):
    GITHUB = "junior.collect.github"
    GITLAB = "junior.collect.gitlab"
    STASH = "junior.collect.stash"     # <-- add
    LOCAL = "junior.collect.local"
```

### Step 3: Wire auto-detection (if token-based)

```python
# config.py — Settings class
@property
def resolved_collector(self) -> CollectorBackend:
    if self.gitlab_token:
        return CollectorBackend.GITLAB
    if self.github_token:
        return CollectorBackend.GITHUB
    if self.stash_token:                # <-- add
        return CollectorBackend.STASH
    return CollectorBackend.LOCAL
```

Add the token field and any platform-specific env vars to `Settings`.
Update `_validate_publish()` if the same platform also publishes.

### Step 4: Add dependency (if needed)

```toml
# pyproject.toml
[project.optional-dependencies]
stash = ["atlassian-python-api>=3.0"]
```

Done. `STASH_TOKEN=... junior --publish` will auto-detect and use your backend.

---

## Adding an Agent Backend

Agent backends receive collected context and return structured review findings.

### Step 1: Create the module

```
src/junior/agent/my_agent.py
```

```python
"""My custom AI review agent."""

import structlog

from junior.config import Settings
from junior.models import CollectedContext, ReviewResult, determine_recommendation
from junior.agent.core import build_user_message, read_project_instructions
from junior.prompt_loader import Prompt

logger = structlog.get_logger()


def review(
    context: CollectedContext,
    settings: Settings,
    prompts: list[Prompt],
) -> ReviewResult:
    """Run AI review. Must return ReviewResult."""
    user_msg = build_user_message(context)
    project_instructions = read_project_instructions(settings.ci_project_dir)

    # Your AI logic here:
    # - Use settings.model_string for the model (e.g. "openai:gpt-5.4-mini")
    # - Use prompts[*].body for system prompts
    # - Use project_instructions for repo-specific context
    # - Return ReviewResult with comments, summary, recommendation

    comments = []  # list[ReviewComment]
    return ReviewResult(
        summary="...",
        recommendation=determine_recommendation(comments),
        comments=comments,
        tokens_used=0,
    )
```

Key points:
- Use `build_user_message(context)` for the formatted user message (MR metadata, changed files, diff)
- Use `read_project_instructions(settings.ci_project_dir)` for AGENT.md content
- Use `settings.model_string` for the provider:model string
- Use `determine_recommendation(comments)` or let the LLM decide
- Set `tokens_used` for cost tracking in logs

### Step 2: Add enum member

```python
# config.py
class AgentBackend(_ModulePathEnum):
    PYDANTIC = "junior.agent.pydantic"
    CODEX = "junior.agent.codex"
    CLAUDECODE = "junior.agent.claudecode"
    DEEPAGENTS = "junior.agent.deepagents"
    MY_AGENT = "junior.agent.my_agent"  # <-- add
```

### Step 3: Update validation (if needed)

If your agent has special auth requirements (like codex which manages its own),
update `_validate_review()`:

```python
def _validate_review(self) -> list[str]:
    if self.agent_backend in (AgentBackend.CODEX, AgentBackend.MY_AGENT):
        return []
    # ... standard validation
```

Done. `AGENT_BACKEND=my_agent junior ...` will use your backend.

---

## Adding a Publisher Backend

Publishers post review results to a platform.

### Step 1: Create the module

```
src/junior/publish/stash.py
```

```python
"""Stash publisher backend — post review to Bitbucket PR."""

import structlog

from junior.config import Settings
from junior.models import ReviewResult
from junior.publish.core import MAX_INLINE_COMMENTS, format_inline_comment, format_summary

logger = structlog.get_logger()


def post_review(settings: Settings, result: ReviewResult) -> None:
    """Post review results to Stash PR."""
    summary = format_summary(result, settings=settings)

    # Post summary comment via API
    ...

    # Post inline comments (optional)
    inline_comments = [c for c in result.comments if c.file_path and c.line_number]
    for comment in inline_comments[:MAX_INLINE_COMMENTS]:
        body = format_inline_comment(comment)
        # Post inline comment via API
        ...
```

Key points:
- Use `format_summary(result, settings=settings)` for the markdown summary
- Use `format_inline_comment(comment)` for individual inline comments
- Respect `MAX_INLINE_COMMENTS` limit
- Handle API errors gracefully (inline comment failure is not critical)

### Step 2: Add enum member + auto-detection

Same pattern as collector — add to `PublishBackend` enum and `resolved_publisher`.

---

## Removing a Backend

### Example: removing GitHub support

1. Delete the modules:
   ```
   rm src/junior/collect/github.py
   rm src/junior/publish/github.py
   ```

2. Remove enum members from `config.py`:
   ```python
   class CollectorBackend(_ModulePathEnum):
       # GITHUB = "junior.collect.github"  # removed
       GITLAB = "junior.collect.gitlab"
       LOCAL = "junior.collect.local"
   ```

3. Remove auto-detection branches in `resolved_collector`, `resolved_publisher`

4. Remove `github_*` fields from `Settings` (if no longer needed)

5. Remove GitHub-specific validation from `_validate_publish()`

6. Remove dependencies from `pyproject.toml` (if any were GitHub-only)

No other files need to change — dispatch is fully decoupled.

---

## Shared Utilities

Each backend type has a `core/` directory with shared code:

| Directory | Shared utilities |
|-----------|-----------------|
| `collect/core/` | `collect_base()`, `enrich_with_metadata()` |
| `agent/core/` | `build_user_message()`, `build_review_prompt()`, `read_project_instructions()`, `BASE_RULES` |
| `publish/core/` | `format_summary()`, `format_inline_comment()`, `MAX_INLINE_COMMENTS` |

Use these instead of reimplementing common logic in your backend.

## Checklist

- [ ] Module created with required export function
- [ ] Enum member added to `config.py`
- [ ] Auto-detection wired (if token-based)
- [ ] Validation updated (if special auth requirements)
- [ ] Dependencies added to `pyproject.toml` (if needed)
- [ ] Tested locally: `AGENT_BACKEND=my_backend junior --target-branch main`

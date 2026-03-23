# Step 5: Publish (Phase 3)

**Module**: `junior.publish.local.post_review()` via `junior.publish.core.formatter.format_summary()`

## Input

- `ReviewResult` from Step 4
- `Settings` (for footer metadata)

## Output: Formatted Markdown (99 lines)

Written to `/tmp/junior_review_output.md`.

### Header

```markdown
## Junior Code Review

The code quality is poor overall, with multiple critical security flaws
that must be addressed immediately: unsafe `eval`, command injection via
`shell=True`, SQL injection in several helpers, weak token handling,
hardcoded secrets, and MD5 password hashing...
```

### Findings Table

```markdown
| Severity | Count |
|----------|-------|
| Red Critical | 5 |
| Orange High | 20 |
| Yellow Medium | 13 |
```

### Detailed Findings (grouped by severity)

```markdown
#### Critical
- **[security]** `api.py:93` -- `process_webhook()` uses `eval(payload)`...
  - Suggestion: Parse the payload with `json.loads()`...

#### High
- **[security]** `auth.py:55` -- `check_permission()` returns `True`...
  - Suggestion: Fail closed: return `False` for unknown roles...
...

#### Medium
- **[security]** `hello.py:29` -- `load_contacts()` accepts arbitrary file_path...
  - Suggestion: Restrict reads to a fixed directory...
```

### Footer

```markdown
---
*Reviewed by Junior AI | pydantic | 35,398 tokens*
```

## Data Flow Summary

```
CollectedContext (Step 1)
    |
    v
build_user_message() (Step 2) ---> User Message (12KB markdown)
    |
    v
load_prompts() (Step 3) ---------> System Prompts (4KB, 3 agents)
    |
    v
pydantic.review() (Step 4) ------> ReviewResult (38 findings, 35K tokens)
    |
    v
format_summary() (Step 5) -------> Formatted Review (99 lines markdown)
    |
    v
local.post_review() -------------> /tmp/junior_review_output.md (or stdout)
```

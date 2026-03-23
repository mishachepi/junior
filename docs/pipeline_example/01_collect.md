# Step 1: Collect (Phase 1)

**Module**: `junior.collect.local` -> `junior.collect.core.collect.collect_base()`

Pipeline: `git diff` -> parse files -> detect project -> commit messages -> extra context.

## Input

| Parameter | Value |
|-----------|-------|
| `ci_project_dir` | `.` |
| `target_branch` | `main` |
| `base_sha` | (none) |
| `collector` | `local` |

## Output: `CollectedContext`

```json
{
  "project_id": 0,
  "mr_iid": 0,
  "mr_title": "",
  "mr_description": "",
  "source_branch": "",
  "target_branch": "main",
  "labels": [],
  "commit_messages": [
    "feat: add authentication and database layer\nImplement user authentication with token-based sessions\nand SQLite database for user management.",
    "feat: add API endpoints and integrate auth with greetings\nAdd REST-like handlers for login, registration, search,\nadmin actions, and webhook processing.\nUpdate hello.py to support authenticated greetings."
  ],
  "full_diff": "<11,801 chars — full unified diff of 4 files>",
  "changed_files": [
    {"path": "api.py",      "status": "added",    "diff": "<...>", "content": "<109 lines>"},
    {"path": "auth.py",     "status": "added",    "diff": "<...>", "content": "<103 lines>"},
    {"path": "database.py", "status": "added",    "diff": "<...>", "content": "<120 lines>"},
    {"path": "hello.py",    "status": "modified", "diff": "<...>", "content": "<58 lines>"}
  ],
  "extra_context": {}
}
```

## Key Metrics

| Metric | Value |
|--------|-------|
| Diff size | 11,801 chars |
| Changed files | 4 |
| Commits parsed | 2 |
| Extra context | none |

## Notes

- Local collector skips MR metadata (title, description, labels) since there's no API
- `source_branch` is empty because local collector doesn't query git for current branch name
- Each `ChangedFile` contains both the unified diff and full file content

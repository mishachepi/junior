# Step 2: Context Builder (User Message)

**Module**: `junior.agent.core.context_builder.build_user_message()`

Transforms `CollectedContext` into a markdown-formatted user message for the AI agent.

## Input

`CollectedContext` from Step 1.

## Output: User Message (440 lines, 12,339 chars)

```markdown
## Merge Request:
**Branches:**  -> main

### Commits (2)
- feat: add authentication and database layer
  Implement user authentication with token-based sessions
  and SQLite database for user management.
- feat: add API endpoints and integrate auth with greetings
  Add REST-like handlers for login, registration, search,
  admin actions, and webhook processing.
  Update hello.py to support authenticated greetings.

### Changed Files
- `api.py` (added)
- `auth.py` (added)
- `database.py` (added)
- `hello.py` (modified)

### Diff
\`\`\`diff
diff --git api.py api.py
new file mode 100644
...
<full unified diff — 385 added lines across 4 files>
...
\`\`\`
```

## Structure

| Section | Content |
|---------|---------|
| Header | MR title, description, branches, labels |
| Additional Context | `--context` and `--context-file` entries (empty here) |
| Commits | List of commit messages |
| Changed Files | File paths with status |
| Diff | Full unified diff in a code block |

## Data Flow

```
CollectedContext --> build_user_message() --> str (markdown)
                                                |
                                                v
                                    Sent as user message to AI agent
```

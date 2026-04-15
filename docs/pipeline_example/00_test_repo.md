# Step 0: Test Repository

## Branches

- **main**: single commit `088ac41 initial: hello world` (only `hello.py` with basic `greet()`)
- **feature/auth-system**: 2 commits on top of main

## Commits on feature/auth-system

```
9feab5b feat: add API endpoints and integrate auth with greetings
ef9098a feat: add authentication and database layer
```

## Changed Files (4 files, +385 lines)

| File | Status | Lines |
|------|--------|-------|
| `api.py` | added | +109 |
| `auth.py` | added | +103 |
| `database.py` | added | +120 |
| `hello.py` | modified | +53 |

## CLI Command

```bash
OPENAI_API_KEY=sk-... junior \
  --backend pydantic \
  --prompts security,logic,design \
  --source branch \
  --target-branch main \
  -o /tmp/junior_review_output.md \
  ../junior-test-repo
```

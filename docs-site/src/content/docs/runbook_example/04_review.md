---
title: "Step 4: AI Review (Phase 2)"
---

# Step 4: AI Review (Phase 2)

**Module**: `junior.harnesses.pydantic` (via `junior.runbook.runner.run_runbook()`)

**Provider**: OpenAI | **Model**: gpt-5.4-mini | **Tokens**: 35,398

## Input

- User message from Step 2 (12,339 chars)
- The merged system prompt from Step 3 (4,316 chars total)
- The pydantic harness makes a single structured LLM call

## Output: `ReviewResult`

The pydantic harness makes one structured LLM call with `output_type=LLMReviewOutput`. The model returns the `summary`, `recommendation`, and the full `comments` list directly in that one response. Junior only attaches the measured token usage afterward.

```json
{
  "summary": "The code quality is poor overall, with multiple critical security flaws...",
  "recommendation": "request_changes",
  "comments": [/* 38 findings */],
  "input_tokens": 28174,
  "output_tokens": 7224,
  "tokens_used": 35398
}
```

## Findings Summary

| Severity | Count |
|----------|-------|
| Critical | 5 |
| High | 20 |
| Medium | 13 |
| **Total** | **38** |

## Critical Findings

| File | Line | Category | Issue |
|------|------|----------|-------|
| `api.py` | 93 | security | `eval(payload)` on untrusted input — arbitrary code execution |
| `api.py` | 59 | security | `subprocess.run(..., shell=True)` with user input — command injection |
| `api.py` | 88 | bug | `eval(payload)` in webhook handler |
| `api.py` | 73 | security | `eval(payload)` — flagged again at a second call site |
| `api.py` | 50 | security | `shell=True` with user-controlled command |

## High Findings (top 10)

| File | Line | Category | Issue |
|------|------|----------|-------|
| `auth.py` | 55 | security | `check_permission()` returns True for unknown roles |
| `auth.py` | 14 | security | Deterministic token from timestamp + hardcoded secret |
| `auth.py` | 8 | security | Hardcoded `SECRET_KEY` in source |
| `auth.py` | 11 | security | MD5 for password hashing |
| `database.py` | 33 | security | SQL injection via f-string in `find_user()` |
| `database.py` | 61 | bug | SQL injection in `delete_user()` |
| `database.py` | 70 | bug | SQL injection in `update_user_role()` |
| `database.py` | 80 | bug | SQL injection in `list_users()` |
| `database.py` | 94 | bug | SQL injection in `search_users()` |
| `auth.py` | 27 | logic | Token validation broken — regenerates with current timestamp |

## Notes

- Some issues are flagged more than once (e.g. `eval` at multiple call sites)
- The model returns `request_changes` as the `recommendation`, given the critical findings
- 35,398 tokens used by the single structured call

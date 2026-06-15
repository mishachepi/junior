---
title: "Review output in detail"
---

# Review output in detail

The full result of the run traced in [Anatomy of a run](README.md): all 38
findings the model returned, and the markdown Junior rendered from them.

## Findings

The model returned `request_changes` with 38 comments:

| Severity | Count |
|----------|-------|
| 🔴 Critical | 5 |
| 🟠 High | 20 |
| 🟡 Medium | 13 |
| **Total** | **38** |

### Critical

| File | Line | Category | Issue |
|------|------|----------|-------|
| `api.py` | 93 | security | `eval(payload)` on untrusted input — arbitrary code execution |
| `api.py` | 59 | security | `subprocess.run(..., shell=True)` with user input — command injection |
| `api.py` | 88 | bug | `eval(payload)` in webhook handler |
| `api.py` | 73 | security | `eval(payload)` — flagged again at a second call site |
| `api.py` | 50 | security | `shell=True` with user-controlled command |

### High (top 10)

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

A few issues are flagged more than once (e.g. `eval` at multiple call sites).
With critical findings present, the model's `recommendation` is
`request_changes`.

## Formatted output

`publish.core.formatter.format_summary()` renders the `ReviewResult` to markdown
(here 99 lines). Structure:

### Header

```markdown
## Junior Code Review

The code quality is poor overall, with multiple critical security flaws
that must be addressed immediately: unsafe `eval`, command injection via
`shell=True`, SQL injection in several helpers, weak token handling,
hardcoded secrets, and MD5 password hashing...
```

### Findings table

```markdown
### Findings

| Severity | Count |
|----------|-------|
| 🔴 Critical | 5 |
| 🟠 High | 20 |
| 🟡 Medium | 13 |
```

### Detailed findings (grouped by severity)

```markdown
#### 🔴 Critical
- **[security]** `api.py:93` — `process_webhook()` uses `eval(payload)`...
  - Suggestion: Parse the payload with `json.loads()`...

#### 🟠 High
- **[security]** `auth.py:55` — `check_permission()` returns `True`...
  - Suggestion: Fail closed: return `False` for unknown roles...

#### 🟡 Medium
- **[security]** `hello.py:29` — `load_contacts()` accepts arbitrary file_path...
  - Suggestion: Restrict reads to a fixed directory...
```

### Footer

```markdown
---
*Reviewed by [Junior AI](https://github.com/mishachepi/junior/) | pydantic | gpt-5.4-mini | 28,174 in / 7,224 out tokens*
```

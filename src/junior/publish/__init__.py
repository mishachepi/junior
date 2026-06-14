"""Phase 3: publish review results.

Each module (local / gitlab / github) exports `post_review(settings, result)`.
Runbooks call the one for their platform directly — the platform is part of
each runbook (see junior.runbooks.code_review).
"""

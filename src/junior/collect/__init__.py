"""Phase 1: deterministic context collection.

Each module (local / gitlab / github) exports `collect(settings) -> ReviewContext`.
Runbooks import the one they need directly — there is no central dispatch; the
platform is part of each runbook (see junior.runbooks.code_review).
"""

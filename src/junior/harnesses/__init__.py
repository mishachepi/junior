"""LLM harnesses (phase 2 drivers).

Each harness module here exposes a `HARNESS` instance implementing
`junior.runbook.base.Harness`. Resolution happens in
`junior.runbook.registry.get_harness` via the `HarnessKind` enum (whose value
is the module path). Harnesses are domain-agnostic — prompt/context building
lives in each runbook (e.g. `junior.runbooks.code_review`).
"""

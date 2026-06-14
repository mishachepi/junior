---
title: "Use cases"
description: Six things teams do with Junior — each one command (or two lines of YAML) away.
---

# Use cases

Six things teams actually do with Junior. Each is one command — or two lines of YAML — away.

## Gate your CI on an AI review

Junior exits **1** when the review finds a blocking issue (a critical finding or a
`request_changes` recommendation) — so a pipeline step *is* the quality gate, no glue code:

```yaml
# .gitlab-ci.yml
ai-review:
  script:
    - junior run --runbook gitlab_pr_review --publish   # posts the MR note + inline threads
```

The MR gets a structured review; a critical finding fails the job. Ready-to-paste configs
for GitLab CI and GitHub Actions: [Run in CI](ci.md).

## Review your changes before you push

The `local_review` runbook reviews your **local diff** — no PR, no tokens, no setup
beyond `junior init`:

```bash
junior run --source staged --prompt "Quick correctness check"   # what you're about to commit
junior run                                                      # the whole branch vs main
```

Add `--publish` for a pretty Markdown review in the terminal instead of raw JSON.

## Bring AI review to Bitbucket Data Center

Self-hosted Bitbucket has no native AI review. Junior posts a summary comment plus inline
comments anchored to the diff — from any CI (Jenkins, Bamboo, TeamCity):

```bash
junior run --runbook bitbucket_pr_review --publish \
  --env BITBUCKET_URL=https://bitbucket.company.com \
  --env BITBUCKET_TOKEN=$TOKEN --env BITBUCKET_PROJECT=PROJ \
  --env BITBUCKET_REPO=backend --env BITBUCKET_PR_ID=$PR_ID
```

Setup details: [Run in CI → Bitbucket Data Center](ci.md#bitbucket-data-center).

## Keep the code on your machine — local models

The `pi` harness runs reviews on **Ollama / LM Studio / vLLM** — no API key, no cloud,
nothing leaves the laptop. Declare the endpoint once in `~/.pi/agent/models.json`, then:

```bash
junior run --harness pi --model ollama/qwen2.5-coder:7b
```

How it works (and its limits on small models): [Pi harness](agent_backends/pi.md).

## Write your own runbook — two lines of YAML

A runbook is *collect → one schema-validated LLM call → publish*. The smallest one is a
prompt plus a shell command:

```yaml
# .junior/runbooks/standup/standup.yaml
system_prompt: Summarize this git log as a short standup update.
collect: git log --since=yesterday --oneline
```

```bash
echo "local_runbooks: true" >> .junior.yaml   # enable repo-local runbooks (once)
junior run --runbook standup                 # validated JSON on stdout
```

Schemas, publish commands, env — the full manifest reference:
[Write a runbook in YAML](script_runbooks.md).

## Chain juniors — one does the task, the next one checks it

Runbooks compose like any Unix tool (the rules: [Runbooks in YAML](script_runbooks.md)):

```bash
junior run --runbook triage | junior run --runbook gatekeeper --publish
```

The first junior produces a draft (say, an incident summary from `ansible-playbook`
output); the second reviews it against your rules and publishes only what passes —
to a terminal, a file, or a script that posts to Jira. Recipe:
[Write a runbook in YAML → chaining](script_runbooks.md).

---

Every run, in every scenario, leaves a secret-free audit trail in
`.junior/output/{timestamp}.json` (`junior runs` to browse) — you can always replay
what was delegated and what came back. That premise is the whole point:
[Philosophy](philosophy.md).

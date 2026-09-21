---
name: release
description: Cut a junior release — bump version, roll CHANGELOG, tag, push; the tag triggers the Docker image build+push to Docker Hub. Use when the user says "release", "cut X.Y.Z", "tag a version", "publish the image".
---

# Release junior

One release = one commit + one annotated tag `X.Y.Z` (no `v` prefix) on `main`.
Pushing the tag runs `.github/workflows/release-image.yml`, which builds the
`full` image (amd64 + arm64) and pushes `mihchepi/junior:X.Y.Z` + `:latest`.

## Preconditions

- On `main`, `git status` clean, `main` == `origin/main`.
- Latest CI run on `main` is green: `gh run list --workflow ci.yml --limit 1`.
- `CHANGELOG.md` has a non-empty `## Unreleased` section.
- Repo secrets `DOCKERHUB_USERNAME` + `DOCKERHUB_TOKEN` exist
  (`gh secret list`) — without them the image job fails at login.

## Steps

1. **Pick the version.** Patch for fixes, minor for new harnesses/runbooks or
   CLI surface changes. Current: `grep -m1 '^version' pyproject.toml`.
2. **Bump** `version = "X.Y.Z"` in `pyproject.toml`, then `uv lock`
   (the lock records the project version).
3. **Roll the CHANGELOG:** rename `## Unreleased` → `## X.Y.Z — YYYY-MM-DD`
   and insert a fresh empty `## Unreleased` above it.
4. **Smoke:** `uv run ruff check src/ tests/` and `uv run --all-extras pytest -q`
   must be green.
5. **Commit + tag:**
   ```bash
   git add pyproject.toml uv.lock CHANGELOG.md
   git commit -m "release: X.Y.Z"
   git tag -a X.Y.Z -m "X.Y.Z"
   ```
6. **Push** — only on the user's explicit go:
   ```bash
   git push origin main && git push origin X.Y.Z
   ```
7. **Verify the image job:**
   ```bash
   gh run list --workflow release-image.yml --limit 1
   gh run watch <id> --exit-status
   docker run --rm mihchepi/junior:X.Y.Z junior --version   # prints X.Y.Z
   ```

The workflow refuses a tag whose version differs from `pyproject.toml` — that
is the guard against tagging the wrong commit.

## Fallbacks

- **Rebuild an existing version** (image only, no new tag):
  `gh workflow run release-image.yml -f version=X.Y.Z` — builds `main` HEAD, so
  only do this when HEAD *is* that version.
- **Local build** (no CI): needs a docker daemon (`colima start`) and the
  `docker-buildx` plugin (`brew install docker-buildx`), plus `docker login`.
  ```bash
  docker buildx build --target full --platform linux/amd64,linux/arm64 \
    --build-arg VERSION=X.Y.Z -t mihchepi/junior:X.Y.Z -t mihchepi/junior:latest --push .
  ```
  Single-arch smoke without pushing: drop `--platform` and `--push`, add `--load`.

## Don'ts

- No release from a branch other than `main`; no tag without the matching
  `pyproject.toml` bump in the same commit.
- Never re-point an existing tag. Wrong tag → cut the next patch version.

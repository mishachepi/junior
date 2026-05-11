# syntax=docker/dockerfile:1.7
# ---- base: uv + python + git ----
FROM ghcr.io/astral-sh/uv:0.11-python3.14-trixie-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_PROGRESS=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# OCI metadata. VERSION is overridden at build time:
#   docker build --build-arg VERSION=$(grep -oP 'version = "\K[^"]+' pyproject.toml) --target pydantic .
ARG VERSION=dev
LABEL org.opencontainers.image.title="junior" \
      org.opencontainers.image.description="AI code review agent for GitLab MRs and GitHub PRs" \
      org.opencontainers.image.source="https://github.com/mishachepi/junior" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}"

COPY pyproject.toml uv.lock ./


# ---- pydantic: default backend + gitlab support ----
FROM base AS pydantic

# 1) Resolve and install dependencies only — this layer is reused as long as
#    pyproject.toml and uv.lock are unchanged, even when src/ changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --extra gitlab

# 2) Install the project itself — busts only when src/ changes.
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable --extra gitlab

RUN useradd -u 1000 --create-home junior
USER junior
# Intentional broad scope: CI volume mounts often have unpredictable ownership.
# If you run this image locally with a mounted workspace, the same setting
# avoids "dubious ownership" errors from git.
RUN git config --global --add safe.directory '*'
CMD ["junior"]


# ---- codex: codex CLI backend + gitlab support ----
FROM base AS codex

# Node.js from NodeSource APT repo. More robust than `COPY --from=node:...`
# because the node binary then matches the runtime libc/libstdc++ ABI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @openai/codex \
    && npm cache clean --force

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --extra gitlab --extra codex

COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable --extra gitlab --extra codex

RUN useradd -u 1000 --create-home junior
USER junior
RUN git config --global --add safe.directory '*'
CMD ["junior"]


# ---- full: all backends ----
FROM base AS full

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @openai/codex \
    && npm cache clean --force

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --extra all --extra codex

COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable --extra all --extra codex

RUN useradd -u 1000 --create-home junior
USER junior
RUN git config --global --add safe.directory '*'
CMD ["junior"]

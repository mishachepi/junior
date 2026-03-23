# ---- Base: uv + python + git ----
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock* ./


# ---- pydantic: default backend + gitlab support ----
FROM base AS pydantic

COPY src/ ./src/
RUN uv pip install --no-cache ".[gitlab]"

RUN useradd --create-home junior
USER junior
RUN git config --global --add safe.directory '*'
CMD ["junior"]


# ---- codex: codex CLI backend + gitlab support ----
FROM base AS codex

COPY --from=node:22.16-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22.16-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && npm install -g @openai/codex \
    && npm cache clean --force

COPY src/ ./src/
RUN uv pip install --no-cache ".[gitlab,codex]"

RUN useradd --create-home junior
USER junior
RUN git config --global --add safe.directory '*'
CMD ["junior"]


# ---- full: all backends ----
FROM base AS full

COPY --from=node:22.16-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22.16-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && npm install -g @openai/codex \
    && npm cache clean --force

COPY src/ ./src/
RUN uv pip install --no-cache ".[all]"

RUN useradd --create-home junior
USER junior
RUN git config --global --add safe.directory '*'
CMD ["junior"]

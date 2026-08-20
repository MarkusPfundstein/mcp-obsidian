FROM python:3.11-slim AS base

# Pull the standalone uv/uvx binaries instead of installing via pip.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so they're cached independently of source changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# The server speaks MCP over stdio, so it must be run with stdin attached
# (e.g. `docker compose run --rm -T mcp-obsidian`), not `docker compose up`.
ENTRYPOINT ["mcp-obsidian"]

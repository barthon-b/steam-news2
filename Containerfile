FROM python:3.13-slim

# Install uv (the `uv` + `uvx` binaries) from its official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_LINK_MODE=copy

# Layer 1: dependencies only, so source changes don't re-resolve/re-download.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Layer 2: source + the project itself.
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["steam-news2"]

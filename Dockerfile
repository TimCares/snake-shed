# syntax=docker/dockerfile:1

# =============================================================================
# Stage 1: Builder — install dependencies and build the package
# =============================================================================
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install only runtime dependencies first (layer cache — only re-runs when lockfile changes).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy source and install the project itself into the virtualenv.
COPY src/ src/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# =============================================================================
# Stage 2: Runtime — minimal production image
# =============================================================================
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/build/building/best-practices/#user
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/app" \
    --shell "/usr/sbin/nologin" \
    --uid "${UID}" \
    appuser

WORKDIR /app

# Copy the production virtual environment with runtime assets.
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

USER appuser

CMD ["python", "-m", "my_project"]

# syntax=docker/dockerfile:1
#
# Replace `my_project` with your actual package name (matches
# [project].name in pyproject.toml with hyphens → underscores).

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

# Tells the app's config loader to skip the implicit `config/.env` fallback.
# Container env vars must come from the runtime (`docker run --env-file`,
# Compose `env_file:`, k8s Secrets, …), never from a file baked into the image.
ENV __DISABLE_LOAD_DOTENV__=1

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

# Copy the production virtual environment and runtime assets.
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser src/ src/

USER appuser

CMD ["python", "-m", "my_project"]

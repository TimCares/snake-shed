# syntax=docker/dockerfile:1

# =============================================================================
# Stage 1: Builder — install dependencies and build the package
# =============================================================================
# Pinned to bookworm (Debian 12) on purpose: it must match the glibc of the
# distroless/cc-debian12 runtime below, because we copy a handful of system
# shared libraries (libz, libgomp, ...) from this stage into that one. `slim`
# alone now resolves to trixie (Debian 13, newer glibc), which would risk
# `GLIBC_x.y not found` errors at runtime.
FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /uvx /bin/

# UV_PYTHON_INSTALL_DIR  install the managed interpreter to a fixed, relocatable
#                        path we can copy verbatim into the runtime image.
# UV_PYTHON_PREFERENCE   never fall back to the slim base's /usr/local Python;
#                        the venv must be built against the managed standalone
#                        CPython so the runtime image needs no system Python.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed

WORKDIR /app

# Install a self-contained, managed CPython (python-build-standalone) into
# /python, pinned by .python-version. This interpreter is what the venv links
# against and what we copy into the distroless runtime, no apt, no system
# Python, fully version-controlled.
COPY .python-version ./
RUN uv python install

# Install only runtime dependencies first (layer cache => only re-runs when lockfile changes).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy source and install the project itself into the virtualenv.
COPY src/ src/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# =============================================================================
# Stage 2: Library staging — collect the system .so files distroless lacks
# =============================================================================
# Only the distroless runtime needs this; the debian runtime already has a full
# userland. scripts/stage_libs.py runs ldd over the venv + managed interpreter
# to find every system shared library the wheels link against (their DT_NEEDED
# closure — automatic, self-maintaining), plus any lazily dlopen'd libraries
# named in extra-libs.txt, and copies them under /staging-libs mirroring their
# absolute paths. See that script's module docstring and extra-libs.txt for the
# full rationale.
FROM builder AS lib-staging

COPY scripts/stage_libs.py docker/extra-libs.txt ./
RUN python stage_libs.py --allowlist extra-libs.txt --output /staging-libs

# =============================================================================
# Stage 3 (optional): Debian runtime — convenience target, NOT for production
# =============================================================================
# A full debian:bookworm userland, so every system library a wheel might dlopen
# at runtime is already present: you trade a much larger attack surface (exactly
# the OS-CVE surface distroless removes) for never having to think about a
# missing .so. Use it while iterating, or when you hit a lazy-dlopen miss you
# have not yet catalogued in extra-libs.txt — then move the lib into the
# allowlist and ship the distroless target to production.
#
# Built only on request: `docker build --target runtime-debian .`
FROM debian:bookworm AS runtime-debian

# Match the distroless runtime's unprivileged uid 65532 so file permissions and
# USER semantics are identical across both targets.
RUN groupadd --gid 65532 nonroot \
    && useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin nonroot

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# No /staging-libs here — debian provides the system libraries itself. Just the
# managed interpreter and the venv (same provenance as the distroless target).
COPY --from=builder /python /python
COPY --from=builder /app/.venv /app/.venv

USER nonroot

CMD ["python", "-m", "my_project"]

# =============================================================================
# Stage 4: hardened — the production image (distroless, DEFAULT build target)
# =============================================================================
# `hardened` IS the distroless runtime (formerly named `runtime-distroless`);
# the name states the intent — minimal attack surface — rather than the base
# image. gcr.io/distroless/cc provides glibc + libgcc + libstdc++ + CA
# certificates and NOTHING ELSE — no shell, no package manager, no
# perl/ncurses/sqlite. That both shrinks the attack surface (the OS CVEs we
# previously VEX-suppressed are simply not present) and complements the runtime
# hardening in docker-compose.yaml (read_only, cap_drop: ALL, no-new-privileges):
# there is no `sh`/`apt`/`curl` left for an attacker to pivot with after a
# hypothetical RCE.
#
# This is the LAST stage, so a plain `docker build` (no --target) produces it.
# The `:nonroot` tag runs as uid 65532 by default.
FROM gcr.io/distroless/cc-debian12:nonroot AS hardened

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# System shared libraries the wheels need that distroless/cc omits (libz, ...),
# discovered and staged by scripts/stage_libs.py in the lib-staging stage under
# their original absolute paths. Merging at / lands each lib in its correct
# multiarch dir (/usr/lib/<arch>-linux-gnu) on the loader's default search path;
# architecture-portable because every stage is built for the same platform.
COPY --from=lib-staging /staging-libs/ /

# The managed CPython the venv is linked against (its bin/python symlink points
# into /python), followed by the venv itself. Both stay root-owned and
# world-readable: the unprivileged runtime user can execute but not modify its
# own code — defense in depth alongside the read-only root filesystem.
COPY --from=builder /python /python
COPY --from=builder /app/.venv /app/.venv

USER nonroot

# Build-time import gate: load every compiled extension module the venv ships
# and fail the build if any cannot be dynamically linked. This catches a system
# library a wheel reaches for lazily via dlopen — which ldd never sees, so
# stage_libs.py cannot stage it — here, at build time, instead of as a runtime
# ImportError in production. Runs as `nonroot` against the final image
# filesystem; the script is bind-mounted for this one step, so nothing extra
# ships in the image (distroless has no shell, hence the exec form).
RUN --mount=type=bind,source=scripts/validate_imports.py,target=/tmp/validate_imports.py \
    ["/app/.venv/bin/python", "/tmp/validate_imports.py"]

CMD ["python", "-m", "my_project"]

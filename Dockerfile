# syntax=docker/dockerfile:1.7
#
# ecs-deploy CLI container image (ignitetech-group fork of fabfuel/ecs-deploy).
#
# Base: CPython 3.13 on Debian Trixie (Debian 13). Ships glibc 2.41 +
# OpenSSL 3.5, both newer than what alpine:3.19 offers, and importantly
# uses the same libc/SSL stack as our other production containers
# (gfi-mcp, etc.) so security advisories track in lockstep.
#
# Build: multi-stage. Stage 1 installs the package + its hashed,
# cooldown-pinned dependency lockfile (requirements.txt) into a venv. Stage
# 2 is a clean slim-trixie image that just inherits the venv. The pip
# cache, the uv binary, and any apt build deps live only in stage 1.

# ---------------------------------------------------------------------------
# Builder stage
# ---------------------------------------------------------------------------
FROM python:3.13-slim-trixie AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install uv (fast resolver/installer). Pinned to a known-good release.
COPY --from=ghcr.io/astral-sh/uv:0.8.13 /uv /uvx /usr/local/bin/

WORKDIR /build

# Sync the dependency tree from the hashed lockfile FIRST, before copying
# project source. Layer-cache busts only when requirements.txt changes.
COPY requirements.txt ./
RUN python -m venv /opt/venv && \
    uv pip sync --python /opt/venv/bin/python requirements.txt

# Now install the package itself (no deps, since they're already pinned).
COPY setup.py setup.cfg README.rst ./
COPY ecs_deploy ./ecs_deploy/
RUN uv pip install --no-deps --python /opt/venv/bin/python .

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM python:3.13-slim-trixie

LABEL org.opencontainers.image.source="https://github.com/ignitetech-group/ecs-deploy"
LABEL org.opencontainers.image.description="ignitetech-group fork of fabfuel/ecs-deploy"
LABEL org.opencontainers.image.licenses="BSD-3-Clause"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:${PATH}"

# ca-certificates is required by botocore/boto3 to verify HTTPS to AWS
# endpoints. We don't need git or build tools at runtime — those lived
# only in the builder stage.
# hadolint ignore=DL3008
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# Run as a non-root user. uid 1001 is the project standard and matches the
# gfi-mcp pattern used elsewhere in the org.
RUN useradd --system --uid 1001 --create-home --shell /usr/sbin/nologin app
USER app
WORKDIR /home/app

ENTRYPOINT ["ecs"]
CMD ["--help"]

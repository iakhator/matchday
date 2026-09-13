# Production image. See Dockerfile.dev for local development, which runs
# with --reload, installs dev dependencies and bind-mounts the source.
#
# Two stages so the build toolchain and the uv cache stay out of the image
# that actually runs.

FROM python:3.13-slim-trixie AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dependencies are resolved from the lockfile before the source is copied,
# so editing application code does not invalidate this layer.
#
# --no-dev leaves out pytest and friends: a production image should not be
# able to run the test suite, and every package left out is one that cannot
# have a vulnerability reported against it here.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev


FROM python:3.13-slim-trixie AS runtime

# curl is for the healthcheck below. Nothing else is added - the smaller
# the runtime image, the less there is to keep patched.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# A compromised process should not be able to modify the code it is
# running, so the app runs as a user that does not own /app.
RUN useradd --create-home --uid 10001 gateway

WORKDIR /app

COPY --from=builder --chown=root:root /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER gateway

EXPOSE 8010

# Liveness only - deliberately not /health/scheduler. A stale sync job
# means the data is going stale, not that this container is broken, and
# restarting it would neither fix the sync nor stop the restart loop.
# Point an uptime monitor at /health/scheduler instead; see the README.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8010/health || exit 1

# `serve` starts the API; `migrate` applies migrations and exits, for a
# release phase to call. See docker-entrypoint.sh for why migrations are
# not run automatically on start.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["serve"]

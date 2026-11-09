# syntax=docker/dockerfile:1

# ---- builder: resolve the locked runtime dependencies into /opt/venv ----
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
# Only the lockfile and manifest, so this layer is cached until dependencies change.
# The s3 and redis extras are included so one image runs any backend; dev/lint extras stay out.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --extra s3 --extra redis --no-install-project

# ---- runtime: slim image, no uv, non-root ----
FROM python:3.14-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --no-create-home app

# Same path as in the builder, so the venv's script shebangs still resolve.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Local-backend storage. Mount a volume here; Docker seeds an empty named volume with this ownership.
RUN mkdir -p /data/images && chown app:app /data/images

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROGIMAGE_STORAGE_DIR=/data/images

USER app
EXPOSE 8000

# Liveness only (slim images have no curl). Readiness (/readyz) is for the orchestrator to gate traffic on.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

# Exec form so SIGTERM reaches uvicorn. Worker count comes from WEB_CONCURRENCY, which uvicorn reads natively.
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--timeout-graceful-shutdown", "20"]

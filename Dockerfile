# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.12-alpine AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

FROM python:3.12-alpine
WORKDIR /app
ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /app/.venv /app/.venv
COPY src ./src

ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8080

EXPOSE 8080
ENTRYPOINT ["python", "-m", "abs_webnovel.main", "--cache-dir", "/app/cache"]

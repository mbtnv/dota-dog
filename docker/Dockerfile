FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /usr/local/bin/uv

FROM base AS builder

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY src ./src

RUN uv sync --no-dev

FROM base AS runtime

COPY --from=builder /app /app

CMD ["/app/.venv/bin/python3", "-m", "dota_dog.app"]

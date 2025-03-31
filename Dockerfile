FROM ghcr.io/astral-sh/uv:python3.13-alpine AS builder

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY uv.lock pyproject.toml /app/

RUN uv sync --frozen --no-install-project --no-dev

COPY . /app

RUN uv sync --frozen --no-dev

FROM python:3.13-alpine

COPY --from=builder --chown=app:app /app /app

LABEL maintainer="Elias Benbourenane <eliasbenbourenane@gmail.com>" \
    org.opencontainers.image.title="PlexAniBridge" \
    org.opencontainers.image.description="Synchronize your Plex watch history, ratings, and reviews with AniList" \
    org.opencontainers.image.authors="Elias Benbourenane <eliasbenbourenane@gmail.com>" \
    org.opencontainers.image.url="https://plexanibridge.elias.eu.org" \
    org.opencontainers.image.documentation="https://plexanibridge.elias.eu.org" \
    org.opencontainers.image.source="https://github.com/eliasbenb/PlexAniBridge" \
    org.opencontainers.image.licenses="MIT"

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

CMD ["python", "/app/main.py"]

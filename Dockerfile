FROM ghcr.io/astral-sh/uv:python3.13-alpine AS builder

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never

RUN apk add --no-cache git

RUN --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

COPY . /app

WORKDIR /app

RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-alpine

COPY --from=builder --chown=app:app /opt/venv /opt/venv

LABEL maintainer="Elias Benbourenane <eliasbenbourenane@gmail.com>" \
    org.opencontainers.image.title="PlexAniBridge" \
    org.opencontainers.image.description="Synchronize your Plex watch history, ratings, and reviews with AniList" \
    org.opencontainers.image.authors="Elias Benbourenane <eliasbenbourenane@gmail.com>" \
    org.opencontainers.image.url="https://plexanibridge.elias.eu.org" \
    org.opencontainers.image.documentation="https://plexanibridge.elias.eu.org" \
    org.opencontainers.image.source="https://github.com/eliasbenb/PlexAniBridge" \
    org.opencontainers.image.licenses="MIT"

ENV PYTHONPATH=/opt/venv/lib/python3.13/site-packages \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --chown=app:app . /app

ENTRYPOINT ["python", "/app/main.py"]

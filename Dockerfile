FROM python:3.13-alpine AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

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

RUN apk add --no-cache shadow su-exec

COPY --from=builder /opt/venv /opt/venv

LABEL maintainer="Elias Benbourenane <eliasbenbourenane@gmail.com>" \
    org.opencontainers.image.title="PlexAniBridge" \
    org.opencontainers.image.description="Synchronize your Plex watch history, ratings, and reviews with AniList" \
    org.opencontainers.image.authors="Elias Benbourenane <eliasbenbourenane@gmail.com>" \
    org.opencontainers.image.url="https://plexanibridge.elias.eu.org" \
    org.opencontainers.image.documentation="https://plexanibridge.elias.eu.org" \
    org.opencontainers.image.source="https://github.com/eliasbenb/PlexAniBridge" \
    org.opencontainers.image.licenses="MIT"

ENV PYTHONPATH=/opt/venv/lib/python3.13/site-packages \
    PYTHONUNBUFFERED=1 \
    PUID=1000 \
    PGID=1000 \
    UMASK=022 \
    SQLITE_VERSION=3500400 \
    PAB_DATA_PATH=/config

RUN wget "https://sqlite.org/2025/sqlite-tools-linux-x64-${SQLITE_VERSION}.zip" -O /tmp/sqlite-tools.zip && \
    unzip /tmp/sqlite-tools.zip -d /usr/local/bin && \
    rm /tmp/sqlite-tools.zip && \
    chmod +x /usr/local/bin/sqlite3

WORKDIR /app

COPY . /app
COPY ./scripts/docker_init.sh /init

RUN mkdir -p /config

VOLUME ["/config"]

EXPOSE 4848

ENTRYPOINT ["/init"]
CMD ["python", "/app/main.py"]

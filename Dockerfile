FROM python:3.13-alpine AS python-builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never

RUN apk add --no-cache git

WORKDIR /tmp

RUN --mount=type=bind,source=uv.lock,target=/tmp/uv.lock,ro \
    --mount=type=bind,source=pyproject.toml,target=/tmp/pyproject.toml,ro \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM node:24-alpine AS node-builder

WORKDIR /app

ENV CI=1 \
    PNPM_HOME=/pnpm \
    PNPM_STORE_DIR=/pnpm/store
ENV PATH="$PNPM_HOME:$PATH"

RUN corepack enable

RUN --mount=type=bind,source=frontend/pnpm-lock.yaml,target=/app/pnpm-lock.yaml,ro \
    --mount=type=bind,source=frontend/package.json,target=/app/package.json,ro \
    --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile

COPY ./frontend /app

RUN pnpm build

FROM python:3.13-alpine

RUN apk add --no-cache shadow su-exec

LABEL maintainer="Elias Benbourenane <eliasbenbourenane@gmail.com>" \
    org.opencontainers.image.title="PlexAniBridge" \
    org.opencontainers.image.description="The smart way to keep your AniList profile perfectly synchronized with your Plex library." \
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
    PAB_DATA_PATH=/config

WORKDIR /app

COPY . /app
COPY ./scripts/docker_init.sh /init

RUN rm -rf /app/frontend && \
    mkdir -p /config

COPY --from=python-builder /opt/venv /opt/venv
COPY --from=node-builder /app/build /app/frontend/build

VOLUME ["/config"]

EXPOSE 4848

ENTRYPOINT ["/init"]
CMD ["python", "/app/main.py"]

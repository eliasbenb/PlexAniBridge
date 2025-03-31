FROM python:3.13-alpine

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /bin/

LABEL maintainer="Elias Benbourenane <eliasbenbourenane@gmail.com>" \
    org.opencontainers.image.title="PlexAniBridge" \
    org.opencontainers.image.description="Synchronize your Plex watch history, ratings, and reviews with AniList" \
    org.opencontainers.image.authors="Elias Benbourenane <eliasbenbourenane@gmail.com>" \
    org.opencontainers.image.url="https://plexanibridge.elias.eu.org" \
    org.opencontainers.image.documentation="https://plexanibridge.elias.eu.org" \
    org.opencontainers.image.source="https://github.com/eliasbenb/PlexAniBridge" \
    org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --compile-bytecode

COPY . .

CMD ["uv", "run", "main.py", "--no-sync"]

FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

RUN apt-get update && \
    apt-get install -y \
    build-essential \
    libreadline-dev \
    wget \
    tar && \
    rm -rf /var/lib/apt/lists/*

ENV SQLITE_VERSION=3500400

RUN wget "https://sqlite.org/2025/sqlite-tools-linux-x64-${SQLITE_VERSION}.zip" -O /tmp/sqlite-tools.zip && \
    unzip /tmp/sqlite-tools.zip -d /usr/local/bin && \
    rm /tmp/sqlite-tools.zip && \
    chmod +x /usr/local/bin/sqlite3

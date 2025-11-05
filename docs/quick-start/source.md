---
title: Source
icon: material/wrench
---

## Requirements

- [Python 3.13+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [SQLite3](https://www.sqlite.org/download.html)
- [Git](https://git-scm.com/downloads)

## Setup

!!! tip

    Have a look at [the configuration page](../configuration.md) for a detailed list of configurable environment variables.

```shell
git clone https://github.com/eliasbenb/PlexAniBridge.git
cd PlexAniBridge

cp .env.example .env # Edit the .env file

# Setup environment
uv sync
uv run pab-deps-install
uv run pab-build

# Run PlexAniBridge
uv run pab-start
```

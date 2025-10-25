---
title: Source
icon: material/wrench
---

## Requirements

- [Python 3.13+](https://www.python.org/downloads/)
- [SQLite3](https://www.sqlite.org/download.html)
- [Git](https://git-scm.com/downloads)

## Setup

!!! tip

    Have a look at [the configuration page](../configuration.md) for a detailed list of configurable environment variables.

```shell
git clone https://github.com/eliasbenb/PlexAniBridge.git
cd PlexAniBridge

pip install -r requirements.txt

cp .env.example .env # Edit the .env file

python main.py
```

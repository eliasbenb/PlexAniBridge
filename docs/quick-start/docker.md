---
title: Docker
icon: material/docker
---

## Requirements

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- AMD64 or ARM64 CPU architecture (or build the image yourself for other architectures)

## Setup

### Docker Compose

Below is a PlexAniBridge Docker compose file with example values. Optional environment variables are commented out.

!!! tip

    Have a look at [the configuration page](../configuration.md) for a detailed list of configurable environment variables.

!!! note

    You can pin the image to a specific version or brancch by changing `latest` to a specific tag, e.g. `main`, `develop`, `v0.2.0-alpha.1`, etc.

```yaml title="compose.yaml"
--8<-- "compose.yaml"
```

To start the container, run:

```shell
docker compose -f compose.yaml up -d
```

### Docker CLI

Below is a minimal example of a Docker run command with only the required variables.

```shell
docker run \
  --name plexanibridge \
  -e ANILIST_TOKEN \
  -e PLEX_TOKEN \
  -e PLEX_USER \
  -e PLEX_URL \
  -e PLEX_SECTIONS \
  -v ./data:/app/data \
  ghcr.io/eliasbenb/plexanibridge:latest
```

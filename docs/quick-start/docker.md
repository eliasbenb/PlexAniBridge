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

```yaml title="compose.yaml"
--8<-- "compose.yaml"
```

To start the container, run:

```shell
docker compose -f compose.yaml up -d
```

!!! tip

    You can pin the image to a specific version or branch by changing `latest` to a specific tag. Some available tags are:
    
    - `latest`: The latest stable release
    - `beta`: The latest beta release (may be unstable)
    - `alpha`: The latest alpha release (may be unstable)
    - `vX.Y.Z`: A specific version from the [releases page](https://github.com/eliasbenb/PlexAniBridge/releases) (e.g. `v0.4.0`)
    - `main`: The latest commit on the `main` branch, which is usually tied to the latest release
    - `develop`: The latest commit on the `develop` branch (may be unstable)


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

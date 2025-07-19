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

!!! tip "PlexAniBridge Configuration"

    Have a look at [the configuration page](../configuration.md) for a detailed list of configurable environment variables.

!!! tip "Docker Variables"

    While configuring the Docker variables are not required, they are highly recommended to ensure proper functionality.

    Setting the `PUID` and `PGID` variables allows PlexAniBridge to run with the same permissions as the user running the container, which is important if you want to access files on the host system. You can find your user ID and group ID by running `id -u` and `id -g` in the terminal.

    The `TZ` variable sets the timezone for the container, which is useful for logging and scheduling tasks. You can search for your timezone in the [list of tz database time zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) Wikipedia page.

    ```yaml
    environment:
        PUID: 1000
        PGID: 1000
        TZ: Etc/UTC
    ```

```yaml title="compose.yaml"
--8<-- "docs/compose.yaml"
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
    - `X.Y.Z`: Alias of `vX.Y.Z` (e.g. `0.4.0`)
    - `main`: The latest commit on the `main` branch, which is usually tied to the latest release
    - `develop`: The latest commit on the `develop` branch (may be unstable)
    - `experimental`: The latest commit on the `experimental` branch (may be unstable)


### Docker CLI

Below is a minimal example of a Docker run command with only the required variables.

```shell
docker run \
  --name plexanibridge \
  -e ANILIST_TOKEN \
  -e PLEX_TOKEN \
  -e PLEX_USER \
  -e PLEX_URL \
  -v ./data:/app/data \
  ghcr.io/eliasbenb/plexanibridge:v0
```

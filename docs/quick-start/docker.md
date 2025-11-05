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

```yaml title="compose.yaml"
--8<-- "docs/compose.yaml"
```

!!! tip "PlexAniBridge Configuration"

    Have a look at [the configuration page](../configuration.md) for a detailed list of configurable environment variables.

!!! tip "Docker Variables"

    While configuring the Docker variables are not required, they are highly recommended to ensure proper functionality.

    Setting the `PUID` and `PGID` variables allows PlexAniBridge to run with the same permissions as the user running the container, which is important if you want to access files on the host system. You can find your user ID and group ID by running `id -u` and `id -g` in the terminal.

    The `UMASK` variable sets the default file permissions for new files created by the container. A common value is `022`, which gives read and execute permissions to everyone, but only write permissions to the owner.

    The `TZ` variable sets the timezone for the container, which is useful for logging and scheduling tasks. You can search for your timezone in the [list of tz database time zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) Wikipedia page.

    ```yaml
    environment:
        PUID: 1000
        PGID: 1000
        UMASK: 022
        TZ: Etc/UTC
    ```

To start the container, run:

```shell
docker compose -f compose.yaml up -d
```

!!! tip "Image Tags"

    You can pin the image to a specific version or branch by changing `latest` to a specific tag. Some available tags are:

    - `latest`: The latest stable release
    - `beta`: The latest beta release (may be unstable)
    - `alpha`: The latest alpha release (may be unstable)
    - `vX.Y.Z`: A specific version from the [releases page](https://github.com/eliasbenb/PlexAniBridge/releases) (e.g. `v1.0.0`)
    - `X.Y.Z`: Alias of `vX.Y.Z` (e.g. `1.0.0`)
    - `main`: The latest commit on the `main` branch, which is usually tied to the latest release
    - `develop`: The latest commit on the `develop` branch (may be unstable)
    - `experimental`: The latest commit on the `experimental` branch (may be unstable)

### Docker CLI

Below is a minimal example of a Docker run command with only the required variables.

```shell
docker run \
    --name plexanibridge \
    -e PUID=1000 \
    -e PGID=1000 \
    -e UMASK=022 \\
    -e TZ=Etc/UTC \
    -e PAB_ANILIST_TOKEN=eyJ... \
    -e PAB_PLEX_TOKEN=2Sb... \
    -e PAB_PLEX_USER=username \
    -e PAB_PLEX_URL=http://plex:32400 \
    -p 4848:4848 \
    -v /path/to/plexanibridge/data:/config \
    ghcr.io/eliasbenb/plexanibridge:v1
```

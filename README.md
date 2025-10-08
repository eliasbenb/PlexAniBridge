# <a href="https://plexanibridge.elias.eu.org"><img src="./docs/img/logo.png" alt="PlexAniBridge Logo" width="32" style="vertical-align: middle;"/></a> PlexAniBridge

The smart way to keep your AniList profile perfectly synchronized with your Plex library.

> [!IMPORTANT]
> Visit the [PlexAniBridge documentation](https://plexanibridge.elias.eu.org) for detailed setup instructions and usage information.

[![Discord Shield](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fdiscord.com%2Fapi%2Finvites%2Fey8kyQU9aD%3Fwith_counts%3Dtrue&query=%24.approximate_member_count&style=for-the-badge&logo=discord&label=Discord%20Users&labelColor=%23313338&color=%235865f2&cacheSeconds=10800)](https://discord.gg/ey8kyQU9aD) [![GitHub Shield](https://img.shields.io/github/stars/eliasbenb/PlexAniBridge?style=for-the-badge&logo=github&label=GitHub%20Stars&labelColor=%2324292e&color=%23f0f0f0)](https://github.com/eliasbenb/PlexAniBridge) [![Docker Pulls](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fghcr-badge.elias.eu.org%2Fapi%2Feliasbenb%2FPlexAniBridge%2Fplexanibridge&query=downloadCount&style=for-the-badge&logo=docker&label=Docker%20Pulls&color=2496ed)](https://github.com/eliasbenb/PlexAniBridge/pkgs/container/plexanibridge)


## Key Features

- **🔄 Comprehensive Synchronization**: Automatically syncs watch status, progress, ratings, reviews, and start/completion dates between Plex and AniList.
- **🎯 Smart Content Matching**: Uses a [curated mappings database](https://github.com/eliasbenb/PlexAniBridge-Mappings) with fuzzy title search fallback and support for custom mapping overrides.
- **⚡ Optimized Performance**: Intelligent batch processing, rate limiting, and caching to minimize API usage while maximizing sync speed.
- **👥 Multi-User & Multi-Profile**: Supports multiple Plex users (including Home users) with individual AniList accounts and configurable sync profiles.
- **🖥️ Web Dashboard**: Intuitive web interface with a real-time sync timeline, profile management, custom mapping editor, and log viewer.
- **🔧 Flexible Configuration**: Filter by library sections or genres and configure scanning modes (polling or periodic).
- **🛡️ Safe & Reliable**: Built-in dry run mode for testing and automatic AniList backups with a [restore script](./scripts/anilist_restore.py) for easy recovery.
- **🐳 Easy Deployment**: Docker-ready with easy and comprehensive environment variable configuration.

![Flowchart Diagram](https://mermaid.ink/img/pako:eNqtlN1q2zAUx19FqLC24MSfsh2zFdpmsEELo2UM1vRCkWVb1LaMJDftmjzDGLvYZW_2Arsbfan1ESY7cRLvAwqbr3R8_vqdc_6WdQcJjymMYJLzGcmwUODkbFIC_byVVNh7F4_3n762a2Bf7m8yznbGudwHYJNzt3Nut-tNTm8u9h7vPz-0S3BKY4bBORXXVOxfrjSHRxfPWZECKciL3UypSkamKfBsmDKV1dNaEwkvFS3VkPDCpDnDckrLqdkgD0t2JFicUvPVy8OxGXMiTQ0zc57yYVWmu8A8AD3hqqyOT5hUbXffuqjr6RRXFStT2WS_PPz4_rERFBS8HoMxVniKJV1Jt3wDg8HB_B1WJKMS0IpJ7bKct8W3POypCn7Nfte4reYMK614BgTVmllPtDF3QwOxbqyRY9V0Pm987U3aSo9rIbSRALfj5Pr1tnL9QVqtHjbn_KqutKQz5I86_W3ynKUNV96WZN5V3DJIqtuctjsSlufRjkNciixDKsGvaLTjIWzHo1U4mLFYZZFb3RiE51xEO0mS9DDN4EsORdiy4jWHkDCxrD7H-SunM2aJshw8SpI1ynLCkJCnojp_uvFCHHhozbJpQF3vqazlYVqCkjAZJXgN8kmAgrgPsjcgb4QsFPzKcv4jy_0nFjRgqv9BGClRUwMWVBS4CeFdU2cCVUYLOoGRXsZYXE3gpFzoPRUu33NedNsEr9MMRgnOpY7qSh98OmY4FbhYv9WHPKbimNelgpHje6OWAqM7eAMje-QN_QBZXhg6oe0gA97CyPWtIfICL0QuspHvoIUBP7RVraGPLN9DCPm-57rICw2o7zHFxenyHm2vUwPiWvFzff6XfS5-Alenxg0?type=png)

## Docker Quick Start
You'll need to have docker installed and be signed into your Plex server and anilist account. Then get your PlexAniBridge server running with docker and anything you watch on your Plex server should be synced to your anilist account.

1. Clone the repo `git clone https://github.com/eliasbenb/PlexAniBridge.git`
2. Open up `PlexAniBridge/docs/compose.yaml` and fill in `PAB_ANILIST_TOKEN` ([link](https://plexanibridge.elias.eu.org/configuration/#anilist_token)), `PAB_PLEX_TOKEN` ([link](https://plexanibridge.elias.eu.org/configuration/#plex_token)), `PAB_PLEX_USER` ([link](https://plexanibridge.elias.eu.org/configuration/#plex_user), can find it under Plex Server > Settings > Account) and `PLEX_URL` (you can use the private address found under Plex Server > Settings > Remote Access. This is the minimum to get started. You can customize the behavior later using the other settings
3. Install docker or [docker desktop](https://docs.docker.com/desktop/)
4. Use your CLI terminal of choice to `cd` into the repo you cloned and use docker to start up PlexAniBridge by running  `docker compose -f ./docs/compose.yaml up -d`
5. In your web browser go to `localhost:4848` to access the web UI which will show you sync status and logs
   
The `compose.yaml` should look something like this
```yaml
services:
    plexanibridge:
        image: ghcr.io/eliasbenb/plexanibridge:latest
        environment:
            PUID: 1000
            PGID: 1000
            UMASK: 022
            TZ: Etc/UTC
            PAB_ANILIST_TOKEN: eyJ0ex12345
            PAB_PLEX_TOKEN: nsF6abcdef 
            PAB_PLEX_USER: myusername123
            PAB_PLEX_URL: http://192.168.0.229:32400
        volumes:
            - /path/you/cloned/to/PlexAniBridge/data:/config
        ports:
         - 4848:4848
        restart: unless-stopped
```

## Web UI Screenshot

![Web UI Screenshot](./docs/img/screenshots/timeline.png)

_View more screenshots in the [documentation](https://plexanibridge.elias.eu.org/web/screenshots)_

# <a href="https://plexanibridge.elias.eu.org"><img src="./docs/img/logo.png" alt="PlexAniBridge Logo" width="32" style="vertical-align: middle;"/></a> PlexAniBridge

PlexAniBridge is a tool designed to keep your AniList profile automatically synced with your Plex activity. Whether you're tracking your watch progress, ratings, or reviews, PlexAniBridge has you covered.

> [!IMPORTANT]
> Visit the [PlexAniBridge documentation](https://plexanibridge.elias.eu.org) for detailed setup instructions and usage information.

[![Discord Shield](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fdiscord.com%2Fapi%2Finvites%2Fey8kyQU9aD%3Fwith_counts%3Dtrue&query=%24.approximate_member_count&style=for-the-badge&logo=discord&label=Discord%20Users&labelColor=%23313338&color=%235865f2&cacheSeconds=10800)](https://discord.gg/ey8kyQU9aD) [![GitHub Shield](https://img.shields.io/github/stars/eliasbenb/PlexAniBridge?style=for-the-badge&logo=github&label=GitHub%20Stars&labelColor=%2324292e&color=%23f0f0f0)](https://github.com/eliasbenb/PlexAniBridge) [![Docker Pulls Shield](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fipitio.github.io%2Fbackage%2Feliasbenb%2FPlexAniBridge%2Fplexanibridge.json&query=downloads&style=for-the-badge&logo=docker&label=Docker%20Pulls&color=2496ed&link=https%3A%2F%2Fgithub.com%2Feliasbenb%2FPlexAniBridge%2Fpkgs%2Fcontainer%2Fplexanibridge)](https://github.com/eliasbenb/PlexAniBridge/pkgs/container/plexanibridge)

## Key Features

- **Comprehensive Synchronization**: Tracks watch status, progress, repeat counts, ratings, text reviews, and start/end dates.
- **Smart Content Mapping**: Matches Plex content (movies, shows, specials, etc.) to AniList using [a robust mappings database](https://github.com/eliasbenb/PlexAniBridge-Mappings) with fuzzy title search as a fallback and the ability to add custom mappings.
- **Efficient Scanning**: Supports various modes of scanning like [partial](https://plexanibridge.elias.eu.org/configuration#full_scan), [full](https://plexanibridge.elias.eu.org/configuration#full_scan), or [polling](https://plexanibridge.elias.eu.org/configuration#polling_scan) scans to minimize API usage.
- **Flexible Scheduling**: Configurable [synchronization intervals](https://plexanibridge.elias.eu.org/configuration#sync_interval) in addition to polling capabilities.
- **Multi-User Support**: Sync multiple [Plex users](https://plexanibridge.elias.eu.org/configuration#plex_user) and home users with their respective [AniList users](https://plexanibridge.elias.eu.org/configuration#anilist_token).
- **Plex Online Metadata**: Choose between using local metadata (default) or the online Plex API for enhanced tracking across multiple servers with persistent tracking data.
- **Optimized Performance**: Intelligent caching of requests to minimize API rate limits.
- **Easy Deployment**: Fully compatible with [Docker deployments](https://plexanibridge.elias.eu.org/quick-start/docker) 🐳.

## Docker Quick Start

```yaml
services:
  plexanibridge:
    image: ghcr.io/eliasbenb/plexanibridge:latest
    environment:
      TZ: America/New_York
      ANILIST_TOKEN: eyJ...
      PLEX_TOKEN: 2Sb...
      PLEX_USER: username
      PLEX_URL: http://plex:32400
      PLEX_SECTIONS: '["Anime", "Anime Movies"]'
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

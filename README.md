# <a href="https://plexanibridge.elias.eu.org"><img src="./docs/img/logo.png" alt="PlexAniBridge Logo" width="32" style="vertical-align: middle;"/></a> PlexAniBridge

PlexAniBridge is a tool designed to keep your AniList profile automatically synced with your Plex activity. Whether you're tracking your watch progress, ratings, or reviews, PlexAniBridge has you covered.

> [!IMPORTANT]
> Visit the [PlexAniBridge documentation](https://plexanibridge.elias.eu.org) for detailed setup instructions and usage information.

[![Discord Shield](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fdiscord.com%2Fapi%2Finvites%2Fey8kyQU9aD%3Fwith_counts%3Dtrue&query=%24.approximate_member_count&style=for-the-badge&logo=discord&label=Discord%20Users&labelColor=%23313338&color=%235865f2&cacheSeconds=10800)](https://discord.gg/ey8kyQU9aD) [![GitHub Shield](https://img.shields.io/github/stars/eliasbenb/PlexAniBridge?style=for-the-badge&logo=github&label=GitHub%20Stars&labelColor=%2324292e&color=%23f0f0f0)](https://github.com/eliasbenb/PlexAniBridge) [![Docker Pulls](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fghcr-badge.elias.eu.org%2Fapi%2Feliasbenb%2FPlexAniBridge%2Fplexanibridge&query=downloadCount&style=for-the-badge&logo=docker&label=Docker%20Pulls&color=2496ed)](https://github.com/eliasbenb/PlexAniBridge/pkgs/container/plexanibridge)


## Key Features

- **Comprehensive Synchronization**: Tracks watch status, progress, repeat counts, ratings, text reviews, and start/end dates.
- **Smart Content Mapping**: Matches Plex content (movies, shows, specials, etc.) to AniList using [a robust mappings database](https://github.com/eliasbenb/PlexAniBridge-Mappings) with fuzzy title search as a fallback and the ability to add custom mappings.
- **Efficient Scanning**: Supports various modes of scanning like [partial](https://plexanibridge.elias.eu.org/configuration#full_scan), [full](https://plexanibridge.elias.eu.org/configuration#full_scan), or [polling](https://plexanibridge.elias.eu.org/configuration#polling_scan) scans to minimize API usage.
- **Flexible Scheduling**: Configurable [synchronization intervals](https://plexanibridge.elias.eu.org/configuration#sync_interval) in addition to polling capabilities.
- **Multi-User Support**: Sync multiple [Plex users](https://plexanibridge.elias.eu.org/configuration#plex_user) and home users with their respective [AniList users](https://plexanibridge.elias.eu.org/configuration#anilist_token).
- **Plex Online Metadata**: Choose between using local metadata (default) or the online Plex API for enhanced tracking across multiple servers with persistent tracking data.
- **Optimized Performance**: Intelligent caching of requests to minimize API rate limits.
- **Easy Deployment**: Fully compatible with [Docker deployments](https://plexanibridge.elias.eu.org/quick-start/docker) 🐳.

![Flowchart Diagram](https://mermaid.ink/img/pako:eNqdVGtr2zAU_StCgZKCE_xMbTEKyfJlkEBpKYMl_aBEsi3iWEaS81iT_z5JVkg29igTxuheXZ1z7z2S3uGaEwoRzCu-X5dYKDB7XtZAj1dJRX9h_m_3neepoodF3_zBnBKGwQsVOyru39zyeLIwi-OaTQQjBXX-8WzR174Zk-oSOsdNw-pi0XcTMMUKr7CkLqCLku2qELgpwRLqr_NdMgODwePpK1brkkqAa7aln1bi8RmrW3NMiLOA4qBiK4HF8WTr6NBoTT7AZys2fF3VrM65QbfsoNRlcXF07LoWCe6AoDtG9_JkevI7pr-RjSeW67UhtphG8JxVtpyXY722jkJQKa8eQRuK1a3j10SuS1IZje9MPsASnLQ-Nyn-oxMuuRnnGwnaxjX3y1TDOCmvwRdtzYYnwXeM6HLcQei2_Lk7Lg11rKgl1S2oUC9OcEAyTyrBNxT1oihy88GeEVWisDl4a15xgXp5nv-EYSTsQGiCfZ_8D8h45iCCJAyj8OMQ0INbKraYEX3T3g3kEqqSbukSIj0lWGxMl886DreKG6UgUqKlHhS8LUqIclxJbbX2UEwZ1upsLyENrr9xfmtC9A4PEAVxOgzSh3iUxWkYh0GaevAIURSGwzDK0lEajGJ_FCZnD363AP4wfUh8PaIgTbIs8fWGQpisXTJaJyo-87ZWEIWZB_V90Id_3j0h9iU5_wBX-1zo?type=png)

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
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

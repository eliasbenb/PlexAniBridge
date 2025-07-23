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
- **🔧 Flexible Configuration**: Filter by library sections or genres and configure scanning modes (polling or periodic).
- **🛡️ Safe & Reliable**: Built-in dry run mode for testing and automatic AniList backups with a [restore script](./scripts/anilist_restore.py) for easy recovery.
- **🐳 Easy Deployment**: Docker-ready with easy and comprehensive environment variable configuration.

![Flowchart Diagram](https://mermaid.ink/img/pako:eNqdVGtr2zAU_StCgZKCE_xMbTEKyfJlkEBpKYMl_aBEsi3iWEaS81iT_z5JVkg29igTxuheXZ1z7z2S3uGaEwoRzCu-X5dYKDB7XtZAj1dJRX9h_m_3neepoodF3_zBnBKGwQsVOyru39zyeLIwi-OaTQQjBXX-8WzR174Zk-oSOsdNw-pi0XcTMMUKr7CkLqCLku2qELgpwRLqr_NdMgODwePpK1brkkqAa7aln1bi8RmrW3NMiLOA4qBiK4HF8WTr6NBoTT7AZys2fF3VrM65QbfsoNRlcXF07LoWCe6AoDtG9_JkevI7pr-RjSeW67UhtphG8JxVtpyXY722jkJQKa8eQRuK1a3j10SuS1IZje9MPsASnLQ-Nyn-oxMuuRnnGwnaxjX3y1TDOCmvwRdtzYYnwXeM6HLcQei2_Lk7Lg11rKgl1S2oUC9OcEAyTyrBNxT1oihy88GeEVWisDl4a15xgXp5nv-EYSTsQGiCfZ_8D8h45iCCJAyj8OMQ0INbKraYEX3T3g3kEqqSbukSIj0lWGxMl886DreKG6UgUqKlHhS8LUqIclxJbbX2UEwZ1upsLyENrr9xfmtC9A4PEAVxOgzSh3iUxWkYh0GaevAIURSGwzDK0lEajGJ_FCZnD363AP4wfUh8PaIgTbIs8fWGQpisXTJaJyo-87ZWEIWZB_V90Id_3j0h9iU5_wBX-1zo?type=png)

## Docker Quick Start

```yaml
services:
  plexanibridge:
    image: ghcr.io/eliasbenb/plexanibridge:v1
    environment:
      PUID: 1000
      PGID: 1000
      TZ: Etc/UTC
      PAB_ANILIST_TOKEN: eyJ...
      PAB_PLEX_TOKEN: 2Sb...
      PAB_PLEX_USER: username
      PAB_PLEX_URL: http://plex:32400
    volumes:
      - /path/to/plexanibridge/data:/config
    restart: unless-stopped
```

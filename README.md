# PlexAniBridge

PlexAniBridge is a tool designed to keep your AniList profile automatically synced with your Plex activity. Whether you're tracking your watch progress, ratings, or reviews, PlexAniBridge has you covered.

> [!IMPORTANT]  
> Visit the [PlexAniBridge documentation](https://plexanibridge.elias.eu.org) for detailed setup instructions and usage information.

[![Discord Shield](https://discord.com/api/guilds/1329899003814609067/widget.png?style=shield)](https://discord.gg/ey8kyQU9aD)

## Key Features

- **Comprehensive Synchronization**: Tracks watch status, progress, repeat counts, ratings, text reviews, and start/end dates.
- **Smart Content Mapping**: Matches Plex content (movies, shows, specials, etc.) to AniList using [a robust mappings database](https://github.com/eliasbenb/PlexAniBridge-Mappings) with fuzzy title search as a fallback and the ability to add custom media mappings.
- **Efficient Scanning**: Supports various modes of scanning like [partial](https://plexanibridge.elias.eu.org/configuration#full_scan), [full](https://plexanibridge.elias.eu.org/configuration#full_scan), or [polling](https://plexanibridge.elias.eu.org/configuration#polling_scan) scans to minimize API usage.
- **Flexible Scheduling**: Configurable [synchronization intervals](https://plexanibridge.elias.eu.org/configuration#sync_interval) in addition to polling capabilities.
- **Multi-User Support**: Sync multiple [Plex users](https://plexanibridge.elias.eu.org/configuration#plex_user) and home users with their respective [AniList users](https://plexanibridge.elias.eu.org/configuration#anilist_token).
- **Optimized Performance**: Intelligent caching of requests to minimize API rate limits.
- **Easy Deployment**: Fully compatible with [Docker deployments](https://plexanibridge.elias.eu.org/quick-start/docker) 🐳.

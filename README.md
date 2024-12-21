# PlexAniBridge

PlexAniBridge is a synchronization tool that automatically keeps your AniList profile up-to-date based on your Plex watching activity. The tool is designed to be extremely light-weight and work with both movies and shows.

## Features

- Synchronize watch statusm, watch progress, repeat counts, rating scores, text reviews, and start/end dates
- Mapping Plex movies, shows, seasons, episode ranges, and specials to AniList using [Kometa mappings](https://github.com/Kometa-Team/Anime-IDs) with fuzzy title search as a fallback
- Partial scanning support — only consider items added/updated/rated since the last sync
- Scheduled sync jobs with configurable polling capabilities
- Intelligent caching of Plex and AniList requests to reduce rate limits
- [Docker](#docker) 🐳 deployments

## Quick Start

### Docker

> [!TIP]
> Have a look at [the configuration section](#Configuration) for a full list of configurable environment variables.
>
> Below is a minimal example of a Docker compose with only the required variables. For a full example, see [compose.yaml](./compose.yaml).

```yaml
services:
  plexanibridge:
    image: ghcr.io/eliasbenb/plexanibridge:latest # :main, :develop, :v0.1.0, etc.
    environment:
      ANILIST_TOKEN: eyJ0eXALOiJKV1DiLCJFbGciOiJSUzI...
      PLEX_URL: http://localhost:32400
      PLEX_TOKEN: 2Sb...
      PLEX_SECTIONS: '["Anime", "Anime Movies"]'
    volumes:
      - ./data:/app/data
      # - ./logs:/app/logs
    restart: unless-stopped
```

### Source

```bash
git clone https://github.com/eliasbenb/PlexAniBridge.git
cd PlexAniBridge

pip install -r requirements.txt # Python 3.10+
cp .env.example .env # Edit the .env file

python main.py
```

## Configuration

> [!NOTE]
> Any list item prefixed with `*` is required to be set for the script to run.

- `*ANILIST_TOKEN`: AniList API access token [get one here](https://anilist.co/login?apiVersion=v2&client_id=23079&response_type=token)
- `*PLEX_URL`: URL to your Plex server (default: `http://localhost:32400`)
- `*PLEX_TOKEN`: Plex API access token [get one here](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)
- `*PLEX_SECTIONS`: List of Plex library sections to consider
  - The syntax is the same as a Python list. E.g. `["Anime", "Anime Movies"]`
- `SYNC_INTERVAL`: Interval in seconds between each sync job. (default: `3600`)
  - Set as `-1` to disable scheduled sync jobs. This will cause the script to run only once and exit.
  - When `PARTIAL_SCAN` is enabled, it can be benificial to lower the interval for quicker syncs. In this case, an interval of `300` (5 minutes) is recommended.
- `PARTIAL_SCAN`: Only consider items added/updated/rated since last sync. (default: `True`)
  - The initial sync will always be a full sync, regardless of this setting.
  - Any subsequent syncs will only consider items added/updated/rated since the last sync's start time.
- `DESTRUCTIVE_SYNC`: Regressively update AniList data to match Plex regardless of existing data. (default: `False`).
  - When syncing items, the script typically only updates fields on AniList that are less than the corresponding fields on Plex. With `DESTRUCTIVE_SYNC` enabled, this is no longer the case.
  - For example, if the watch progress on AniList is greater than the watch progress on Plex, the progress on AniList will be lowered to match the progress on Plex.
  - Destructive syncs apply to every field (e.g. status, watch progress, score, repeat, notes, start date, end date, etc.).
  - In addition to regressive updates, destructive syncs also allow for deleting items from AniList lists. This can occur if the item exists in the Plex library but has no status (no watch history and is not watchlisted).
  - Not recommended unless you know what you're doing.
- `EXCLUDED_SYNC_FIELDS`: List of fields to exclude from sync (default: `[]`)
  - The syntax is the same as a Python list. E.g. `["notes", "score"]`
  - This is useful if you don't want to sync certain fields, such as notes or scores.
  - All available fields are: `["status", "score", "progress", "repeat", "notes", "started_at", "completed_at"]`
- `DATA_PATH`: Path to the data folder that will store the database and custom mappings (default: `./data`)
- `LOG_LEVEL`: Logging level (default: `INFO`)
  - Possible values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- `DRY_RUN`: Disables modifying AniList data (default: `False`)
  - When enabled, the script will only log what it would do, without actually doing it.
  - Use it when running the script for the first time to make sure everything is working as expected.
- `FUZZY_SEARCH_THRESHOLD`: Fuzzy search threshold for matching anime titles (default: `90`)
  - Sometimes no match is found between Plex and AniList. In this case, the script will try to find a match by searching AniList for similar titles.
  - The threshold is a percentage of similarity between two titles. Results below this threshold will be ignored.
  - Lower values will result in more matches, but also more false positives.
  - Higher values will result in fewer matches, but also fewer false positives.

## Notices

> [!WARNING]
> This project is still in development, while it is usable, I cannot guarantee that it will be stable for every release.

> [!IMPORTANT]
> To prevent data loss, PlexAniBridge automatically creates backups of your AniList data before syncing. These backups are stored under the data folder (set in `DATA_PATH`) in the `backups` directory. These backups are automatically deleted after 7 days.

## TODO

> [!WARNING]
> This project is still in development, while it is usable, I cannot guarantee that it will be stable for every release.

- [ ] Custom mapping support
- [ ] AniList recovery script to restore from the automatically created backups in the data folder

## Special Thanks/Dependencies

- [Kometa Mappings](https://github.com/Kometa-Team/Anime-IDs)
- [Python-PlexAPI](https://github.com/pkkid/python-plexapi)

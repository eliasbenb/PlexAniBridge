# PlexAniBridge

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
      - ./db:/app/db
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
  - The only exception to the above rule is when the Plex value is 0 or None. E.g. if the watch progress on Plex is 0, the watch progress on AniList will not be destructively updated.
  - Destructive syncs apply to every field (e.g. status, watch progress, score, repeat, notes, start date, end date, etc.).
  - Not recommended unless you know what you're doing.
- `DB_PATH`: Path to the SQLite database file (default: `./db/plexanibridge.db`)
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

## TODO

> [!WARNING]
> This project is still in development, while it is usable, I cannot guarantee that it will always work as expected.

- [x] Sync watch progress
- [x] Sync rating scores
- [x] Sync text-based reviews/notes
- [x] Sync status
- [x] Sync start/end dates
- [x] Sync repeat count
- [x] Partial scanning, only consider items added/updated/rated since last sync
- [x] Scheduled sync jobs
- [x] Match anime with Kometa mappings
- [x] Match anime with titles
- [x] Docker support
- [x] Destructive sync (fully replace AniList data to match Plex regardless of existing data)
- [x] Cache AniList responses to avoid rate limits
- [ ] Special/OVA/ONA support
- [ ] Custom mapping support
- [ ] Config option for users to choose which fields to sync (status, progress, repeats, rating, notes, start/end dates)

## Special Thanks/Dependencies

- [Kometa Mappings](https://github.com/Kometa-Team/Anime-IDs)
- [Python-PlexAPI](https://github.com/pkkid/python-plexapi)

# PlexAniBridge

## Quick Start

### Docker

> [!TIP]
> Have a look at [compose.yaml](./compose.yaml) for a full compose file with comments for each config option.

```yaml
services:
  plexanibridge:
    image: ghcr.io/eliasbenb/plexanibridge:main
    environment:
      # SYNC_INTERVAL: 3600
      # PARTIAL_SCAN: False
      ANILIST_TOKEN: eyJ0eXALOiJKV1DiLCJFbGciOiJSUzI...
      ANILIST_USER: username
      PLEX_URL: http://localhost:32400
      PLEX_TOKEN: 2Sb...
      PLEX_SECTIONS: '["Anime", "Anime Movies"]'
      PLEX_USER: username
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

## TODO

> [!WARNING]
> This project is still in development, while it is usable, I cannot guarantee that it will always work as expected.

- [x] Sync watch progress
- [x] Sync rating scores
- [x] Sync text-based reviews/notes
- [x] Sync status (watching, completed, dropped, paused, planning)
- [x] Partial scanning, only consider items added/updated/rated since last sync
- [x] Scheduled sync jobs
- [x] Match anime with Kometa mappings
- [x] Match anime with titles
- [x] Docker support
- [ ] Destructive sync (fully replace AniList data to match Plex regardless of existing data)
- [ ] Multi-directional sync
- [ ] Sync start/end dates
- [ ] Sync repeat count
- [ ] Special/OVA/ONA support
- [ ] Cache AniList responses to avoid rate limits
- [ ] Use AniList relations for better and quicker matching

## Special Thanks/Dependencies

- [Kometa Mappings](https://github.com/Kometa-Team/Anime-IDs)
- [Python-PlexAPI](https://github.com/pkkid/python-plexapi)

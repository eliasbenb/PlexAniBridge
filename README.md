# PlexAniBridge

## Quick Start

### Docker

> [!TIP]
> Have a look at [compose.yaml](./compose.yaml) for a full compose file with comments for each config option.

```yaml
services:
  plexanibridge:
    image: ghcr.io/eliasbenb/plexanibridge
    environment:
      SYNC_INTERVAL: 3600
      ANILIST_TOKEN: eyJ0eXALOiJKV1DiLCJFbGciOiJSUzI...
      ANILIST_USER: username
      PLEX_URL: http://localhost:32400
      PLEX_TOKEN: 2Sb...
      PLEX_SECTIONS: '["Anime", "Anime Movies"]'
      PLEX_USER: username
    # volumes:
    #   - ./logs:/app/logs
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

- [x] Sync watched status
- [x] Sync watch progress
- [x] Sync rating scores
- [x] Match anime with Kometa mappings
- [x] Match anime with titles
- [x] Scheduled sync
- [x] Docker
- [ ] Sync reviews/notes
- [ ] Multi-directional sync
- [ ] Partial scanning, only sync items in Plex's recent history
- [ ] Cache AniList responses
- [ ] Use AniList relations for better and quicker matching

## Special Thanks/Dependencies

- [Kometa Mappings](https://github.com/Kometa-Team/Anime-IDs)
- [Python-PlexAPI](https://github.com/pkkid/python-plexapi)

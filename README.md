# PlexAniBridge

## Quick Start

### Docker

Have a look at [compose.yaml](./compose.yaml) for a full compose file with comments for each config option.

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

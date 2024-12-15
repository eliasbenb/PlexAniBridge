from src.core import BridgeClient
from src.settings import config

if __name__ == "__main__":
    bridge = BridgeClient(
        anilist_token=config.ANILIST_TOKEN,
        anilist_user=config.ANILIST_USER,
        animap_sync_interval=config.ANIMAP_SYNC_INTERVAL,
        plex_url=config.PLEX_URL,
        plex_token=config.PLEX_TOKEN,
        plex_sections=config.PLEX_SECTIONS,
        plex_user=config.PLEX_USER,
        fuzzy_search_threshold=config.FUZZY_SEARCH_THRESHOLD,
    )
    bridge.sync()

"""Provider factory helpers."""

from src.config.settings import AniBridgeProfileConfig, PlexMetadataSource
from src.core.providers.library import LibraryProvider
from src.core.providers.list import ListProvider
from src.providers.anilist.list import AniListListProvider
from src.providers.plex.library import PlexLibraryProvider
from src.providers.plex_metadata.client import PlexOnlineLibraryProvider


def build_library_provider(profile: AniBridgeProfileConfig) -> LibraryProvider:
    """Instantiate the configured library provider for the profile."""
    provider_cls = (
        PlexOnlineLibraryProvider
        if profile.plex_metadata_source == PlexMetadataSource.ONLINE
        else PlexLibraryProvider
    )

    config = {
        "url": profile.plex_url,
        "token": profile.plex_token.get_secret_value(),
        "user": profile.plex_user,
        "sections": profile.plex_sections,
        "genres": profile.plex_genres,
    }

    return provider_cls(config=config)


def build_list_provider(
    profile_name: str, profile: AniBridgeProfileConfig
) -> ListProvider:
    """Instantiate the configured list provider for the profile."""
    backup_dir = profile.data_path / "backups"

    config = {
        "token": profile.anilist_token.get_secret_value(),
        "dry_run": profile.dry_run,
        "profile_name": profile_name,
        "backup_dir": str(backup_dir),
    }

    return AniListListProvider(config=config)

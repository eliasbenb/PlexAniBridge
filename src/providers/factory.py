"""Provider factory helpers."""

from anibridge_anilist_provider.list import AniListListProvider
from anibridge_plex_provider.library import PlexLibraryProvider
from anibridge_providers.library import LibraryProvider
from anibridge_providers.list import ListProvider

from src.config.settings import AniBridgeProfileConfig


def build_library_provider(profile: AniBridgeProfileConfig) -> LibraryProvider:
    """Instantiate the configured library provider for the profile."""
    config = {
        "url": profile.plex_url,
        "token": profile.plex_token.get_secret_value(),
        "user": profile.plex_user,
        "sections": profile.plex_sections,
        "genres": profile.plex_genres,
    }

    return PlexLibraryProvider(config=config)


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

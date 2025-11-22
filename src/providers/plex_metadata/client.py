"""Plex metadata (online) library provider implementation."""

from plexapi.video import Video

from src.exceptions import PlexUserNotFoundError
from src.providers.plex.client import PlexClient, PlexClientBundle
from src.providers.plex.library import PlexLibraryProvider, PlexLibrarySection
from src.providers.plex_metadata.metadata import PlexMetadataServer

__all__ = ["PlexOnlineLibraryProvider"]


class _MetadataPlexClient(PlexClient):
    def _create_client_bundle(self) -> PlexClientBundle:
        bundle = super()._create_client_bundle()
        if bundle.target_user is not None:
            raise PlexUserNotFoundError(
                "Plex metadata provider requires admin credentials"
            )

        metadata_client = PlexMetadataServer(self._config.url, self._config.token)
        return PlexClientBundle(
            admin_client=bundle.admin_client,
            user_client=metadata_client,
            account=bundle.account,
            target_user=None,
            user_id=bundle.user_id,
            display_name=bundle.display_name,
            is_admin=bundle.is_admin,
        )


class PlexOnlineLibraryProvider(PlexLibraryProvider):
    """Library provider backed by Plex's online metadata service."""

    NAMESPACE = "plex-online"

    def is_on_continue_watching(self, section: PlexLibrarySection, item: Video) -> bool:
        """Continue Watching is not supported for the metadata service."""
        return False

    def _create_client(self) -> PlexClient:
        return _MetadataPlexClient(
            config=self._client_config,
            section_filter=self._section_filter,
            genre_filter=self._genre_filter,
        )

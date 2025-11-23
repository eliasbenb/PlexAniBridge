"""Runtime models for Plex-backed library providers."""

from collections.abc import Sequence
from datetime import datetime
from typing import Literal, cast

import plexapi.library as plexapi_library
import plexapi.video as plexapi_video

from src import log
from src.core.providers.library import (
    ExternalId,
    HistoryEntry,
    LibraryEpisode,
    LibraryMedia,
    LibraryMovie,
    LibraryProvider,
    LibrarySeason,
    LibrarySection,
    LibraryShow,
    LibraryUser,
    MediaKind,
)

from .client import PlexClient, PlexClientConfig
from .community import PlexCommunityClient

_GUID_NAMESPACE_MAP: dict[str, str] = {
    # Plex Movie/Series agents
    "imdb": "imdb",
    "tmdb": "tmdb",
    "tvdb": "tvdb",
    # Legacy Plex agents
    "com.plexapp.agents.imdb": "imdb",
    "com.plexapp.agents.thetvdb": "tvdb",
    "com.plexapp.agents.themoviedb": "tmdb",
    "com.plexapp.agents.tmdb": "tmdb",
}


class PlexLibrarySection(LibrarySection):
    """Concrete ``LibrarySection`` backed by a python-plexapi library section."""

    def __init__(
        self, provider: PlexLibraryProvider, item: plexapi_library.LibrarySection
    ) -> None:
        """Represent a Plex library section.

        Args:
            provider (PlexLibraryProvider): The owning Plex library provider.
            item (plexapi_library.LibrarySection): The underlying Plex section.
        """
        self._provider = provider
        self._section = item

        self.key = str(item.key)
        self.title = item.title
        self.media_kind = MediaKind.SHOW if item.type == "show" else MediaKind.MOVIE

    def provider(self) -> PlexLibraryProvider:
        """Return the provider that supplies this section.

        Returns:
            PlexLibraryProvider: The owning Plex library provider.
        """
        return self._provider

    def raw(self):
        """Expose the underlying Plex section object for provider access.

        Returns:
            plexapi_library.LibrarySection: The raw Plex section.
        """
        return self._section


class PlexLibraryMedia(LibraryMedia):
    """Common behaviour for Plex-backed library media objects."""

    def __init__(
        self,
        provider: PlexLibraryProvider,
        section: PlexLibrarySection,
        item: plexapi_video.Video,
        kind: MediaKind,
    ) -> None:
        """Initialize the media wrapper.

        Args:
            provider (PlexLibraryProvider): The owning Plex library provider.
            section (PlexLibrarySection): The parent Plex library section.
            item (plexapi_video.Video): The underlying Plex media item.
            kind (MediaKind): The kind of media represented.
        """
        self._provider = provider
        self._section = section
        self._item = item
        self.media_kind = kind
        self.key = str(item.ratingKey)
        self.title = item.title

    @property
    def on_watching(self) -> bool:
        """Check if the media item is on the user's current watching list."""
        return self._provider.is_on_continue_watching(self._section, self._item)

    @property
    def on_watchlist(self) -> bool:
        """Check if the media item is on the user's watchlist."""
        if not isinstance(self._item, (plexapi_video.Movie, plexapi_video.Show)):
            return False
        try:
            return bool(self._item.onWatchlist())
        except Exception:
            return False

    @property
    def user_rating(self) -> int | None:
        """Return the user rating for this media item on a 0-100 scale."""
        if self._item.userRating is None:
            return None
        try:
            # Normalize to a 0-100 scale
            return round(float(self._item.userRating) * 10)
        except (TypeError, ValueError):
            return None

    @property
    def view_count(self) -> int:
        """Return the number of times this media item has been viewed."""
        return self._item.viewCount or 0

    async def history(self) -> Sequence[HistoryEntry]:
        """Fetch the viewing history for this media item.

        Returns:
            Sequence[HistoryEntry]: A sequence of history entries for this media item.
        """
        return await self._provider.get_history(self._item)

    def ids(self) -> Sequence[ExternalId]:
        """Extract external IDs from the Plex media item's GUIDs.

        Returns:
            Sequence[ExternalId]: A sequence of external identifiers.
        """
        ids: dict[tuple[str, str], ExternalId] = {}

        if not isinstance(
            self._item,
            (
                plexapi_video.Movie,
                plexapi_video.Show,
                plexapi_video.Season,
                plexapi_video.Episode,
            ),
        ):
            raise TypeError(
                "ids property is only available for Movie, Show, Season, and Episode"
            )

        for guid in self._item.guids:
            if not guid.id:
                continue

            namespace, value = ("unknown", guid.id)

            if "://" in guid.id:
                prefix, suffix = guid.id.split("://", 1)
                namespace = _GUID_NAMESPACE_MAP.get(prefix, prefix or "unknown")
                value = suffix.split("?", 1)[0]

            key = (namespace, value)
            ids.setdefault(key, ExternalId(namespace=namespace, value=value))

        if self._item.guid:
            value = self._item.guid.rsplit("/", 1)[-1]
            ids.setdefault(("plex", value), ExternalId("plex", value))

        return tuple(ids.values())

    def provider(self) -> PlexLibraryProvider:
        """Return the provider that owns this entity.

        Returns:
            PlexLibraryProvider: The owning Plex library provider.
        """
        return self._provider

    def raw(self) -> plexapi_video.Video:
        """Expose the underlying Plex media object.

        Returns:
            plexapi_video.Video: The raw Plex media item.
        """
        return self._item

    async def review(self) -> str | None:
        """Fetch the user's review for this media item, if available.

        Returns:
            str | None: The user's review text, or None if not reviewed.
        """
        return await self._provider.get_review(self._item)

    def section(self) -> PlexLibrarySection:
        """Return the library section this media item belongs to.

        Returns:
            PlexLibrarySection: The parent library section.
        """
        if self._section is not None:
            return self._section

        raw_section = self._item.section()
        self._section = PlexLibrarySection(self._provider, raw_section)
        return self._section


class PlexLibraryMovie(PlexLibraryMedia, LibraryMovie):
    """Concrete ``LibraryMovie`` wrapper for python-plexapi ``Movie`` objects."""

    __slots__ = ()

    def __init__(
        self,
        provider: PlexLibraryProvider,
        section: PlexLibrarySection,
        item: plexapi_video.Movie,
    ) -> None:
        """Initialize the movie wrapper.

        Args:
            provider (PlexLibraryProvider): The owning Plex library provider.
            section (PlexLibrarySection): The parent Plex library section.
            item (plexapi_video.Movie): The underlying Plex movie item.
        """
        self._provider = provider
        self._section = section
        self._item = item
        self.media_kind = MediaKind.MOVIE
        self.key = str(item.ratingKey)
        self.title = item.title


class PlexLibraryShow(PlexLibraryMedia, LibraryShow):
    """Concrete ``LibraryShow`` wrapper for Plex ``Show`` objects."""

    __slots__ = ()

    def __init__(
        self,
        provider: PlexLibraryProvider,
        section: PlexLibrarySection,
        item: plexapi_video.Show,
    ) -> None:
        """Initialize the show wrapper.

        Args:
            provider (PlexLibraryProvider): The owning Plex library provider.
            section (PlexLibrarySection): The parent Plex library section.
            item (plexapi_video.Show): The underlying Plex show item.
        """
        self._provider = provider
        self._section = section
        self._item = item
        self.media_kind = MediaKind.SHOW
        self.key = str(item.ratingKey)
        self.title = item.title

    @property
    def ordering(self) -> Literal["tmdb", "tvdb", ""]:
        """Return the item's preferred episode ordering."""
        return self._provider._client.get_ordering(cast(plexapi_video.Show, self._item))

    def episodes(self) -> Sequence[PlexLibraryEpisode]:
        """Return all episodes belonging to the show.

        Returns:
            Sequence[PlexLibraryEpisode]: All episodes in the show.
        """
        return [
            cast(PlexLibraryEpisode, self._provider._wrap_media(self._section, episode))
            for episode in self._item.episodes()
        ]

    def seasons(self) -> Sequence[PlexLibrarySeason]:
        """Return all seasons belonging to the show.

        Returns:
            Sequence[PlexLibrarySeason]: All seasons in the show.
        """
        return tuple(
            PlexLibrarySeason(self._provider, self._section, season, show=self)
            for season in self._item.seasons()
        )


class PlexLibrarySeason(PlexLibraryMedia, LibrarySeason):
    """Concrete ``LibrarySeason`` wrapper for Plex ``Season`` objects."""

    def __init__(
        self,
        provider: PlexLibraryProvider,
        section: PlexLibrarySection,
        item: plexapi_video.Season,
        *,
        show: PlexLibraryShow | None = None,
    ) -> None:
        """Initialize the season wrapper.

        Args:
            provider (PlexLibraryProvider): The owning Plex library provider.
            section (PlexLibrarySection): The parent Plex library section.
            item (plexapi_video.Season): The underlying Plex season item.
            show (PlexLibraryShow | None): The parent show, if known.
        """
        self._provider = provider
        self._section = section
        self._item = item
        self.media_kind = MediaKind.SEASON
        self.key = str(item.ratingKey)
        self.title = item.title
        self._show = show
        self.index = self._item.index

    def episodes(self) -> Sequence[LibraryEpisode]:
        """Return the episodes belonging to this season.

        Returns:
            Sequence[LibraryEpisode]: All episodes in the season.
        """
        return tuple(
            PlexLibraryEpisode(
                self._provider, self._section, episode, season=self, show=self._show
            )
            for episode in self._item.episodes()
        )

    def show(self) -> LibraryShow:
        """Return the parent show.

        Returns:
            LibraryShow: The parent show.
        """
        if self._show is not None:
            return self._show

        raw_parent = self._item._parent()
        raw_show = (
            cast(plexapi_video.Show, raw_parent)
            if isinstance(raw_parent, plexapi_video.Show)
            else self._item.show()
        )
        self._show = PlexLibraryShow(self._provider, self._section, raw_show)
        return self._show


class PlexLibraryEpisode(PlexLibraryMedia, LibraryEpisode):
    """Concrete ``LibraryEpisode`` wrapper for Plex ``Episode`` objects."""

    def __init__(
        self,
        provider: PlexLibraryProvider,
        section: PlexLibrarySection,
        item: plexapi_video.Episode,
        *,
        season: PlexLibrarySeason | None = None,
        show: PlexLibraryShow | None = None,
    ) -> None:
        """Initialize the episode wrapper.

        Args:
            provider (PlexLibraryProvider): The owning Plex library provider.
            section (PlexLibrarySection): The parent Plex library section.
            item (plexapi_video.Episode): The underlying Plex episode item.
            season (PlexLibrarySeason | None): The parent season, if known.
            show (PlexLibraryShow | None): The parent show, if known.
        """
        self._provider = provider
        self._section = section
        self._item = item
        self.media_kind = MediaKind.EPISODE
        self.key = str(item.ratingKey)
        self.title = item.title
        self._show = show
        self._season = season
        self.index = self._item.index
        self.season_index = self._item.parentIndex

    def season(self) -> LibrarySeason:
        """Return the parent season.

        Returns:
            LibrarySeason: The parent season.
        """
        if self._season is not None:
            return self._season

        raw_parent = self._item._parent()
        if isinstance(raw_parent, plexapi_video.Season):
            raw_season = cast(plexapi_video.Season, raw_parent)
        else:
            raw_season = self._item.season()

        self._season = PlexLibrarySeason(
            self._provider,
            self._section,
            raw_season,
            show=cast(PlexLibraryShow, self.show()),
        )
        return self._season

    def show(self) -> LibraryShow:
        """Return the parent show.

        Returns:
            LibraryShow: The parent show.
        """
        if self._show is not None:
            return self._show

        raw_parent = self._item._parent()
        raw_grandparent = raw_parent._parent() if raw_parent else None

        if isinstance(raw_parent, plexapi_video.Show):
            raw_show = raw_parent
        elif isinstance(raw_grandparent, plexapi_video.Show):
            raw_show = raw_grandparent
        else:
            raw_show = self._item.show()

        self._show = PlexLibraryShow(self._provider, self._section, raw_show)
        return self._show


class PlexLibraryProvider(LibraryProvider):
    """Default Plex ``LibraryProvider`` backed by the local Plex Media Server."""

    NAMESPACE = "plex"

    def __init__(self, *, config: dict | None = None) -> None:
        """Parse configuration and prepare provider defaults.

        Args:
            config (dict | None): Optional configuration options for the provider.
        """
        super().__init__(config=config)

        url = self.config.get("url") or ""
        token = self.config.get("token") or ""
        user = self.config.get("user") or ""
        if not url or not token or not user:
            raise ValueError(
                "The Plex provider requires 'url', 'token', and 'user' configuration "
                "values"
            )

        self._plex_url = url
        self._plex_token = token
        self._plex_user = user

        self._client_config = PlexClientConfig(url=url, token=token, user=user)
        self._section_filter = self.config.get("sections") or []
        self._genre_filter = self.config.get("genres") or []

        self._client = self._create_client()
        self._community_client: PlexCommunityClient | None = None

        self._is_admin_user = False
        self._user: LibraryUser | None = None

        self._sections: list[PlexLibrarySection] = []
        self._section_map: dict[str, PlexLibrarySection] = {}

    async def initialize(self) -> None:
        """Connect to Plex and prepare provider state."""
        await self._client.initialize()
        bundle = self._client.bundle
        self._is_admin_user = bundle.is_admin
        self._user = LibraryUser(
            key=str(bundle.user_id),
            title=bundle.display_name,
        )

        self._sections = self._build_sections()
        self._community_client = PlexCommunityClient(self._client_config.token)

        await self.clear_cache()

    async def close(self) -> None:
        """Release any resources held by the provider."""
        await self._client.close()
        if self._community_client is not None:
            await self._community_client.close()
            self._community_client = None
        self._sections.clear()
        self._section_map.clear()

    def user(self) -> LibraryUser | None:
        """Return the Plex account represented by this provider.

        Returns:
            LibraryUser | None: The user information, or None if not available.
        """
        return self._user

    async def get_sections(self) -> Sequence[LibrarySection]:
        """Enumerate Plex library sections visible to the provider user.

        Returns:
            Sequence[LibrarySection]: Available library sections.
        """
        return tuple(self._sections)

    async def list_items(
        self,
        section: LibrarySection,
        *,
        min_last_modified: datetime | None = None,
        require_watched: bool = False,
        keys: Sequence[str] | None = None,
    ) -> Sequence[LibraryMedia]:
        """List items in a Plex library section matching the provided criteria.

        Each item returned must belong to the specified section and meet the provided
        filtering criteria.

        Args:
            section (LibrarySection): The library section to list items from.
            min_last_modified (datetime | None): If provided, only items modified after
                this timestamp will be included.
            require_watched (bool): If True, only include items that have been marked as
                watched/viewed.
            keys (Sequence[str] | None): If provided, only include items whose
                media keys are in this list.

        Returns:
            Sequence[LibraryMedia]: The media items matching the criteria.
        """
        if not isinstance(section, PlexLibrarySection):
            raise TypeError(
                "Plex providers expect section objects created by the provider"
            )

        raw_items = self._client.iter_section_items(
            section.raw(),
            min_last_modified=min_last_modified,
            require_watched=require_watched,
            keys=keys,
        )

        return [self._wrap_media(section, item) for item in raw_items]

    async def clear_cache(self) -> None:
        """Reset any cached Plex responses maintained by the provider."""
        self._client.clear_cache()

    def is_on_continue_watching(
        self, section: PlexLibrarySection, item: plexapi_video.Video
    ) -> bool:
        """Determine whether the given item appears in the Continue Watching hub.

        Args:
            section (PlexLibrarySection): The library section the item belongs to.
            item (plexapi_video.Video): The Plex media item to check.

        Returns:
            bool: True if the item is on the Continue Watching list, False otherwise.
        """
        return self._client.is_on_continue_watching(section.raw(), item)

    async def get_review(self, item: plexapi_video.Video) -> str | None:
        """Fetch the user's review for the provided Plex item, if available.

        Args:
            item (plexapi_video.Video): The Plex media item to fetch the review for.

        Returns:
            str | None: The user's review text, or None if not reviewed.
        """
        if not self._community_client or not self._is_admin_user:
            return None
        if not item.guid:
            return None
        metadata_id = item.guid.rsplit("/", 1)[-1]
        try:
            return await self._community_client.get_reviews(metadata_id)
        except Exception:
            log.debug("Failed to fetch Plex review", exc_info=True)
            return None

    async def get_history(self, item: plexapi_video.Video) -> Sequence[HistoryEntry]:
        """Return the watch history for the given Plex item.

        Args:
            item (plexapi_video.Video): The Plex media item to fetch history for.

        Returns:
            Sequence[HistoryEntry]: A sequence of history entries for the media item.
        """
        base_history = await self._client.fetch_history(item)

        # The Plex database isn't great at consistently tracking history, so in addition
        # to pulling from the history endpoint, we also derive history from the
        # lastViewedAt attribute.
        derived_history: list[HistoryEntry] = []
        children = (
            item.episodes()
            if isinstance(item, (plexapi_video.Show, plexapi_video.Season))
            else [item]
        )

        if not children:
            return tuple(
                HistoryEntry(library_key=rating_key, viewed_at=viewed_at)
                for rating_key, viewed_at in base_history
            )

        # Find all child items that have been viewed but aren't in the base history
        children_dict = {str(child.ratingKey): child for child in children}
        base_keys = {rating_key for rating_key, _ in base_history}
        for child_key, child in children_dict.items():
            if child.lastViewedAt is None or child_key in base_keys:
                continue
            derived_history.append(
                HistoryEntry(library_key=child_key, viewed_at=child.lastViewedAt)
            )

        return tuple(
            HistoryEntry(library_key=rating_key, viewed_at=viewed_at)
            for rating_key, viewed_at in base_history
        ) + tuple(derived_history)

    def _build_sections(self) -> list[PlexLibrarySection]:
        """Construct the list of Plex library sections available to the user."""
        sections: list[PlexLibrarySection] = []
        self._section_map.clear()

        for raw in self._client.sections:
            wrapper = PlexLibrarySection(self, raw)
            self._section_map[wrapper.key] = wrapper
            sections.append(wrapper)
        return sections

    def _wrap_media(
        self,
        section: PlexLibrarySection,
        item: plexapi_video.Video,
    ) -> LibraryMedia:
        """Wrap a Plex media item in the appropriate library media class."""
        if isinstance(item, plexapi_video.Episode):
            return PlexLibraryEpisode(self, section, item)
        if isinstance(item, plexapi_video.Season):
            return PlexLibrarySeason(self, section, item)
        if isinstance(item, plexapi_video.Show):
            return PlexLibraryShow(self, section, item)
        if isinstance(item, plexapi_video.Movie):
            return PlexLibraryMovie(self, section, item)
        raise TypeError(f"Unsupported Plex media type: {type(item)!r}")

    def _create_client(self) -> PlexClient:
        """Construct and return a PlexClient for this provider."""
        return PlexClient(
            config=self._client_config,
            section_filter=self._section_filter,
            genre_filter=self._genre_filter,
        )

"""Plex Metadata API Module."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from functools import cached_property, wraps
from itertools import chain
from time import sleep
from typing import Any
from xml.etree import ElementTree

import requests
from limiter import Limiter

from plexapi.base import PlexObject, cached_data_property
from plexapi.exceptions import BadRequest, NotFound, Unauthorized
from plexapi.library import (
    Library,
    LibrarySection,
    MovieSection,
    ShowSection,
)
from plexapi.server import PlexServer
from plexapi.utils import cleanXMLString
from plexapi.video import Episode, Movie, Season, Show, Video
from src import log
from src.utils.cache import gttl_cache

plex_metadata_limiter = Limiter(rate=300 / 60, capacity=30, jitter=True)


def original_server(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to temporarily switch to the original server context.

    Args:
        func (Callable): The function to wrap

    Returns:
        Callable: The wrapped function that will execute with original server context
    """

    @wraps(func)
    def wrapper(self: PlexMetadataObject, *args: Any, **kwargs: Any) -> Any:
        original_url = self._server._baseurl
        original_token = self._server._token
        try:
            self._server._baseurl = self._server.__dict__.get("_original_baseurl", "")
            self._server._token = self._server.__dict__.get("_original_token", "")
            return func(self, *args, **kwargs)
        finally:
            self._server._baseurl = original_url
            self._server._token = original_token

    return wrapper


def discover_server(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to temporarily switch to discover.plex.tv server context.

    Args:
        func (Callable): The function to wrap

    Returns:
        Callable: The wrapped function that will execute with the Discover server
                context
    """

    @wraps(func)
    def wrapper(self: PlexMetadataObject, *args: Any, **kwargs: Any) -> Any:
        original_url = self._server._baseurl
        original_token = self._server._token
        try:
            self._server._baseurl = self._server.myPlexAccount().DISCOVER
            self._server._token = self._server.myPlexAccount().authToken
            return func(self, *args, **kwargs)
        finally:
            self._server._baseurl = original_url
            self._server._token = original_token

    return wrapper


def metadata_server(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to temporarily switch to metadata.provider.plex.tv server context.

    Args:
        func (Callable): The function to wrap

    Returns:
        Callable: The wrapped function that will execute with the Metadata server
                  context
    """

    @wraps(func)
    def wrapper(self: PlexMetadataObject, *args: Any, **kwargs: Any) -> Any:
        original_url = self._server._baseurl
        original_token = self._server._token
        try:
            self._server._baseurl = self._server.myPlexAccount().METADATA
            self._server._token = self._server.myPlexAccount().authToken
            return func(self, *args, **kwargs)
        finally:
            self._server._baseurl = original_url
            self._server._token = original_token

    return wrapper


class PlexMetadataObject(PlexObject):
    """Base class for Plex objects that can interact with Metadata API.

    This class extends the standard PlexObject with capabilities to fetch data
    from different Plex endpoints based on the source of the object.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the PlexMetadataObject with a reference to the server."""
        super().__init__(*args, **kwargs)
        self._source: str = self._server._baseurl

    @original_server
    def _reloadOriginalServer(self, *args, **kwargs):
        return super()._reload(*args, **kwargs)

    @metadata_server
    def _reloadMetadataServer(self, *args, **kwargs):
        return super()._reload(*args, **kwargs)

    def _reload(self, *args, **kwargs):
        if self._source == self._server.__dict__.get("_original_baseurl"):
            return self._reloadOriginalServer(*args, **kwargs)
        elif self._source == self._server.myPlexAccount().METADATA:
            return self._reloadMetadataServer(*args, **kwargs)
        return super()._reload(*args, **kwargs)


class VideoMetadataMixin:
    """Mixin class for video objects to handle rating keys and user states."""

    def _loadData(self, data):
        super()._loadData(data)  # type: ignore
        self.ratingKey = data.attrib.get("ratingKey")


class EpisodeMetadataMixin:
    """Mixin class for episode objects to handle parent and grandparent rating keys."""

    def _loadData(self, data):
        super()._loadData(data)  # type: ignore
        self.parentRatingKey = data.attrib.get("parentRatingKey")
        self.grandparentRatingKey = data.attrib.get("grandparentRatingKey")


class SeasonMetadataMixin:
    """Mixin class for season objects to handle parent rating keys."""

    def _loadData(self, data):
        super()._loadData(data)  # type: ignore
        self.parentRatingKey = data.attrib.get("parentRatingKey")

    @metadata_server
    def episodes(self, **kwargs):
        """Fetch episodes for the season from the Metadata API."""
        key = f"{self.key}/children?includeUserState=1&episodeOrder=tvdbAiring"  # type: ignore
        return self.fetchItems(key, MetadataEpisode, **kwargs)  # type: ignore


class ShowMetadataMixin:
    """Mixin class for show objects to handle user states and seasons."""

    @discover_server
    def __loadUserStates(self, seasons):
        if not seasons:
            return seasons
        rating_keys = [s.ratingKey.rsplit("/", 1)[-1] for s in seasons]
        key = f"/library/metadata/{','.join(rating_keys)}/userState"

        data = self._server.query(key)  # type: ignore
        if data is None:
            return seasons

        user_states = {
            elem.attrib.get("ratingKey"): elem
            for elem in data
            if elem.attrib.get("ratingKey")
        }

        for season in seasons:
            rating_key = season.guid.rsplit("/", 1)[-1]
            if rating_key in user_states:
                user_state_elem = user_states[rating_key]
                season._data.attrib.update(user_state_elem.attrib)
                for child in user_state_elem:
                    season._data.append(child)
                season._loadData(season._data)
        return seasons

    @metadata_server
    def seasons(self, **kwargs):
        """Fetch seasons for the show from the Metadata API."""
        key = f"{self.key}/children?excludeAllLeaves=1&episodeOrder=tvdbAiring"  # type: ignore
        return self.__loadUserStates(
            self.fetchItems(  # type: ignore
                key,
                MetadataSeason,
                container_size=self.childCount,  # type: ignore
                **kwargs,
            )
        )

    def episodes(self, **kwargs):
        """Fetch all episodes for the show from the Metadata API."""
        return list(
            chain.from_iterable(season.episodes(**kwargs) for season in self.seasons())
        )


class LibrarySectionMetadataMixin:
    """Mixin class for library section objects to handle search and item fetching."""

    @original_server
    def _search(self, *args, **kwargs):
        return super().search(*args, **kwargs)  # type: ignore

    @metadata_server
    def search(
        self,
        cls=None,
        title=None,
        sort=None,
        maxresults=None,
        libtype=None,
        container_start=None,
        container_size=None,
        limit=None,
        filters=None,
        **kwargs,
    ):
        """Search for items in the library section.

        Automatically fetches user state information for items from the Metadata API.
        """
        data = self._search(
            title,
            sort,
            maxresults,
            libtype,
            container_start,
            container_size,
            limit,
            filters,
            **kwargs,
        )
        metadata_guids = [item.guid.rsplit("/", 1)[-1] for item in data if item.guid]
        if not metadata_guids:
            return []

        return self.fetchItems(  # type: ignore
            f"/library/metadata/{','.join(metadata_guids)}?includeUserState=1",
            cls,
            **kwargs,
        )


class MetadataVideo(VideoMetadataMixin, PlexMetadataObject, Video):
    """Extends PlexObject with video metadata capabilities."""

    pass


class MetadataMovie(VideoMetadataMixin, PlexMetadataObject, Movie):
    """Extends PlexObject with movie metadata capabilities."""

    pass


class MetadataEpisode(
    EpisodeMetadataMixin, VideoMetadataMixin, PlexMetadataObject, Episode
):
    """Extends PlexObject with episode metadata capabilities."""

    pass


class MetadataSeason(
    SeasonMetadataMixin, VideoMetadataMixin, PlexMetadataObject, Season
):
    """Extends PlexObject with season metadata capabilities."""

    pass


class MetadataShow(ShowMetadataMixin, VideoMetadataMixin, PlexMetadataObject, Show):
    """Extends PlexObject with show metadata capabilities."""

    pass


class MetadataLibrarySection(
    LibrarySectionMetadataMixin, PlexMetadataObject, LibrarySection
):
    """Extends PlexObject with library section metadata capabilities."""

    pass


class MetadataMovieSection(
    LibrarySectionMetadataMixin, PlexMetadataObject, MovieSection
):
    """Extends PlexObject with movie section metadata capabilities."""

    def search(self, *args, **kwargs):
        """Search for movies in the movie section."""
        return LibrarySectionMetadataMixin.search(
            self, *args, cls=MetadataMovie, **kwargs
        )


class MetadataShowSection(LibrarySectionMetadataMixin, PlexMetadataObject, ShowSection):
    """Extends PlexObject with show section metadata capabilities."""

    def search(self, *args, **kwargs):
        """Search for shows in the show section."""
        return LibrarySectionMetadataMixin.search(
            self, *args, cls=MetadataShow, **kwargs
        )


class MetadataLibrary(PlexMetadataObject, Library):
    """Extends PlexObject with library metadata capabilities."""

    @cached_data_property
    def _loadSections(self):
        key = "/library/sections"
        sectionsByID = {}
        sectionsByTitle = defaultdict(list)
        libcls = {
            "movie": MetadataMovieSection,
            "show": MetadataShowSection,
        }

        for elem in self._server.query(key):  # type: ignore
            section = libcls.get(elem.attrib.get("type"), MetadataLibrarySection)(  # type: ignore
                self._server, elem, initpath=key
            )
            sectionsByID[section.key] = section
            sectionsByTitle[section.title.lower().strip()].append(section)

        return sectionsByID, dict(sectionsByTitle)


class PlexMetadataServer(PlexServer):
    """Extends PlexObject with metadata capabilities."""

    def __init__(self, *args, **kwargs):
        """Initialize the PlexMetadataServer with a reference to the original server."""
        super().__init__(*args, **kwargs)

        self._original_baseurl = self._baseurl
        self._original_token = self._token

    @cached_property
    def library(self):
        """Fetch the library metadata from the Plex server."""
        try:
            data = self.query(MetadataLibrary.key)
        except BadRequest:
            data = self.query("/library/sections/")
        return MetadataLibrary(self, data)

    @plex_metadata_limiter()
    @gttl_cache(maxsize=None, ttl=30)
    def query(
        self,
        key,
        method=None,
        headers=None,
        params=None,
        timeout=None,
        retry_count=0,
        **kwargs,
    ):
        """Query the Plex server for data.

        Includes rate limiting and error handling for rate limit exceeded responses.
        """
        if retry_count >= 3:
            raise requests.exceptions.HTTPError("Failed to make request after 3 tries")

        url = self.url(key)
        method = method or self._session.get
        timeout = timeout or self._timeout
        log.debug("%s %s", method.__name__.upper(), url)
        headers = self._headers(**(headers or {}))
        response = method(
            url, headers=headers, params=params, timeout=timeout, **kwargs
        )

        if response.status_code == 429:  # Handle rate limit retries
            retry_after = int(response.headers.get("Retry-After", 60))
            log.warning(
                f"{self.__class__.__name__}: Rate limit exceeded, waiting "
                f"{retry_after} seconds"
            )
            sleep(retry_after + 1)
            return self.query(
                key, method, headers, params, timeout, retry_count, **kwargs
            )
        elif response.status_code == 500:  # Bad Gateway
            log.warning(
                f"{self.__class__.__name__}: Received 502 Bad Gateway, retrying"
            )
            sleep(1)
            return self.query(
                key, method, headers, params, timeout, retry_count + 1, **kwargs
            )

        if response.status_code not in (200, 201, 204):
            errtext = response.text.replace("\n", " ")
            message = (
                f"({response.status_code}) {response.status_code}; {response.url} "
                f"{errtext}"
            )
            if response.status_code == 401:
                raise Unauthorized(message)
            elif response.status_code == 404:
                raise NotFound(message)
            else:
                raise BadRequest(message)

        data = cleanXMLString(response.text).encode("utf8")
        return ElementTree.fromstring(data) if data.strip() else None

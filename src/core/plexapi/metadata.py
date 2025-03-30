import sys
from collections import defaultdict
from functools import cached_property, wraps
from itertools import chain
from time import sleep
from typing import (
    Any,
    Callable,
)
from xml.etree import ElementTree

import requests
from plexapi import log, utils
from plexapi.base import PlexObject
from plexapi.exceptions import BadRequest, NotFound, Unauthorized
from plexapi.library import (
    Library,
    LibrarySection,
    MovieSection,
    ShowSection,
)
from plexapi.server import PlexServer
from plexapi.video import Episode, Movie, Season, Show, Video
from requests.status_codes import _codes as codes

from src.utils.cache import generic_ttl_cache
from src.utils.rate_limiter import RateLimiter


def original_server(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to temporarily switch to the original server context.

    Args:
        func (Callable): The function to wrap

    Returns:
        Callable: The wrapped function that will execute with original server context
    """

    @wraps(func)
    def wrapper(self: "PlexMetadataObject", *args: Any, **kwargs: Any) -> Any:
        original_url = self._server._baseurl
        original_token = self._server._token
        try:
            self._server._baseurl = self._server._original_baseurl
            self._server._token = self._server._original_token
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
        Callable: The wrapped function that will execute with the Discover server context
    """

    @wraps(func)
    def wrapper(self: "PlexMetadataObject", *args: Any, **kwargs: Any) -> Any:
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
        Callable: The wrapped function that will execute with the Metadata server context
    """

    @wraps(func)
    def wrapper(self: "PlexMetadataObject", *args: Any, **kwargs: Any) -> Any:
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._server: PlexMetadataServer
        self._source: str = self._server._baseurl

    @original_server
    def _reloadOriginalServer(self, *args, **kwargs):
        return super()._reload(*args, **kwargs)

    @metadata_server
    def _reloadMetadataServer(self, *args, **kwargs):
        return super()._reload(*args, **kwargs)

    def _reload(self, *args, **kwargs):
        if self._source == self._server._original_baseurl:
            return self._reloadOriginalServer(*args, **kwargs)
        elif self._source == self._server.myPlexAccount().METADATA:
            return self._reloadMetadataServer(*args, **kwargs)
        return super()._reload(*args, **kwargs)


class VideoMetadataMixin:
    def _loadData(self, data):
        super()._loadData(data)
        self.ratingKey = data.attrib.get("ratingKey")


class EpisodeMetadataMixin:
    def _loadData(self, data):
        super()._loadData(data)
        self.parentRatingKey = data.attrib.get("parentRatingKey")
        self.grandparentRatingKey = data.attrib.get("grandparentRatingKey")


class SeasonMetadataMixin:
    def _loadData(self, data):
        super()._loadData(data)
        self.parentRatingKey = data.attrib.get("parentRatingKey")

    @metadata_server
    def episodes(self, **kwargs):
        key = f"{self.key}/children?includeUserState=1&episodeOrder=tvdbAiring"
        return self.fetchItems(key, MetadataEpisode, **kwargs)


class ShowMetadataMixin:
    @discover_server
    def __loadUserStates(self, seasons):
        if not seasons:
            return seasons
        rating_keys = [s.ratingKey.rsplit("/", 1)[-1] for s in seasons]
        key = f"/library/metadata/{','.join(rating_keys)}/userState"

        data = self._server.query(key)
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
        key = f"{self.key}/children?excludeAllLeaves=1&episodeOrder=tvdbAiring"  # &includeUserState=1
        return self.__loadUserStates(
            self.fetchItems(
                key, MetadataSeason, container_size=self.childCount, **kwargs
            )
        )

    def episodes(self, **kwargs):
        return list(
            chain.from_iterable(season.episodes(**kwargs) for season in self.seasons())
        )


class LibrarySectionMetadataMixin:
    @original_server
    def _search(self, *args, **kwargs):
        return super().search(*args, **kwargs)

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

        return self.fetchItems(
            f"/library/metadata/{','.join(metadata_guids)}?includeUserState=1",
            cls,
            **kwargs,
        )


class MetadataVideo(VideoMetadataMixin, PlexMetadataObject, Video):
    pass


class MetadataMovie(VideoMetadataMixin, PlexMetadataObject, Movie):
    pass


class MetadataEpisode(
    EpisodeMetadataMixin, VideoMetadataMixin, PlexMetadataObject, Episode
):
    pass


class MetadataSeason(
    SeasonMetadataMixin, VideoMetadataMixin, PlexMetadataObject, Season
):
    pass


class MetadataShow(ShowMetadataMixin, VideoMetadataMixin, PlexMetadataObject, Show):
    pass


class MetadataLibrarySection(
    LibrarySectionMetadataMixin, PlexMetadataObject, LibrarySection
):
    pass


class MetadataMovieSection(
    LibrarySectionMetadataMixin, PlexMetadataObject, MovieSection
):
    def search(self, *args, **kwargs):
        return LibrarySectionMetadataMixin.search(
            self, cls=MetadataMovie, *args, **kwargs
        )


class MetadataShowSection(LibrarySectionMetadataMixin, PlexMetadataObject, ShowSection):
    def search(self, *args, **kwargs):
        return LibrarySectionMetadataMixin.search(
            self, cls=MetadataShow, *args, **kwargs
        )


class MetadataLibrary(PlexMetadataObject, Library):
    def _loadSections(self):
        key = "/library/sections"
        sectionsByID = {}
        sectionsByTitle = defaultdict(list)
        libcls = {
            "movie": MetadataMovieSection,
            "show": MetadataShowSection,
        }

        for elem in self._server.query(key):
            section = libcls.get(elem.attrib.get("type"), MetadataLibrarySection)(
                self._server, elem, initpath=key
            )
            sectionsByID[section.key] = section
            sectionsByTitle[section.title.lower().strip()].append(section)

        self._sectionsByID = sectionsByID
        self._sectionsByTitle = dict(sectionsByTitle)


class PlexMetadataServer(PlexServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._original_baseurl = self._baseurl
        self._original_token = self._token

        self.rate_limiter = RateLimiter(
            self.__class__.__name__, requests_per_minute=sys.maxsize
        )

    @cached_property
    def library(self):
        try:
            data = self.query(MetadataLibrary.key)
        except BadRequest:
            data = self.query("/library/sections/")
        return MetadataLibrary(self, data)

    @generic_ttl_cache(maxsize=None, ttl=30)
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
            raise requests.HTTPError("Failed to make request after 3 tries")

        if self._baseurl in (
            self.myPlexAccount().DISCOVER,
            self.myPlexAccount().METADATA,
        ):
            self.rate_limiter.wait_if_needed()

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
                f"{self.__class__.__name__}: Rate limit exceeded, waiting {retry_after} seconds"
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
            codename = codes.get(response.status_code)[0]
            errtext = response.text.replace("\n", " ")
            message = f"({response.status_code}) {codename}; {response.url} {errtext}"
            if response.status_code == 401:
                raise Unauthorized(message)
            elif response.status_code == 404:
                raise NotFound(message)
            else:
                raise BadRequest(message)

        data = utils.cleanXMLString(response.text).encode("utf8")
        return ElementTree.fromstring(data) if data.strip() else None

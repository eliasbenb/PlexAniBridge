import sys
from collections import defaultdict
from functools import cached_property, wraps
from itertools import islice
from time import sleep
from typing import (
    Any,
    Callable,
)
from xml.etree import ElementTree

from plexapi import log, utils
from plexapi.base import PlexObject
from plexapi.exceptions import BadRequest, NotFound, Unauthorized
from plexapi.library import (
    Library,
    LibrarySection,
    MovieSection,
    ShowSection,
)
from plexapi.myplex import UserState
from plexapi.server import PlexServer
from plexapi.video import Episode, Movie, Season, Show, Video
from requests.status_codes import _codes as codes

from src.utils.rate_limitter import RateLimiter


def original_server(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to temporarily switch to the original server context.

    Args:
        func (Callable): The function to wrap

    Returns:
        Callable: The wrapped function that will execute with original server context
    """

    @wraps(func)
    def wrapper(self: "DiscoverPlexObject", *args: Any, **kwargs: Any) -> Any:
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
    """Decorator to temporarily switch to discover.provider.plex.tv server context.

    Args:
        func (Callable): The function to wrap

    Returns:
        Callable: The wrapped function that will execute with the Discover server context
    """

    @wraps(func)
    def wrapper(self: "DiscoverPlexObject", *args: Any, **kwargs: Any) -> Any:
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
    def wrapper(self: "DiscoverPlexObject", *args: Any, **kwargs: Any) -> Any:
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


class DiscoverPlexObject(PlexObject):
    """Base class for Plex objects that can interact with Discover API.

    This class extends the standard PlexObject with capabilities to fetch data
    from different Plex endpoints (original server, Discover API, Metadata API).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._server: DiscoverPlexServer
        self._source: str = self._server._baseurl

    @original_server
    def _fetchItemOriginalServer(self, *args, **kwargs):
        return super().fetchItem(*args, **kwargs)

    @discover_server
    def _fetchItemDiscoverServer(self, *args, **kwargs):
        return super().fetchItem(*args, **kwargs)

    @metadata_server
    def _fetchItemMetadataServer(self, *args, **kwargs):
        return super().fetchItem(*args, **kwargs)

    def fetchItem(self, *args, **kwargs):
        if self._server._baseurl == self._server._original_baseurl:
            return self._fetchItemOriginalServer(*args, **kwargs)
        if self._server._baseurl == self._server.myPlexAccount().DISCOVER:
            return self._fetchItemDiscoverServer(*args, **kwargs)
        if self._server._baseurl == self._server.myPlexAccount().METADATA:
            return self._fetchItemMetadataServer(*args, **kwargs)
        return super().fetchItem(*args, **kwargs)

    @original_server
    def _fetchItemsOriginalServer(self, *args, **kwargs):
        return super().fetchItems(*args, **kwargs)

    @discover_server
    def _fetchItemsDiscoverServer(self, *args, **kwargs):
        return super().fetchItems(*args, **kwargs)

    @metadata_server
    def _fetchItemsMetadataServer(self, *args, **kwargs):
        return super().fetchItems(*args, **kwargs)

    def fetchItems(self, *args, **kwargs):
        if self._server._baseurl == self._server._original_baseurl:
            return self._fetchItemsOriginalServer(*args, **kwargs)
        if self._server._baseurl == self._server.myPlexAccount().DISCOVER:
            return self._fetchItemsDiscoverServer(*args, **kwargs)
        if self._server._baseurl == self._server.myPlexAccount().METADATA:
            return self._fetchItemsMetadataServer(*args, **kwargs)
        return super().fetchItems(*args, **kwargs)

    @original_server
    def _reloadOriginalServer(self, *args, **kwargs):
        return super()._reload(*args, **kwargs)

    @discover_server
    def _reloadDiscoverServer(self, *args, **kwargs):
        return super()._reload(*args, **kwargs)

    @metadata_server
    def _reloadMetadataServer(self, *args, **kwargs):
        return super()._reload(*args, **kwargs)

    def _reload(self, *args, **kwargs):
        if self._source == self._server._original_baseurl:
            return self._reloadOriginalServer(*args, **kwargs)
        if self._source == self._server.myPlexAccount().DISCOVER:
            return self._reloadDiscoverServer(*args, **kwargs)
        if self._source == self._server.myPlexAccount().METADATA:
            return self._reloadMetadataServer(*args, **kwargs)
        return super()._reload(*args, **kwargs)

    @discover_server
    def _loadUserStatesDiscoverServer(self, items, **kwargs):
        """Load user state information for multiple items from the Discover API.

        Fetches user state data (watched status, view progress, etc.) using the Discover
        API for the provided items and applies it to the item objects.

        Args:
            items: List of Plex media objects to load user states for
            **kwargs: Additional arguments to pass to fetchItems

        Returns:
            list: List of Plex media objects with user state information applied
        """
        key = ",".join([item.guid.rsplit("/", 1)[-1] for item in items])
        if not key:
            return items

        user_states = self.fetchItems(
            f"/library/metadata/{key}/userState", UserState, **kwargs
        )

        for item, user_state in zip(items, user_states):
            for field in (
                "lastViewedAt",
                "viewCount",
                "viewedLeafCount",
                "viewOffset",
                "viewState",
                "watchlistedAt",
            ):
                if hasattr(user_state, field):
                    setattr(item, field, getattr(user_state, field))

            for key_field, guid_field in zip(
                ("ratingKey", "parentRatingKey", "grandparentRatingKey"),
                ("guid", "parentGuid", "grandparentGuid"),
            ):
                guid_value = getattr(item, guid_field, None)
                if guid_value:
                    setattr(item, key_field, guid_value.rsplit("/", 1)[-1])
        return items

    def _loadUserStates(self, items, **kwargs):
        if self._source == self._server.myPlexAccount().DISCOVER:
            return self._loadUserStatesDiscoverServer(items, **kwargs)
        return items

    def _loadUserState(self, item, **kwargs):
        try:
            return self._loadUserStates([item], **kwargs)[0]
        except IndexError:
            return item


class DiscoverVideo(Video, DiscoverPlexObject):
    pass


class DiscoverMovie(Movie, DiscoverVideo):
    pass


class DiscoverEpisode(Episode, DiscoverVideo):
    pass


class DiscoverSeason(Season, DiscoverVideo):
    def _episodes(self, **kwargs):
        key = f"{self.key}/children?episodeOrder=tvdbAiring"
        return self._loadUserStates(self.fetchItems(key, DiscoverEpisode, **kwargs))

    @original_server
    def _episodesOriginalServer(self, **kwargs):
        return self._episodes(**kwargs)

    @discover_server
    def _episodesDiscoverServer(self, **kwargs):
        return self._episodes(**kwargs)

    @metadata_server
    def _episodesMetadataServer(self, **kwargs):
        return self._loadUserStates(self._episodes(DiscoverEpisode, **kwargs))

    def episodes(self, **kwargs):
        if self._source == self._server._original_baseurl:
            return self._episodesOriginalServer(**kwargs)
        if self._source == self._server.myPlexAccount().DISCOVER:
            return self._episodesDiscoverServer(**kwargs)
        if self._source == self._server.myPlexAccount().METADATA:
            return self._episodesMetadataServer(**kwargs)


class DiscoverShow(Show, DiscoverVideo):
    def episodes(self, **kwargs):
        return sum([season.episodes(**kwargs) for season in self.seasons()], [])

    def _seasons(self, **kwargs):
        key = f"{self.key}/children?excludeAllLeaves=1&episodeOrder=tvdbAiring"
        return self._loadUserStates(
            self.fetchItems(
                key, DiscoverSeason, container_size=self.childCount, **kwargs
            )
        )

    @original_server
    def _seasonsOriginalServer(self, **kwargs):
        return self._seasons(**kwargs)

    @discover_server
    def _seasonsDiscoverServer(self, **kwargs):
        return self._seasons(**kwargs)

    @metadata_server
    def _seasonsMetadataServer(self, **kwargs):
        return self._loadUserStates(self._seasons(DiscoverSeason, **kwargs))

    def seasons(self, **kwargs):
        if self._source == self._server._original_baseurl:
            return self._seasonsOriginalServer(**kwargs)
        if self._source == self._server.myPlexAccount().DISCOVER:
            return self._seasonsDiscoverServer(**kwargs)
        if self._source == self._server.myPlexAccount().METADATA:
            return self._seasonsMetadataServer(**kwargs)


class DiscoverLibrarySection(LibrarySection, DiscoverPlexObject):
    @original_server
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

        Automatically fetches user state information for items from the Discover API.
        """
        data = super().search(
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

        metadata_guids = [item.guid.rsplit("/", 1)[-1] for item in data]

        def _chunked(iterable, size: int = 25):
            it = iter(iterable)
            while chunk := list(islice(it, size)):
                yield chunk

        res = []
        for chunk in _chunked(metadata_guids):
            res.extend(
                self._fetchItemsDiscoverServer(
                    f"/library/metadata/{','.join(chunk)}", cls, **kwargs
                )
            )

        return self._loadUserStates(res)


class DiscoverMovieSection(MovieSection, DiscoverLibrarySection):
    def search(self, *args, **kwargs):
        return super().search(cls=DiscoverMovie, *args, **kwargs)


class DiscoverShowSection(ShowSection, DiscoverLibrarySection):
    def search(self, *args, **kwargs):
        return super().search(cls=DiscoverShow, *args, **kwargs)


class DiscoverLibrary(Library, DiscoverPlexObject):
    def _loadSections(self):
        key = "/library/sections"
        sectionsByID = {}
        sectionsByTitle = defaultdict(list)
        libcls = {
            "movie": DiscoverMovieSection,
            "show": DiscoverShowSection,
        }

        for elem in self._server.query(key):
            section = libcls.get(elem.attrib.get("type"), DiscoverLibrarySection)(
                self._server, elem, initpath=key
            )
            sectionsByID[section.key] = section
            sectionsByTitle[section.title.lower().strip()].append(section)

        self._sectionsByID = sectionsByID
        self._sectionsByTitle = dict(sectionsByTitle)


class DiscoverPlexServer(PlexServer, DiscoverPlexObject):
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
            data = self.query(DiscoverLibrary.key)
        except BadRequest:
            data = self.query("/library/sections/")
        return DiscoverLibrary(self, data)

    def query(
        self, key, method=None, headers=None, params=None, timeout=None, **kwargs
    ):
        """Query the Plex server for data.

        Includes rate limiting and error handling for rate limit exceeded responses.
        """
        if self._baseurl in (
            self.myPlexAccount().DISCOVER,
            self.myPlexAccount().METADATA,
        ):
            self.rate_limiter.wait_if_needed()

        url = self.url(key)
        method = method or self._session.get
        timeout = timeout or self._timeout
        log.debug("%s %s", method.__name__.upper(), url)
        headers = self._headers(**headers or {})
        response = method(
            url, headers=headers, params=params, timeout=timeout, **kwargs
        )

        if response.status_code == 429:  # Handle rate limit retries
            retry_after = int(response.headers.get("Retry-After", 60))
            log.warning(
                f"{self.__class__.__name__}: Rate limit exceeded, waiting {retry_after} seconds"
            )
            sleep(retry_after + 1)
            return self.query(key, method, headers, params, timeout, **kwargs)

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

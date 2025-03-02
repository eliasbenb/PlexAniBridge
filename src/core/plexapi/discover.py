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


def with_discover_server(func: Callable[..., Any]) -> Callable[..., Any]:
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


class DiscoverPlexObject(PlexObject):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._server: DiscoverPlexServer

    @with_discover_server
    def fetchItemDiscover(self, *args, **kwargs):
        return super().fetchItem(*args, **kwargs)

    @with_discover_server
    def fetchItemsDiscover(self, *args, **kwargs):
        return self.fetchItems(*args, **kwargs)

    @with_discover_server
    def _reload(self, *args, **kwargs):
        return super()._reload(*args, **kwargs)

    @with_discover_server
    def _loadUserState(self, items, **kwargs):
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

            for field in zip(
                ("ratingKey", "parentRatingKey", "grandparentRatingKey"),
                ("guid", "parentGuid", "grandparentGuid"),
            ):
                if hasattr(item, field[1]):
                    guid_value = getattr(item, field[1], None)
                    if guid_value:
                        setattr(item, field[0], guid_value.rsplit("/", 1)[-1])
        return items


class DiscoverVideo(DiscoverPlexObject, Video):
    pass


class DiscoverMovie(DiscoverVideo, Movie):
    pass


class DiscoverEpisode(DiscoverVideo, Episode):
    pass


class DiscoverSeason(DiscoverVideo, Season):
    @with_discover_server
    def episodes(self, **kwargs):
        return self._loadUserState(
            self.fetchItems(f"{self.key}/children", DiscoverEpisode, **kwargs)
        )


class DiscoverShow(DiscoverVideo, Show):
    def episodes(self, **kwargs):
        return [e for s in self.seasons() for e in s.episodes(**kwargs)]

    @with_discover_server
    def seasons(self, **kwargs):
        return self._loadUserState(
            self.fetchItems(
                f"{self.key}/children?excludeAllLeaves=1",
                DiscoverSeason,
                container_size=self.childCount,
                **kwargs,
            )
        )


class DiscoverLibrarySection(DiscoverPlexObject, LibrarySection):
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
        load_discover_data=True,
        **kwargs,
    ):
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

        if load_discover_data is False:
            return data

        metadata_guids = [item.guid.rsplit("/", 1)[-1] for item in data]

        def _chunked(iterable, size: int = 25):
            it = iter(iterable)
            while chunk := list(islice(it, size)):
                yield chunk

        res = []
        for chunk in _chunked(metadata_guids):
            res.extend(
                self.fetchItemsDiscover(
                    f"/library/metadata/{','.join(chunk)}", cls, **kwargs
                )
            )

        return self._loadUserState(res)


class DiscoverMovieSection(DiscoverLibrarySection, MovieSection):
    def search(self, *args, **kwargs):
        return super().search(cls=DiscoverMovie, *args, **kwargs)


class DiscoverShowSection(DiscoverLibrarySection, ShowSection):
    def search(self, *args, **kwargs):
        return super().search(cls=DiscoverShow, *args, **kwargs)


class DiscoverLibrary(DiscoverPlexObject, Library):
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


class DiscoverPlexServer(DiscoverPlexObject, PlexServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        if self._baseurl == self.myPlexAccount().DISCOVER:
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

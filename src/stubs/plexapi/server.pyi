from collections.abc import Generator
from functools import cached_property as cached_property

import requests
from _typeshed import Incomplete

from plexapi import utils as utils
from plexapi.alert import AlertListener as AlertListener
from plexapi.base import PlexObject as PlexObject
from plexapi.client import PlexClient as PlexClient
from plexapi.collection import Collection as Collection
from plexapi.exceptions import BadRequest as BadRequest
from plexapi.exceptions import NotFound as NotFound
from plexapi.exceptions import Unauthorized as Unauthorized
from plexapi.library import File as File
from plexapi.library import Hub as Hub
from plexapi.library import Library as Library
from plexapi.library import Path as Path
from plexapi.media import Conversion as Conversion
from plexapi.media import Optimized as Optimized
from plexapi.playlist import Playlist as Playlist
from plexapi.playqueue import PlayQueue as PlayQueue
from plexapi.settings import Settings as Settings
from plexapi.utils import deprecated as deprecated

class PlexServer(PlexObject):
    key: str
    _baseurl: str
    _session: requests.Session
    _timeout: float
    _token: str
    def __init__(
        self,
        baseurl: Incomplete | None = None,
        token: Incomplete | None = None,
        session: Incomplete | None = None,
        timeout: Incomplete | None = None,
    ) -> None: ...
    @cached_property
    def library(self): ...
    @cached_property
    def settings(self): ...
    def identity(self): ...
    def account(self): ...
    def claim(self, account): ...
    def unclaim(self): ...
    @property
    def activities(self): ...
    def agents(self, mediaType: Incomplete | None = None): ...
    def createToken(self, type: str = "delegation", scope: str = "all"): ...
    def switchUser(
        self, user, session: Incomplete | None = None, timeout: Incomplete | None = None
    ) -> PlexServer: ...
    def systemAccounts(self): ...
    def systemAccount(self, accountID): ...
    def systemDevices(self): ...
    def systemDevice(self, deviceID): ...
    def myPlexAccount(self): ...
    def browse(self, path: Incomplete | None = None, includeFiles: bool = True): ...
    def walk(self, path: Incomplete | None = None) -> Generator[Incomplete]: ...
    def isBrowsable(self, path): ...
    def clients(self): ...
    def client(self, name): ...
    def createCollection(
        self,
        title,
        section,
        items: Incomplete | None = None,
        smart: bool = False,
        limit: Incomplete | None = None,
        libtype: Incomplete | None = None,
        sort: Incomplete | None = None,
        filters: Incomplete | None = None,
        **kwargs,
    ): ...
    def createPlaylist(
        self,
        title,
        section: Incomplete | None = None,
        items: Incomplete | None = None,
        smart: bool = False,
        limit: Incomplete | None = None,
        libtype: Incomplete | None = None,
        sort: Incomplete | None = None,
        filters: Incomplete | None = None,
        m3ufilepath: Incomplete | None = None,
        **kwargs,
    ): ...
    def createPlayQueue(self, item, **kwargs): ...
    def downloadDatabases(
        self,
        savepath: Incomplete | None = None,
        unpack: bool = False,
        showstatus: bool = False,
    ): ...
    def downloadLogs(
        self,
        savepath: Incomplete | None = None,
        unpack: bool = False,
        showstatus: bool = False,
    ): ...
    def butlerTasks(self): ...
    def runButlerTask(self, task): ...
    def check_for_update(self, force: bool = True, download: bool = False): ...
    def checkForUpdate(self, force: bool = True, download: bool = False): ...
    def isLatest(self): ...
    def canInstallUpdate(self): ...
    def installUpdate(self): ...
    def history(
        self,
        maxresults: Incomplete | None = None,
        mindate: Incomplete | None = None,
        ratingKey: Incomplete | None = None,
        accountID: Incomplete | None = None,
        librarySectionID: Incomplete | None = None,
    ): ...
    def playlists(
        self,
        playlistType: Incomplete | None = None,
        sectionId: Incomplete | None = None,
        title: Incomplete | None = None,
        sort: Incomplete | None = None,
        **kwargs,
    ): ...
    def playlist(self, title): ...
    def optimizedItems(self, removeAll: Incomplete | None = None): ...
    def optimizedItem(self, optimizedID): ...
    def conversions(self, pause: Incomplete | None = None): ...
    def currentBackgroundProcess(self): ...
    def query(
        self,
        key,
        method: Incomplete | None = None,
        headers: Incomplete | None = None,
        params: Incomplete | None = None,
        timeout: Incomplete | None = None,
        **kwargs,
    ): ...
    def search(
        self,
        query,
        mediatype: Incomplete | None = None,
        limit: Incomplete | None = None,
        sectionId: Incomplete | None = None,
    ): ...
    def continueWatching(self): ...
    def sessions(self): ...
    def transcodeSessions(self): ...
    def startAlertListener(
        self,
        callback: Incomplete | None = None,
        callbackError: Incomplete | None = None,
    ): ...
    def transcodeImage(
        self,
        imageUrl,
        height,
        width,
        opacity: Incomplete | None = None,
        saturation: Incomplete | None = None,
        blur: Incomplete | None = None,
        background: Incomplete | None = None,
        blendColor: Incomplete | None = None,
        minSize: bool = True,
        upscale: bool = True,
        imageFormat: Incomplete | None = None,
    ): ...
    def url(self, key, includeToken: Incomplete | None = None): ...
    def refreshSynclist(self): ...
    def refreshContent(self): ...
    def refreshSync(self) -> None: ...
    def bandwidth(self, timespan: Incomplete | None = None, **kwargs): ...
    def resources(self): ...
    def getWebURL(
        self, base: Incomplete | None = None, playlistTab: Incomplete | None = None
    ): ...
    def _headers(self, **kwargs) -> dict[str, str]: ...

class Account(PlexObject):
    key: str

class Activity(PlexObject):
    key: str

class Release(PlexObject):
    TAG: str
    key: str

class SystemAccount(PlexObject):
    TAG: str

class SystemDevice(PlexObject):
    TAG: str

class StatisticsBandwidth(PlexObject):
    TAG: str
    def account(self): ...
    def device(self): ...

class StatisticsResources(PlexObject):
    TAG: str

class ButlerTask(PlexObject):
    TAG: str

class Identity(PlexObject): ...

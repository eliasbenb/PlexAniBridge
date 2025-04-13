from collections.abc import Generator
from datetime import datetime
from functools import cached_property
from typing import Callable
from xml.etree.ElementTree import Element

import requests
from _typeshed import Incomplete

from plexapi.alert import AlertListener
from plexapi.audio import Audio
from plexapi.base import PlexHistory, PlexObject
from plexapi.library import File, Library, LibrarySection, Path
from plexapi.media import Agent, Session, TranscodeSession
from plexapi.myplex import MyPlexAccount, MyPlexUser
from plexapi.photo import Photo
from plexapi.playlist import Playlist
from plexapi.settings import Settings
from plexapi.video import Video

class PlexServer(PlexObject):
    _baseurl: str
    _session: requests.Session
    _timeout: float
    _token: str
    def __init__(
        self,
        baseurl: str | None = None,
        token: str | None = None,
        session: requests.Session | None = None,
        timeout: int | None = None,
    ) -> None: ...
    @cached_property
    def library(self) -> Library: ...
    @cached_property
    def settings(self) -> Settings: ...
    def identity(self) -> Identity: ...
    def account(self) -> Account: ...
    def claim(self, account: MyPlexAccount) -> Account: ...
    def unclaim(self) -> Account: ...
    @property
    def activities(self) -> list[Activity]: ...
    def agents(self, mediaType: str | None = None) -> list[Agent]: ...
    def createToken(
        self, type: str = "delegation", scope: str = "all"
    ) -> str | None: ...
    def switchUser(
        self,
        user: MyPlexUser | str,
        session: requests.Session | None = None,
        timeout: int | None = None,
    ) -> PlexServer: ...
    def systemAccounts(self) -> list[SystemAccount]: ...
    def systemAccount(self, accountID: int) -> SystemAccount: ...
    def systemDevices(self) -> list[SystemDevice]: ...
    def systemDevice(self, deviceID: int) -> SystemDevice: ...
    def myPlexAccount(self) -> MyPlexAccount: ...
    def browse(
        self, path: Path | str | None = None, includeFiles: bool = True
    ) -> list[Path] | list[File]: ...
    def walk(
        self, path: Path | str | None = None
    ) -> Generator[tuple[str, list[Path], list[File]], None, None]: ...
    def isBrowsable(self, path: Path | str) -> bool: ...
    def clients(self): ...
    def client(self, name): ...
    def createCollection(
        self,
        title: str,
        section: LibrarySection | str,
        items: list[Audio] | list[Photo.__class__] | list[Video] | None = None,
        smart: bool = False,
        limit: int | None = None,
        libtype: str | None = None,
        sort: str | list[str] | None = None,
        filters: dict | None = None,
        **kwargs,
    ): ...
    def createPlaylist(
        self,
        title: str,
        section: LibrarySection | str,
        items: list[Audio] | list[Photo.__class__] | list[Video] | None = None,
        smart: bool = False,
        limit: int | None = None,
        libtype: str | None = None,
        sort: str | list[str] | None = None,
        filters: dict | None = None,
        m3ufilepath: str | None = None,
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
        maxresults: int | None = None,
        mindate: datetime | None = None,
        ratingKey: int | str | None = None,
        accountID: int | str | None = None,
        librarySectionID: int | str | None = None,
    ) -> PlexHistory: ...
    def playlists(
        self,
        playlistType: str | None = None,
        sectionId: int | None = None,
        title: str | None = None,
        sort: str | None = None,
        **kwargs,
    ) -> list[Playlist.__class__]: ...
    def playlist(self, title: str) -> Playlist.__class__: ...
    def optimizedItems(self, removeAll: Incomplete | None = None): ...
    def optimizedItem(self, optimizedID): ...
    def conversions(self, pause: Incomplete | None = None): ...
    def currentBackgroundProcess(self): ...
    def query(
        self,
        key: str | None,
        method: Callable | None = None,
        headers: dict | None = None,
        params: requests.sessions._Params | None = None,
        timeout: int | None = None,
        **kwargs,
    ) -> str | dict | Element | None: ...
    def search(
        self,
        query: str,
        mediatype: str | None = None,
        limit: int | None = None,
        sectionId: int | None = None,
    ): ...
    def continueWatching(self): ...
    def sessions(self) -> list[Session]: ...
    def transcodeSessions(self) -> list[TranscodeSession]: ...
    def startAlertListener(
        self,
        callback: Callable | None = None,
        callbackError: Callable | None = None,
    ) -> AlertListener: ...
    def transcodeImage(
        self,
        imageUrl: str,
        height: int,
        width: int,
        opacity: int | None = None,
        saturation: int | None = None,
        blur: int | None = None,
        background: str | None = None,
        blendColor: str | None = None,
        minSize: bool = True,
        upscale: bool = True,
        imageFormat: str | None = None,
    ) -> str: ...
    def url(self, key: str | None, includeToken: bool | None = None) -> str: ...
    def refreshSynclist(self) -> Element | None: ...
    def refreshContent(self) -> Element | None: ...
    def refreshSync(self) -> None: ...
    def bandwidth(
        self, timespan: str | None = None, **kwargs
    ) -> list[StatisticsBandwidth]: ...
    def resources(self) -> list[StatisticsResources]: ...
    def getWebURL(
        self, base: str | None = None, playlistTab: str | None = None
    ) -> str: ...
    def _headers(self, **kwargs) -> dict[str, str]: ...

class Account(PlexObject):
    pass

class Activity(PlexObject):
    pass

class Release(PlexObject):
    pass

class SystemAccount(PlexObject):
    pass

class SystemDevice(PlexObject):
    pass

class StatisticsBandwidth(PlexObject):
    def account(self) -> SystemAccount: ...
    def device(self) -> SystemDevice: ...

class StatisticsResources(PlexObject):
    pass

class ButlerTask(PlexObject):
    pass

class Identity(PlexObject):
    pass

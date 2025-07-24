from collections.abc import Callable
from datetime import datetime
from typing import Any
from xml.etree.ElementTree import Element

import requests
from _typeshed import Incomplete
from typing_extensions import Self

from plexapi.base import PlexHistory, PlexObject
from plexapi.client import PlexClient
from plexapi.library import LibrarySection
from plexapi.server import PlexServer
from plexapi.sync import SyncItem, SyncList
from plexapi.video import Episode, Movie, Season, Show

class MyPlexAccount(PlexObject):
    FRIENDINVITE: str
    HOMEUSERS: str
    HOMEUSERCREATE: str
    EXISTINGUSER: str
    FRIENDSERVERS: str
    PLEXSERVERS: str
    FRIENDUPDATE: str
    HOMEUSER: str
    MANAGEDHOMEUSER: str
    SIGNIN: str
    SIGNOUT: str
    WEBHOOKS: str
    OPTOUTS: str
    LINK: str
    VIEWSTATESYNC: str
    PING: str
    VOD: str
    MUSIC: str
    DISCOVER: str
    METADATA: str

    _token: str
    _webhooks: list
    adsConsent: str | None
    adsConsentReminderAt: str | None
    adsConsentSetAt: str | None
    anonymous: str | None
    authToken: str
    backupCodesCreated: bool
    confirmed: bool
    country: str | None
    email: str | None
    emailOnlyAuth: bool
    experimentalFeatures: bool
    friendlyName: str | None
    guest: bool
    hasPassword: bool
    home: bool
    homeAdmin: bool
    homeSize: int
    id: int
    joinedAt: datetime
    locale: str | None
    mailingListActive: bool
    mailingListStatus: str | None
    maxHomeSize: int
    pin: str | None
    protected: bool
    rememberExpiresAt: datetime | None
    restricted: bool
    scrobbleTypes: list[int]
    thumb: str | None
    title: str | None
    twoFactorEnabled: bool
    username: str
    uuid: str | None
    subscriptionActive: bool
    subscriptionDescription: str | None
    subscriptionPaymentService: str | None
    subscriptionPlan: str | None
    subscriptionStatus: str | None
    subscriptionSubscribedAt: datetime | None
    profileAutoSelectAudio: bool
    profileDefaultAudioLanguage: str | None
    profileDefaultSubtitleLanguage: str | None
    profileAutoSelectSubtitle: int
    profileDefaultSubtitleAccessibility: int
    profileDefaultSubtitleForces: int
    services: Any | None

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        session: requests.Session | None = None,
        timeout: int | None = None,
        code: str | None = None,
        remember: bool = True,
    ) -> None: ...
    def signout(self): ...
    @property
    def authenticationToken(self): ...
    def query(
        self,
        url: str,
        method: Callable | None = None,
        headers: dict | None = None,
        timeout: int | None = None,
        **kwargs,
    ) -> str | dict | Element | None: ...
    def ping(self) -> bool: ...
    def device(self, name: str | None = None, clientId: str | None = None): ...
    def devices(self) -> list[MyPlexDevice]: ...
    def resource(self, name: str) -> MyPlexResource: ...
    def resources(self) -> list[MyPlexResource]: ...
    def sonos_speakers(self): ...
    def sonos_speaker(self, name): ...
    def sonos_speaker_by_id(self, identifier): ...
    def inviteFriend(
        self,
        user: MyPlexUser | str,
        server: PlexServer,
        sections: list[LibrarySection] | None = None,
        allowSync: bool = False,
        allowCameraUpload: bool = False,
        allowChannels: bool = False,
        filterMovies: dict | None = None,
        filterTelevision: dict | None = None,
        filterMusic: dict | None = None,
    ): ...
    def createHomeUser(
        self,
        user: MyPlexUser | str,
        server: PlexServer,
        sections: list[LibrarySection] | None = None,
        allowSync: bool = False,
        allowCameraUpload: bool = False,
        allowChannels: bool = False,
        filterMovies: dict | None = None,
        filterTelevision: dict | None = None,
        filterMusic: dict | None = None,
    ): ...
    def createExistingUser(
        self,
        user: MyPlexUser | str,
        server: PlexServer,
        sections: list[LibrarySection] | None = None,
        allowSync: bool = False,
        allowCameraUpload: bool = False,
        allowChannels: bool = False,
        filterMovies: dict | None = None,
        filterTelevision: dict | None = None,
        filterMusic: dict | None = None,
    ): ...
    def removeFriend(self, user: MyPlexUser | str): ...
    def removeHomeUser(self, user: MyPlexUser | str) -> MyPlexAccount: ...
    def switchHomeUser(
        self, user: MyPlexUser | str, pin: str | None = None
    ) -> MyPlexAccount: ...
    def setPin(self, newPin: str, currentPin: str | None = None): ...
    def removePin(self, currentPin: str): ...
    def setManagedUserPin(self, user: MyPlexUser | str, newPin: str): ...
    def removeManagedUserPin(self, user: MyPlexUser | str): ...
    def acceptInvite(self, user: MyPlexUser | str): ...
    def cancelInvite(self, user: MyPlexUser | str): ...
    def updateFriend(
        self,
        user: MyPlexUser | str,
        server: PlexServer,
        sections: list[LibrarySection] | None = None,
        removeSections: bool = False,
        allowSync: bool | None = None,
        allowCameraUpload: bool | None = None,
        allowChannels: bool | None = None,
        filterMovies: dict | None = None,
        filterTelevision: dict | None = None,
        filterMusic: dict | None = None,
    ): ...
    def user(self, username: str) -> MyPlexUser: ...
    def users(self) -> list[MyPlexUser]: ...
    def pendingInvite(
        self, username: str, includeSent: bool = True, includeReceived: bool = True
    ) -> MyPlexInvite: ...
    def pendingInvites(
        self, includeSent: bool = True, includeReceived: bool = True
    ) -> list[MyPlexInvite]: ...
    def addWebhook(self, url: str): ...
    def deleteWebhook(self, url: str): ...
    def setWebhooks(self, urls: list[str]): ...
    def webhooks(self): ...
    def optOut(
        self, playback: Incomplete | None = None, library: Incomplete | None = None
    ): ...
    def syncItems(
        self, client: MyPlexDevice | None = None, clientId: str | None = None
    ) -> SyncList: ...
    def sync(
        self,
        sync_item: SyncItem,
        client: MyPlexDevice | None = None,
        clientId: str | None = None,
    ) -> SyncItem: ...
    def claimToken(self) -> str: ...
    def history(
        self, maxresults: int | None = None, mindate: datetime | None = None
    ) -> list[PlexHistory]: ...
    def onlineMediaSources(self): ...
    def videoOnDemand(self): ...
    def tidal(self): ...
    def watchlist(
        self,
        filter: str | None = None,
        sort: str | None = None,
        libtype: str | None = None,
        maxresults: int | None = None,
        **kwargs,
    ) -> list[Movie | Show]: ...
    def onWatchlist(self, item: Movie | Show) -> bool: ...
    def addToWatchlist(self, items: list[Movie | Show]) -> Self: ...
    def removeFromWatchlist(self, items: list[Movie | Show]) -> Self: ...
    def userState(self, item: Movie | Show): ...
    def isPlayed(self, item: Movie | Show | Season | Episode) -> bool: ...
    def markPlayed(self, item: Movie | Show | Season | Episode) -> Self: ...
    def markUnplayed(self, item: Movie | Show | Season | Episode) -> Self: ...
    def searchDiscover(
        self,
        query: str,
        limit: int = 30,
        libtype: str | None = None,
        providers: str = "discover",
    ) -> list[Movie | Show]: ...
    @property
    def viewStateSync(self) -> bool: ...
    def enableViewStateSync(self) -> None: ...
    def disableViewStateSync(self) -> None: ...
    def link(self, pin: str) -> None: ...
    def publicIP(self): ...
    def geoip(self, ip_address: str) -> GeoLocation: ...

class MyPlexUser(PlexObject):
    friend: bool
    allowCameraUpload: bool
    allowChannels: bool
    allowSync: bool
    email: str
    filterAll: str | None
    filterMovies: str | None
    filterMusic: str | None
    filterPhotos: str | None
    filterTelevision: str | None
    home: bool
    id: int
    protected: bool
    recommendationsPlaylistId: str | None
    restricted: str | None
    thumb: str | None
    title: str
    username: str
    servers: list[MyPlexServerShare]
    def get_token(self, machineIdentifier): ...
    def server(self, name): ...
    def history(
        self, maxresults: int | None = None, mindate: datetime | None = None
    ) -> list[PlexHistory]: ...

class MyPlexInvite(PlexObject):
    REQUESTS: str
    REQUESTED: str

class Section(PlexObject):
    def history(
        self, maxresults: int | None = None, mindate: datetime | None = None
    ) -> list[PlexHistory]: ...

class MyPlexServerShare(PlexObject):
    def section(self, name): ...
    def sections(self): ...
    def history(
        self, maxresults: int = 9999999, mindate: datetime | None = None
    ) -> list[PlexHistory]: ...

class MyPlexResource(PlexObject):
    DEFAULT_LOCATION_ORDER: list[str]
    DEFAULT_SCHEME_ORDER: list[str]
    def preferred_connections(
        self,
        ssl: Incomplete | None = None,
        locations: Incomplete | None = None,
        schemes: Incomplete | None = None,
    ): ...
    def connect(
        self,
        ssl: bool | None = None,
        timeout: int | None = None,
        locations: Incomplete | None = None,
        schemes: Incomplete | None = None,
    ) -> PlexServer | PlexClient.__class__: ...

class ResourceConnection(PlexObject):
    pass

class MyPlexDevice(PlexObject):
    def connect(
        self, timeout: int | None = None
    ) -> PlexServer | PlexClient.__class__: ...
    def delete(self) -> None: ...
    def syncItems(self) -> SyncList: ...

class MyPlexPinLogin:
    PINS: str
    CHECKPINS: str
    POLLINTERVAL: int
    headers: dict
    finished: bool
    expired: bool
    token: str
    def __init__(
        self,
        session: requests.Session | None = None,
        requestTimeout: int | None = None,
        headers: dict | None = None,
        oauth: bool = False,
    ) -> None: ...
    @property
    def pin(self) -> str: ...
    def oauthUrl(self, forwardUrl: str | None = None) -> str: ...
    def run(
        self,
        callback: Callable[[str], Any] | None = None,
        timeout: int | None = None,
    ) -> None: ...
    def waitForLogin(self) -> bool: ...
    def stop(self) -> None: ...
    def checkLogin(self) -> bool: ...

class AccountOptOut(PlexObject):
    CHOICES: Incomplete
    def optIn(self) -> None: ...
    def optOut(self) -> None: ...
    def optOutManaged(self) -> None: ...

class UserState(PlexObject):
    pass

class GeoLocation(PlexObject):
    pass

from _typeshed import Incomplete

from plexapi.base import PlexObject

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
    key: str
    def __init__(
        self,
        username: Incomplete | None = None,
        password: Incomplete | None = None,
        token: Incomplete | None = None,
        session: Incomplete | None = None,
        timeout: Incomplete | None = None,
        code: Incomplete | None = None,
        remember: bool = True,
    ) -> None: ...
    def signout(self): ...
    @property
    def authenticationToken(self): ...
    def query(
        self,
        url,
        method: Incomplete | None = None,
        headers: Incomplete | None = None,
        timeout: Incomplete | None = None,
        **kwargs,
    ): ...
    def ping(self): ...
    def device(
        self, name: Incomplete | None = None, clientId: Incomplete | None = None
    ): ...
    def devices(self): ...
    def resource(self, name): ...
    def resources(self): ...
    def sonos_speakers(self): ...
    def sonos_speaker(self, name): ...
    def sonos_speaker_by_id(self, identifier): ...
    def inviteFriend(
        self,
        user,
        server,
        sections: Incomplete | None = None,
        allowSync: bool = False,
        allowCameraUpload: bool = False,
        allowChannels: bool = False,
        filterMovies: Incomplete | None = None,
        filterTelevision: Incomplete | None = None,
        filterMusic: Incomplete | None = None,
    ): ...
    def createHomeUser(
        self,
        user,
        server,
        sections: Incomplete | None = None,
        allowSync: bool = False,
        allowCameraUpload: bool = False,
        allowChannels: bool = False,
        filterMovies: Incomplete | None = None,
        filterTelevision: Incomplete | None = None,
        filterMusic: Incomplete | None = None,
    ): ...
    def createExistingUser(
        self,
        user,
        server,
        sections: Incomplete | None = None,
        allowSync: bool = False,
        allowCameraUpload: bool = False,
        allowChannels: bool = False,
        filterMovies: Incomplete | None = None,
        filterTelevision: Incomplete | None = None,
        filterMusic: Incomplete | None = None,
    ): ...
    def removeFriend(self, user): ...
    def removeHomeUser(self, user): ...
    def switchHomeUser(self, user, pin: Incomplete | None = None): ...
    def setPin(self, newPin, currentPin: Incomplete | None = None): ...
    def removePin(self, currentPin): ...
    def setManagedUserPin(self, user, newPin): ...
    def removeManagedUserPin(self, user): ...
    def acceptInvite(self, user): ...
    def cancelInvite(self, user): ...
    def updateFriend(
        self,
        user,
        server,
        sections: Incomplete | None = None,
        removeSections: bool = False,
        allowSync: Incomplete | None = None,
        allowCameraUpload: Incomplete | None = None,
        allowChannels: Incomplete | None = None,
        filterMovies: Incomplete | None = None,
        filterTelevision: Incomplete | None = None,
        filterMusic: Incomplete | None = None,
    ): ...
    def user(self, username): ...
    def users(self): ...
    def pendingInvite(
        self, username, includeSent: bool = True, includeReceived: bool = True
    ): ...
    def pendingInvites(
        self, includeSent: bool = True, includeReceived: bool = True
    ): ...
    def addWebhook(self, url): ...
    def deleteWebhook(self, url): ...
    def setWebhooks(self, urls): ...
    def webhooks(self): ...
    def optOut(
        self, playback: Incomplete | None = None, library: Incomplete | None = None
    ): ...
    def syncItems(
        self, client: Incomplete | None = None, clientId: Incomplete | None = None
    ): ...
    def sync(
        self,
        sync_item,
        client: Incomplete | None = None,
        clientId: Incomplete | None = None,
    ): ...
    def claimToken(self): ...
    def history(
        self, maxresults: Incomplete | None = None, mindate: Incomplete | None = None
    ): ...
    def onlineMediaSources(self): ...
    def videoOnDemand(self): ...
    def tidal(self): ...
    def watchlist(
        self,
        filter: Incomplete | None = None,
        sort: Incomplete | None = None,
        libtype: Incomplete | None = None,
        maxresults: Incomplete | None = None,
        **kwargs,
    ): ...
    def onWatchlist(self, item): ...
    def addToWatchlist(self, items): ...
    def removeFromWatchlist(self, items): ...
    def userState(self, item): ...
    def isPlayed(self, item): ...
    def markPlayed(self, item): ...
    def markUnplayed(self, item): ...
    def searchDiscover(
        self,
        query,
        limit: int = 30,
        libtype: Incomplete | None = None,
        providers: str = "discover",
    ): ...
    @property
    def viewStateSync(self): ...
    def enableViewStateSync(self) -> None: ...
    def disableViewStateSync(self) -> None: ...
    def link(self, pin) -> None: ...
    def publicIP(self): ...
    def geoip(self, ip_address): ...

class MyPlexUser(PlexObject):
    TAG: str
    key: str
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
        self, maxresults: Incomplete | None = None, mindate: Incomplete | None = None
    ): ...

class MyPlexInvite(PlexObject):
    TAG: str
    REQUESTS: str
    REQUESTED: str

class Section(PlexObject):
    TAG: str
    def history(
        self, maxresults: Incomplete | None = None, mindate: Incomplete | None = None
    ): ...

class MyPlexServerShare(PlexObject):
    TAG: str
    def section(self, name): ...
    def sections(self): ...
    def history(self, maxresults: int = 9999999, mindate: Incomplete | None = None): ...

class MyPlexResource(PlexObject):
    TAG: str
    key: str
    DEFAULT_LOCATION_ORDER: Incomplete
    DEFAULT_SCHEME_ORDER: Incomplete
    def preferred_connections(
        self,
        ssl: Incomplete | None = None,
        locations: Incomplete | None = None,
        schemes: Incomplete | None = None,
    ): ...
    def connect(
        self,
        ssl: Incomplete | None = None,
        timeout: Incomplete | None = None,
        locations: Incomplete | None = None,
        schemes: Incomplete | None = None,
    ): ...

class ResourceConnection(PlexObject):
    TAG: str

class MyPlexDevice(PlexObject):
    TAG: str
    key: str
    def connect(self, timeout: Incomplete | None = None): ...
    def delete(self) -> None: ...
    def syncItems(self): ...

class MyPlexPinLogin:
    PINS: str
    CHECKPINS: str
    POLLINTERVAL: int
    headers: Incomplete
    finished: bool
    expired: bool
    token: Incomplete
    def __init__(
        self,
        session: Incomplete | None = None,
        requestTimeout: Incomplete | None = None,
        headers: Incomplete | None = None,
        oauth: bool = False,
    ) -> None: ...
    @property
    def pin(self): ...
    def oauthUrl(self, forwardUrl: Incomplete | None = None): ...
    def run(
        self, callback: Incomplete | None = None, timeout: Incomplete | None = None
    ) -> None: ...
    def waitForLogin(self): ...
    def stop(self) -> None: ...
    def checkLogin(self): ...

class AccountOptOut(PlexObject):
    TAG: str
    CHOICES: Incomplete
    def optIn(self) -> None: ...
    def optOut(self) -> None: ...
    def optOutManaged(self) -> None: ...

class UserState(PlexObject):
    TAG: str

class GeoLocation(PlexObject):
    TAG: str

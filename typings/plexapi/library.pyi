from collections.abc import Generator
from datetime import datetime
from functools import cached_property as cached_property
from typing import Any

from _typeshed import Incomplete

from plexapi.audio import Audio, Track
from plexapi.base import PlexHistory, PlexObject
from plexapi.media import Agent
from plexapi.mixins import (
    AlbumEditMixins,
    ArtistEditMixins,
    EpisodeEditMixins,
    MovieEditMixins,
    PhotoalbumEditMixins,
    PhotoEditMixins,
    SeasonEditMixins,
    ShowEditMixins,
    TrackEditMixins,
)
from plexapi.myplex import MyPlexDevice
from plexapi.photo import Photo
from plexapi.settings import Setting
from plexapi.sync import MediaSettings, Policy, SyncItem
from plexapi.video import Episode, Movie, Season, Show, Video

class Library(PlexObject):
    def sections(self) -> list[LibrarySection]: ...
    def section(self, title) -> LibrarySection: ...
    def sectionByID(self, sectionID) -> LibrarySection: ...
    def hubs(
        self,
        sectionID: Incomplete | None = None,
        identifier: Incomplete | None = None,
        **kwargs,
    ): ...
    def all(self, **kwargs) -> list[Audio | Photo.__class__ | Video]: ...
    def onDeck(self): ...
    def recentlyAdded(self): ...
    def search(
        self,
        title: Incomplete | None = None,
        libtype: Incomplete | None = None,
        **kwargs,
    ): ...
    def cleanBundles(self): ...
    def emptyTrash(self): ...
    def optimize(self): ...
    def update(self): ...
    def cancelUpdate(self): ...
    def refresh(self): ...
    def deleteMediaPreviews(self): ...
    def add(
        self,
        name: str = "",
        type: str = "",
        agent: str = "",
        scanner: str = "",
        location: str = "",
        language: str = "en-US",
        *args,
        **kwargs,
    ): ...
    def history(
        self, maxresults: int | None = None, mindate: datetime | None = None
    ) -> PlexHistory: ...
    def tags(self, tag): ...

class LibrarySection(PlexObject):
    title: str
    type: str
    @cached_property
    def totalSize(self) -> int: ...
    @property
    def totalDuration(self) -> int: ...
    @property
    def totalStorage(self) -> int: ...
    def __getattribute__(self, attr): ...
    def totalViewSize(
        self, libtype: str | None = None, includeCollections: bool = True
    ): ...
    def delete(self): ...
    def edit(self, agent: Incomplete | None = None, **kwargs): ...
    def addLocations(self, location): ...
    def removeLocations(self, location): ...
    def get(self, title, **kwargs): ...
    def getGuid(self, guid): ...
    def all(self, libtype: Incomplete | None = None, **kwargs): ...
    def folders(self): ...
    def managedHubs(self): ...
    def resetManagedHubs(self) -> None: ...
    def hubs(self): ...
    def agents(self) -> list[Agent]: ...
    def settings(self) -> list[Setting]: ...
    def editAdvanced(self, **kwargs): ...
    def defaultAdvanced(self): ...
    def lockAllField(self, field, libtype: Incomplete | None = None): ...
    def unlockAllField(self, field, libtype: Incomplete | None = None): ...
    def timeline(self): ...
    def onDeck(self): ...
    def continueWatching(self): ...
    def recentlyAdded(
        self, maxresults: int = 50, libtype: Incomplete | None = None
    ): ...
    def firstCharacter(self): ...
    def analyze(self): ...
    def emptyTrash(self): ...
    def update(self, path: Incomplete | None = None): ...
    def cancelUpdate(self): ...
    def refresh(self): ...
    def deleteMediaPreviews(self): ...
    def filterTypes(self): ...
    def getFilterType(self, libtype: Incomplete | None = None): ...
    def fieldTypes(self): ...
    def getFieldType(self, fieldType): ...
    def listFilters(self, libtype: Incomplete | None = None): ...
    def listSorts(self, libtype: Incomplete | None = None): ...
    def listFields(self, libtype: Incomplete | None = None): ...
    def listOperators(self, fieldType): ...
    def listFilterChoices(self, field, libtype: Incomplete | None = None): ...
    def hubSearch(
        self,
        query,
        mediatype: Incomplete | None = None,
        limit: Incomplete | None = None,
    ): ...
    def search(
        self,
        title: Incomplete | None = None,
        sort: Incomplete | None = None,
        maxresults: Incomplete | None = None,
        libtype: Incomplete | None = None,
        container_start: Incomplete | None = None,
        container_size: Incomplete | None = None,
        limit: Incomplete | None = None,
        filters: Incomplete | None = None,
        **kwargs,
    ) -> list[Video]: ...
    def sync(
        self,
        policy: Policy,
        mediaSettings: MediaSettings,
        client: MyPlexDevice | None = None,
        clientId: Incomplete | str = None,
        title: Incomplete | str = None,
        sort: Incomplete | str = None,
        libtype: Incomplete | str = None,
        **kwargs,
    ) -> SyncItem: ...
    def history(
        self, maxresults: int | None = None, mindate: datetime | None = None
    ) -> PlexHistory: ...
    def createCollection(
        self,
        title,
        items: Incomplete | None = None,
        smart: bool = False,
        limit: Incomplete | None = None,
        libtype: Incomplete | None = None,
        sort: Incomplete | None = None,
        filters: Incomplete | None = None,
        **kwargs,
    ): ...
    def collection(self, title): ...
    def collections(self, **kwargs): ...
    def createPlaylist(
        self,
        title,
        items: Incomplete | None = None,
        smart: bool = False,
        limit: Incomplete | None = None,
        sort: Incomplete | None = None,
        filters: Incomplete | None = None,
        m3ufilepath: Incomplete | None = None,
        **kwargs,
    ): ...
    def playlist(self, title): ...
    def playlists(self, sort: Incomplete | None = None, **kwargs): ...
    def filterFields(self, mediaType: str | None = None) -> list[FilteringField]: ...
    def listChoices(
        self, category: str, libtype: str | None = None, **kwargs
    ) -> list[FilterChoice]: ...
    def getWebURL(
        self, base: str | None = None, tab: str | None = None, key: str | None = None
    ) -> str: ...
    def common(self, items): ...
    def multiEdit(self, items, **kwargs): ...
    def batchMultiEdits(self, items): ...
    def saveMultiEdits(self): ...

class MovieSection(LibrarySection, MovieEditMixins):
    METADATA_TYPE: str
    CONTENT_TYPE: str
    def searchMovies(self, **kwargs) -> list[Movie]: ...
    def recentlyAddedMovies(self, maxresults: int = 50) -> list[Movie]: ...
    def sync(
        self,
        policy: Policy,
        mediaSettings: MediaSettings,
        client: MyPlexDevice | None = None,
        clientId: Incomplete | str = None,
        title: Incomplete | str = None,
        sort: Incomplete | str = None,
        libtype: Incomplete | str = None,
        videoQuality: int = 0,
        limit: int | None = None,
        unwatched: bool = False,
        **kwargs,
    ) -> SyncItem: ...

class ShowSection(LibrarySection, ShowEditMixins, SeasonEditMixins, EpisodeEditMixins):
    METADATA_TYPE: str
    CONTENT_TYPE: str
    def searchShows(self, **kwargs) -> list[Show]: ...
    def searchSeasons(self, **kwargs) -> list[Season]: ...
    def searchEpisodes(self, **kwargs) -> list[Episode]: ...
    def recentlyAddedShows(self, maxresults: int = 50) -> list[Show]: ...
    def recentlyAddedSeasons(self, maxresults: int = 50) -> list[Season]: ...
    def recentlyAddedEpisodes(self, maxresults: int = 50) -> list[Episode]: ...
    def sync(
        self,
        policy: Policy,
        mediaSettings: MediaSettings,
        client: MyPlexDevice | None = None,
        clientId: Incomplete | str = None,
        title: Incomplete | str = None,
        sort: Incomplete | str = None,
        libtype: Incomplete | str = None,
        videoQuality: int = 0,
        limit: int | None = None,
        unwatched: bool = False,
        **kwargs,
    ) -> SyncItem: ...

class MusicSection(LibrarySection, ArtistEditMixins, AlbumEditMixins, TrackEditMixins):
    METADATA_TYPE: str
    CONTENT_TYPE: str
    def albums(self): ...
    def stations(self): ...
    def searchArtists(self, **kwargs): ...
    def searchAlbums(self, **kwargs): ...
    def searchTracks(self, **kwargs): ...
    def recentlyAddedArtists(self, maxresults: int = 50): ...
    def recentlyAddedAlbums(self, maxresults: int = 50): ...
    def recentlyAddedTracks(self, maxresults: int = 50): ...
    def sync(
        self,
        policy: Policy,
        mediaSettings: MediaSettings,
        client: MyPlexDevice | None = None,
        clientId: Incomplete | str = None,
        title: Incomplete | str = None,
        sort: Incomplete | str = None,
        libtype: Incomplete | str = None,
        bitrate: int = 0,
        limit: int | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> SyncItem: ...
    def sonicAdventure(
        self, start: Track.__class__ | int, end: Track.__class__ | int, **kwargs: Any
    ) -> list[Track.__class__]: ...

class PhotoSection(LibrarySection, PhotoalbumEditMixins, PhotoEditMixins):
    METADATA_TYPE: str
    CONTENT_TYPE: str
    def all(self, libtype: str | None = None, **kwargs) -> list[Photo.__class__]: ...
    def collections(self, **kwargs) -> None: ...
    def searchAlbums(self, **kwargs): ...
    def searchPhotos(self, **kwargs): ...
    def recentlyAddedAlbums(self, maxresults: int = 50): ...
    def sync(
        self,
        policy: Policy,
        mediaSettings: MediaSettings,
        client: MyPlexDevice | None = None,
        clientId: Incomplete | str = None,
        title: Incomplete | str = None,
        sort: Incomplete | str = None,
        libtype: Incomplete | str = None,
        resolution: str = "",
        limit: int | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> SyncItem: ...

class LibraryTimeline(PlexObject):
    pass

class Location(PlexObject):
    pass

class Hub(PlexObject):
    def __len__(self) -> int: ...
    items: Incomplete
    more: bool
    size: Incomplete
    def section(self): ...

class LibraryMediaTag(PlexObject):
    def items(self, *args, **kwargs): ...

class Aperture(LibraryMediaTag):
    TAGTYPE: int

class Art(LibraryMediaTag):
    TAGTYPE: int

class Autotag(LibraryMediaTag):
    TAGTYPE: int

class Chapter(LibraryMediaTag):
    TAGTYPE: int

class Collection(LibraryMediaTag):
    TAGTYPE: int

class Concert(LibraryMediaTag):
    TAGTYPE: int

class Country(LibraryMediaTag):
    TAGTYPE: int

class Device(LibraryMediaTag):
    TAGTYPE: int

class Director(LibraryMediaTag):
    TAGTYPE: int

class Exposure(LibraryMediaTag):
    TAGTYPE: int

class Format(LibraryMediaTag):
    TAGTYPE: int

class Genre(LibraryMediaTag):
    TAGTYPE: int

class Guid(LibraryMediaTag):
    TAGTYPE: int

class ISO(LibraryMediaTag):
    TAGTYPE: int

class Label(LibraryMediaTag):
    TAGTYPE: int

class Lens(LibraryMediaTag):
    TAGTYPE: int

class Make(LibraryMediaTag):
    TAGTYPE: int

class Marker(LibraryMediaTag):
    TAGTYPE: int

class MediaProcessingTarget(LibraryMediaTag):
    TAGTYPE: int

class Model(LibraryMediaTag):
    TAGTYPE: int

class Mood(LibraryMediaTag):
    TAGTYPE: int

class Network(LibraryMediaTag):
    TAGTYPE: int

class Place(LibraryMediaTag):
    TAGTYPE: int

class Poster(LibraryMediaTag):
    TAGTYPE: int

class Producer(LibraryMediaTag):
    TAGTYPE: int

class RatingImage(LibraryMediaTag):
    TAGTYPE: int

class Review(LibraryMediaTag):
    TAGTYPE: int

class Role(LibraryMediaTag):
    TAGTYPE: int

class Similar(LibraryMediaTag):
    TAGTYPE: int

class Studio(LibraryMediaTag):
    TAGTYPE: int

class Style(LibraryMediaTag):
    TAGTYPE: int

class Tag(LibraryMediaTag):
    TAGTYPE: int

class Theme(LibraryMediaTag):
    TAGTYPE: int

class Writer(LibraryMediaTag):
    TAGTYPE: int

class FilteringType(PlexObject):
    pass

class FilteringFilter(PlexObject):
    pass

class FilteringSort(PlexObject):
    pass

class FilteringField(PlexObject):
    pass

class FilteringFieldType(PlexObject):
    pass

class FilteringOperator(PlexObject):
    pass

class FilterChoice(PlexObject):
    pass
    def items(self): ...

class ManagedHub(PlexObject):
    def move(self, after: Incomplete | None = None) -> None: ...
    def remove(self) -> None: ...
    def updateVisibility(
        self,
        recommended: Incomplete | None = None,
        home: Incomplete | None = None,
        shared: Incomplete | None = None,
    ): ...
    def promoteRecommended(self): ...
    def demoteRecommended(self): ...
    def promoteHome(self): ...
    def demoteHome(self): ...
    def promoteShared(self): ...
    def demoteShared(self): ...

class Folder(PlexObject):
    def subfolders(self) -> list[Folder]: ...
    def allSubfolders(self) -> list[Folder]: ...

class FirstCharacter(PlexObject): ...

class Path(PlexObject):
    def browse(self, includeFiles: bool = True) -> list[Path] | list[File]: ...
    def walk(self) -> Generator[tuple[str, list[Path], list[File]]]: ...

class File(PlexObject):
    pass

class Common(PlexObject):
    @property
    def commonType(self) -> str: ...
    @property
    def ratingKeys(self) -> list[int]: ...
    def items(self): ...

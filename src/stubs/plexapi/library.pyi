from collections.abc import Generator
from functools import cached_property as cached_property
from typing import Any

from _typeshed import Incomplete

from plexapi.audio import Track
from plexapi.base import PlexObject
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

class Library(PlexObject):
    key: str
    def sections(self): ...
    def section(self, title): ...
    def sectionByID(self, sectionID): ...
    def hubs(
        self,
        sectionID: Incomplete | None = None,
        identifier: Incomplete | None = None,
        **kwargs,
    ): ...
    def all(self, **kwargs): ...
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
        self, maxresults: Incomplete | None = None, mindate: Incomplete | None = None
    ): ...
    def tags(self, tag): ...

class LibrarySection(PlexObject):
    @cached_property
    def totalSize(self): ...
    @property
    def totalDuration(self): ...
    @property
    def totalStorage(self): ...
    def __getattribute__(self, attr): ...
    def totalViewSize(
        self, libtype: Incomplete | None = None, includeCollections: bool = True
    ): ...
    def delete(self): ...
    def _reload(
        self, key: str | None = None, _overwriteNone: bool = True, **kwargs
    ): ...
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
    def agents(self): ...
    def settings(self): ...
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
    ): ...
    def sync(
        self,
        policy,
        mediaSettings,
        client: Incomplete | None = None,
        clientId: Incomplete | None = None,
        title: Incomplete | None = None,
        sort: Incomplete | None = None,
        libtype: Incomplete | None = None,
        **kwargs,
    ): ...
    def history(
        self, maxresults: Incomplete | None = None, mindate: Incomplete | None = None
    ): ...
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
    def filterFields(self, mediaType: Incomplete | None = None): ...
    def listChoices(self, category, libtype: Incomplete | None = None, **kwargs): ...
    def getWebURL(
        self,
        base: Incomplete | None = None,
        tab: Incomplete | None = None,
        key: Incomplete | None = None,
    ): ...
    def common(self, items): ...
    def multiEdit(self, items, **kwargs): ...
    def batchMultiEdits(self, items): ...
    def saveMultiEdits(self): ...

class MovieSection(LibrarySection, MovieEditMixins):
    TAG: str
    TYPE: str
    METADATA_TYPE: str
    CONTENT_TYPE: str
    def searchMovies(self, **kwargs): ...
    def recentlyAddedMovies(self, maxresults: int = 50): ...
    def sync(
        self,
        videoQuality,
        limit: Incomplete | None = None,
        unwatched: bool = False,
        *args,
        **kwargs,
    ): ...

class ShowSection(LibrarySection, ShowEditMixins, SeasonEditMixins, EpisodeEditMixins):
    TAG: str
    TYPE: str
    METADATA_TYPE: str
    CONTENT_TYPE: str
    def searchShows(self, **kwargs): ...
    def searchSeasons(self, **kwargs): ...
    def searchEpisodes(self, **kwargs): ...
    def recentlyAddedShows(self, maxresults: int = 50): ...
    def recentlyAddedSeasons(self, maxresults: int = 50): ...
    def recentlyAddedEpisodes(self, maxresults: int = 50): ...
    def sync(
        self,
        videoQuality,
        limit: Incomplete | None = None,
        unwatched: bool = False,
        *args,
        **kwargs,
    ): ...

class MusicSection(LibrarySection, ArtistEditMixins, AlbumEditMixins, TrackEditMixins):
    TAG: str
    TYPE: str
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
    def sync(self, bitrate, limit: Incomplete | None = None, *args, **kwargs): ...
    def sonicAdventure(
        self, start: Track | int, end: Track | int, **kwargs: Any
    ) -> list[Track]: ...

class PhotoSection(LibrarySection, PhotoalbumEditMixins, PhotoEditMixins):
    TAG: str
    TYPE: str
    METADATA_TYPE: str
    CONTENT_TYPE: str
    def all(self, libtype: Incomplete | None = None, **kwargs): ...
    def collections(self, **kwargs) -> None: ...
    def searchAlbums(self, **kwargs): ...
    def searchPhotos(self, **kwargs): ...
    def recentlyAddedAlbums(self, maxresults: int = 50): ...
    def sync(self, resolution, limit: Incomplete | None = None, *args, **kwargs): ...

class LibraryTimeline(PlexObject):
    TAG: str

class Location(PlexObject):
    TAG: str

class Hub(PlexObject):
    TAG: str
    def __len__(self) -> int: ...
    items: Incomplete
    more: bool
    size: Incomplete
    def _reload(
        self, key: str | None = None, _overwriteNone: bool = True, **kwargs
    ): ...
    def section(self): ...

class LibraryMediaTag(PlexObject):
    TAG: str
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
    TAG: str
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
    TAG: str

class FilteringFilter(PlexObject):
    TAG: str

class FilteringSort(PlexObject):
    TAG: str

class FilteringField(PlexObject):
    TAG: str

class FilteringFieldType(PlexObject):
    TAG: str

class FilteringOperator(PlexObject):
    TAG: str

class FilterChoice(PlexObject):
    TAG: str
    def items(self): ...

class ManagedHub(PlexObject):
    TAG: str
    def _reload(
        self, key: str | None = None, _overwriteNone: bool = True, **kwargs
    ): ...
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
    def subfolders(self): ...
    def allSubfolders(self): ...

class FirstCharacter(PlexObject): ...

class Path(PlexObject):
    TAG: str
    def browse(self, includeFiles: bool = True): ...
    def walk(self) -> Generator[Incomplete]: ...

class File(PlexObject):
    TAG: str

class Common(PlexObject):
    TAG: str
    @property
    def commonType(self): ...
    @property
    def ratingKeys(self): ...
    def items(self): ...

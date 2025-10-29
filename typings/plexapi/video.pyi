from collections.abc import Iterator
from datetime import datetime
from functools import cached_property
from typing import Self

from plexapi.base import Playable, PlexHistory, PlexPartialObject, PlexSession
from plexapi.media import Review, Role, SubtitleStream
from plexapi.mixins import (
    AdvancedSettingsMixin,
    ArtMixin,
    ArtUrlMixin,
    EpisodeEditMixins,
    ExtrasMixin,
    HubsMixin,
    LogoMixin,
    MovieEditMixins,
    PlayedUnplayedMixin,
    PosterMixin,
    PosterUrlMixin,
    RatingMixin,
    SeasonEditMixins,
    ShowEditMixins,
    SplitMergeMixin,
    ThemeMixin,
    ThemeUrlMixin,
    UnmatchMatchMixin,
    WatchlistMixin,
)
from plexapi.myplex import MyPlexDevice
from plexapi.sync import SyncItem

class Video(PlexPartialObject, PlayedUnplayedMixin):
    ratingKey: int
    guid: str | None
    addedAt: datetime
    art: str
    artBlurHash: str
    fields: list
    lastRatedAt: datetime
    lastViewedAt: datetime
    librarySectionID: int
    librarySectionKey: str
    librarySectionTitle: str
    listType: str
    summary: str
    thumb: str
    thumbBlurHash: str
    title: str
    titleSort: str
    type: str
    updatedAt: datetime
    userRating: float
    viewCount: int

    def url(self, part: str) -> str | None: ...
    def augmentation(self) -> list: ...
    def uploadSubtitles(self, filepath: str) -> Self: ...
    def searchSubtitles(
        self, language: str = "en", hearingImpaired: int = 0, forced: int = 0
    ) -> list[SubtitleStream]: ...
    def downloadSubtitles(self, subtitleStream: SubtitleStream) -> Self: ...
    def removeSubtitles(
        self,
        subtitleStream: SubtitleStream | None = None,
        streamID: int | None = None,
        streamTitle: str | None = None,
    ) -> Self: ...
    def optimize(
        self,
        title: str = "",
        target: str = "",
        deviceProfile: str = "",
        videoQuality: int | None = None,
        locationID: int = -1,
        limit: int | None = None,
        unwatched: bool = False,
    ) -> Self: ...
    def sync(
        self,
        videoQuality: int,
        client: MyPlexDevice | None = None,
        clientId: str | None = None,
        limit: int | None = None,
        unwatched: bool = False,
        title: str | None = None,
    ) -> SyncItem: ...

class Movie(
    Video,
    Playable,
    AdvancedSettingsMixin,
    SplitMergeMixin,
    UnmatchMatchMixin,
    ExtrasMixin,
    HubsMixin,
    RatingMixin,
    ArtMixin,
    LogoMixin,
    PosterMixin,
    ThemeMixin,
    MovieEditMixins,
    WatchlistMixin,
):
    TAG: str
    TYPE: str
    METADATA_TYPE: str
    audienceRating: float
    audienceRatingImage: str
    chapters: list
    chapterSource: str
    collections: list
    contentRating: str
    countries: list
    directors: list
    duration: int
    editionTitle: str
    enableCreditsMarkerGeneration: int
    genres: list
    guids: list
    labels: list
    languageOverride: str
    markers: list
    media: list
    originallyAvailableAt: datetime
    originalTitle: str
    primaryExtraKey: str
    producers: list
    rating: float
    ratingImage: str
    ratings: list
    roles: list
    slug: str
    similar: list
    sourceURI: str
    studio: str
    tagline: str
    theme: str
    ultraBlurColors: object
    useOriginalTitle: int
    viewOffset: int
    writers: list
    year: int

    @property
    def actors(self) -> list[Role]: ...
    @property
    def locations(self): ...
    @property
    def hasCreditsMarker(self) -> bool: ...
    @property
    def hasVoiceActivity(self) -> bool: ...
    @property
    def hasPreviewThumbnails(self) -> bool: ...
    def reviews(self) -> list[Review]: ...
    def editions(self) -> list[Movie]: ...
    def removeFromContinueWatching(self) -> Self: ...
    @property
    def metadataDirectory(self) -> str: ...

class Show(
    Video,
    AdvancedSettingsMixin,
    SplitMergeMixin,
    UnmatchMatchMixin,
    ExtrasMixin,
    HubsMixin,
    RatingMixin,
    ArtMixin,
    LogoMixin,
    PosterMixin,
    ThemeMixin,
    ShowEditMixins,
    WatchlistMixin,
):
    TAG: str
    TYPE: str
    METADATA_TYPE: str
    audienceRating: float
    audienceRatingImage: str
    audioLanguage: str
    autoDeletionItemPolicyUnwatchedLibrary: int
    autoDeletionItemPolicyWatchedLibrary: int
    childCount: int
    collections: list
    contentRating: str
    duration: int
    enableCreditsMarkerGeneration: int
    episodeSort: int
    flattenSeasons: int
    genres: list
    guids: list
    index: int
    labels: list
    languageOverride: str
    leafCount: int
    locations: list[str]
    network: str
    originallyAvailableAt: datetime
    originalTitle: str
    rating: float
    ratings: list
    roles: list
    seasonCount: int
    showOrdering: str
    similar: list
    slug: str
    studio: str
    subtitleLanguage: str
    subtitleMode: int
    tagline: str
    theme: str
    ultraBlurColors: object
    useOriginalTitle: int
    viewedLeafCount: int
    year: int

    def __iter__(self): ...
    @property
    def actors(self) -> list[Role]: ...
    @property
    def isPlayed(self) -> bool: ...
    def onDeck(self) -> bool: ...
    def season(self, title: str | None = None, season: int | None = None) -> Season: ...
    def seasons(self, **kwargs) -> list[Season]: ...
    def episode(
        self,
        title: str | None = None,
        season: int | None = None,
        episode: int | None = None,
    ) -> Episode: ...
    def episodes(self, **kwargs) -> list[Episode]: ...
    def get(
        self,
        title: str | None = None,
        season: int | None = None,
        episode: int | None = None,
    ) -> Episode: ...
    def watched(self) -> list[Episode]: ...
    def unwatched(self) -> list[Episode]: ...
    def download(
        self,
        savepath: str | None = None,
        keep_original_name: bool = False,
        subfolders: bool = False,
        **kwargs,
    ) -> list[str]: ...
    @property
    def metadataDirectory(self) -> str: ...

class Season(
    Video,
    AdvancedSettingsMixin,
    ExtrasMixin,
    RatingMixin,
    ArtMixin,
    LogoMixin,
    PosterMixin,
    ThemeUrlMixin,
    SeasonEditMixins,
):
    TAG: str
    TYPE: str
    METADATA_TYPE: str
    audienceRating: float
    audioLanguage: str
    collections: list
    guids: list
    index: int
    labels: list
    leafCount: int
    parentGuid: str
    parentIndex: int
    parentKey: str
    parentRatingKey: int
    parentSlug: str
    parentStudio: str
    parentTheme: str
    parentThumb: str
    parentTitle: str
    rating: float
    ratings: list
    subtitleLanguage: str
    subtitleMode: int
    ultraBlurColors: object
    viewedLeafCount: int
    year: int

    def __iter__(self) -> Iterator[Episode]: ...
    @property
    def isPlayed(self) -> bool: ...
    @property
    def seasonNumber(self) -> int: ...
    def onDeck(self) -> bool: ...
    def episode(
        self, title: str | None = None, episode: int | None = None
    ) -> Episode: ...
    def episodes(self, **kwargs) -> list[Episode]: ...
    def get(self, title: str | None = None, episode: int | None = None) -> Episode: ...
    def show(self) -> Show: ...
    def watched(self) -> list[Episode]: ...
    def unwatched(self) -> list[Episode]: ...
    def download(
        self, savepath: str | None = None, keep_original_name: bool = False, **kwargs
    ) -> list[str]: ...
    @property
    def metadataDirectory(self) -> str: ...

class Episode(
    Video,
    Playable,
    ExtrasMixin,
    RatingMixin,
    ArtMixin,
    LogoMixin,
    PosterMixin,
    ThemeUrlMixin,
    EpisodeEditMixins,
):
    TAG: str
    TYPE: str
    METADATA_TYPE: str
    audienceRating: float
    audienceRatingImage: str
    chapters: list
    chapterSource: str
    collections: list
    contentRating: str
    directors: list
    duration: int
    grandparentArt: str
    grandparentGuid: str
    grandparentKey: str
    grandparentRatingKey: int
    grandparentSlug: str
    grandparentTheme: str
    grandparentThumb: str
    grandparentTitle: str
    guids: list
    index: int
    labels: list
    markers: list
    media: list
    originallyAvailableAt: datetime
    parentGuid: str
    parentIndex: int
    parentKey: str
    parentRatingKey: int
    parentThumb: str
    parentTitle: str
    parentYear: int
    producers: list
    rating: float
    ratings: list
    roles: list
    skipParent: bool
    sourceURI: str
    ultraBlurColors: object
    viewOffset: int
    writers: list
    year: int
    @property
    def actors(self) -> list[Role]: ...
    @property
    def locations(self): ...  # TODO: type
    @property
    def episodeNumber(self) -> int: ...
    @cached_property
    def seasonNumber(self) -> int: ...
    @property
    def seasonEpisode(self) -> str: ...
    @property
    def hasCommercialMarker(self) -> bool: ...
    @property
    def hasIntroMarker(self) -> bool: ...
    @property
    def hasCreditsMarker(self) -> bool: ...
    @property
    def hasVoiceActivity(self) -> bool: ...
    @property
    def hasPreviewThumbnails(self) -> bool: ...
    def season(self) -> Season: ...
    def show(self) -> Show: ...
    def removeFromContinueWatching(self) -> Self: ...
    @property
    def metadataDirectory(self) -> str: ...

class Clip(Video, Playable, ArtUrlMixin, PosterUrlMixin):
    TAG: str
    TYPE: str
    METADATA_TYPE: str
    @property
    def locations(self): ...  # TODO: type
    @property
    def metadataDirectory(self) -> str: ...

class Extra(Clip): ...

class MovieSession(PlexSession, Movie):
    pass

class EpisodeSession(PlexSession, Episode):
    pass

class ClipSession(PlexSession, Clip):
    pass

class MovieHistory(PlexHistory, Movie):
    pass

class EpisodeHistory(PlexHistory, Episode):
    pass

class ClipHistory(PlexHistory, Clip):
    pass

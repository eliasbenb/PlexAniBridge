from functools import cached_property as cached_property

from _typeshed import Incomplete

from plexapi.base import Playable, PlexHistory, PlexPartialObject, PlexSession
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

class Video(PlexPartialObject, PlayedUnplayedMixin):
    ratingKey: int
    guid: str | None
    def url(self, part): ...
    def augmentation(self): ...
    def uploadSubtitles(self, filepath): ...
    def searchSubtitles(
        self, language: str = "en", hearingImpaired: int = 0, forced: int = 0
    ): ...
    def downloadSubtitles(self, subtitleStream): ...
    def removeSubtitles(
        self,
        subtitleStream: Incomplete | None = None,
        streamID: Incomplete | None = None,
        streamTitle: Incomplete | None = None,
    ): ...
    def optimize(
        self,
        title: str = "",
        target: str = "",
        deviceProfile: str = "",
        videoQuality: Incomplete | None = None,
        locationID: int = -1,
        limit: Incomplete | None = None,
        unwatched: bool = False,
    ): ...
    def sync(
        self,
        videoQuality,
        client: Incomplete | None = None,
        clientId: Incomplete | None = None,
        limit: Incomplete | None = None,
        unwatched: bool = False,
        title: Incomplete | None = None,
    ): ...

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
    @property
    def actors(self): ...
    @property
    def locations(self): ...
    @property
    def hasCreditsMarker(self): ...
    @property
    def hasVoiceActivity(self): ...
    @property
    def hasPreviewThumbnails(self): ...
    def reviews(self): ...
    def editions(self): ...
    def removeFromContinueWatching(self): ...
    @property
    def metadataDirectory(self): ...

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
    def __iter__(self): ...
    @property
    def actors(self): ...
    @property
    def isPlayed(self): ...
    def onDeck(self): ...
    def season(
        self, title: Incomplete | None = None, season: Incomplete | None = None
    ): ...
    def seasons(self, **kwargs): ...
    def episode(
        self,
        title: Incomplete | None = None,
        season: Incomplete | None = None,
        episode: Incomplete | None = None,
    ): ...
    def episodes(self, **kwargs): ...
    def get(
        self,
        title: Incomplete | None = None,
        season: Incomplete | None = None,
        episode: Incomplete | None = None,
    ): ...
    def watched(self): ...
    def unwatched(self): ...
    def download(
        self,
        savepath: Incomplete | None = None,
        keep_original_name: bool = False,
        subfolders: bool = False,
        **kwargs,
    ): ...
    @property
    def metadataDirectory(self): ...

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
    def __iter__(self): ...
    @property
    def isPlayed(self): ...
    @property
    def seasonNumber(self): ...
    def onDeck(self): ...
    def episode(
        self, title: Incomplete | None = None, episode: Incomplete | None = None
    ): ...
    def episodes(self, **kwargs): ...
    def get(
        self, title: Incomplete | None = None, episode: Incomplete | None = None
    ): ...
    def show(self): ...
    def watched(self): ...
    def unwatched(self): ...
    def download(
        self,
        savepath: Incomplete | None = None,
        keep_original_name: bool = False,
        **kwargs,
    ): ...
    @property
    def metadataDirectory(self): ...

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
    @cached_property
    def parentKey(self): ...
    @cached_property
    def parentRatingKey(self): ...
    @cached_property
    def parentThumb(self): ...
    @property
    def actors(self): ...
    @property
    def locations(self): ...
    @property
    def episodeNumber(self): ...
    @cached_property
    def seasonNumber(self): ...
    @property
    def seasonEpisode(self): ...
    @property
    def hasCommercialMarker(self): ...
    @property
    def hasIntroMarker(self): ...
    @property
    def hasCreditsMarker(self): ...
    @property
    def hasVoiceActivity(self): ...
    @property
    def hasPreviewThumbnails(self): ...
    def season(self): ...
    def show(self): ...
    def removeFromContinueWatching(self): ...
    @property
    def metadataDirectory(self): ...

class Clip(Video, Playable, ArtUrlMixin, PosterUrlMixin):
    TAG: str
    TYPE: str
    METADATA_TYPE: str
    @property
    def locations(self): ...
    @property
    def metadataDirectory(self): ...

class Extra(Clip): ...

class MovieSession(PlexSession, Movie):
    def reload(self, key: str | None = None, **kwargs): ...
    def _reload(self, key=None, _overwriteNone: bool = True, **kwargs): ...

class EpisodeSession(PlexSession, Episode):
    def reload(self, key: str | None = None, **kwargs): ...
    def _reload(self, key=None, _overwriteNone: bool = True, **kwargs): ...

class ClipSession(PlexSession, Clip):
    def reload(self, key: str | None = None, **kwargs): ...
    def _reload(self, key=None, _overwriteNone: bool = True, **kwargs): ...

class MovieHistory(PlexHistory, Movie):
    def reload(self, key: str | None = None, **kwargs): ...
    def _reload(
        self, key: str | None = None, _overwriteNone: bool = True, **kwargs
    ): ...

class EpisodeHistory(PlexHistory, Episode):
    def reload(self, key: str | None = None, **kwargs): ...
    def _reload(
        self, key: str | None = None, _overwriteNone: bool = True, **kwargs
    ): ...

class ClipHistory(PlexHistory, Clip):
    def reload(self, key: str | None = None, **kwargs): ...
    def _reload(
        self, key: str | None = None, _overwriteNone: bool = True, **kwargs
    ): ...

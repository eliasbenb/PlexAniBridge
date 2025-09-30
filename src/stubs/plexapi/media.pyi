from typing import Any

from plexapi.base import PlexObject
from plexapi.settings import Setting

class Media(PlexObject):
    aspectRatio: float | None
    audioChannels: int | None
    audioCodec: str | None
    audioProfile: str | None
    bitrate: int | None
    container: str | None
    duration: int | None
    height: int | None
    id: int | None
    has64bitOffsets: bool | None
    hasVoiceActivity: bool | None
    optimizedForStreaming: bool | None
    proxyType: int | None
    selected: bool | None
    target: str | None
    title: str | None
    videoCodec: str | None
    videoFrameRate: str | None
    videoProfile: str | None
    videoResolution: str | None
    width: int | None
    uuid: str | None
    aperture: str | None
    exposure: str | None
    iso: int | None
    lens: str | None
    make: str | None
    model: str | None
    _parentKey: str

    @property
    def parts(self) -> list[MediaPart]: ...
    @property
    def isOptimizedVersion(self) -> bool: ...
    def delete(self) -> Any: ...

class MediaPart(PlexObject):
    accessible: bool | None
    audioProfile: str | None
    container: str | None
    decision: str | None
    deepAnalysisVersion: int | None
    duration: int | None
    exists: bool | None
    file: str | None
    has64bitOffsets: bool | None
    hasThumbnail: bool | None
    id: int | None
    indexes: str | None
    optimizedForStreaming: bool | None
    packetLength: int | None
    protocol: str | None
    requiredBandwidths: str | None
    selected: bool | None
    size: int | None
    streams: list[MediaPartStream]
    syncItemId: int | None
    syncState: str | None
    videoProfile: str | None

    @property
    def hasPreviewThumbnails(self) -> bool: ...
    def videoStreams(self) -> list[VideoStream]: ...
    def audioStreams(self) -> list[AudioStream]: ...
    def subtitleStreams(self) -> list[SubtitleStream]: ...
    def lyricStreams(self) -> list[LyricStream]: ...
    def setSelectedAudioStream(self, stream: AudioStream | int) -> MediaPart: ...
    def setSelectedSubtitleStream(self, stream: SubtitleStream | int) -> MediaPart: ...
    def resetSelectedSubtitleStream(self) -> MediaPart: ...
    def setDefaultAudioStream(self, stream: AudioStream | int) -> MediaPart: ...
    def setDefaultSubtitleStream(self, stream: SubtitleStream | int) -> MediaPart: ...
    def resetDefaultSubtitleStream(self) -> MediaPart: ...

class MediaPartStream(PlexObject):
    bitrate: int | None
    codec: str | None
    decision: str | None
    default: bool | None
    displayTitle: str | None
    extendedDisplayTitle: str | None
    id: int | None
    index: int | None
    language: str | None
    languageCode: str | None
    languageTag: str | None
    location: str | None
    requiredBandwidths: str | None
    selected: bool | None
    streamType: int | None
    title: str | None
    type: int | None

class VideoStream(MediaPartStream):
    STREAMTYPE: int
    anamorphic: str | None
    bitDepth: int | None
    cabac: int | None
    chromaLocation: str | None
    chromaSubsampling: str | None
    codecID: str | None
    codedHeight: int | None
    codedWidth: int | None
    colorPrimaries: str | None
    colorRange: str | None
    colorSpace: str | None
    colorTrc: str | None
    DOVIBLCompatID: int | None
    DOVIBLPresent: bool | None
    DOVIELPresent: bool | None
    DOVILevel: int | None
    DOVIPresent: bool | None
    DOVIProfile: int | None
    DOVIRPUPresent: bool | None
    DOVIVersion: float | None
    duration: int | None
    frameRate: float | None
    frameRateMode: str | None
    hasScalingMatrix: bool | None
    height: int | None
    level: int | None
    profile: str | None
    pixelAspectRatio: str | None
    pixelFormat: str | None
    refFrames: int | None
    scanType: str | None
    streamIdentifier: int | None
    width: int | None

class AudioStream(MediaPartStream):
    STREAMTYPE: int
    audioChannelLayout: str | None
    bitDepth: int | None
    bitrateMode: str | None
    channels: int | None
    duration: int | None
    profile: str | None
    samplingRate: int | None
    streamIdentifier: int | None
    albumGain: float | None
    albumPeak: float | None
    albumRange: float | None
    endRamp: str | None
    gain: float | None
    loudness: float | None
    lra: float | None
    peak: float | None
    startRamp: str | None

    def setSelected(self) -> MediaPart: ...
    def setDefault(self) -> MediaPart: ...

class SubtitleStream(MediaPartStream):
    STREAMTYPE: int
    canAutoSync: bool | None
    container: str | None
    forced: bool | None
    format: str | None
    headerCompression: str | None
    hearingImpaired: bool | None
    perfectMatch: bool | None
    providerTitle: str | None
    score: int | None
    sourceKey: str | None
    transient: str | None
    userID: int | None

    def setSelected(self) -> MediaPart: ...
    def setDefault(self) -> MediaPart: ...

class LyricStream(MediaPartStream):
    STREAMTYPE: int
    format: str | None
    minLines: int | None
    provider: str | None
    timed: bool | None

class Session(PlexObject):
    id: str | None
    bandwidth: int | None
    location: str | None

class TranscodeSession(PlexObject):
    audioChannels: int | None
    audioCodec: str | None
    audioDecision: str | None
    complete: bool | None
    container: str | None
    context: str | None
    duration: int | None
    height: int | None
    maxOffsetAvailable: float | None
    minOffsetAvailable: float | None
    progress: float | None
    protocol: str | None
    remaining: int | None
    size: int | None
    sourceAudioCodec: str | None
    sourceVideoCodec: str | None
    speed: float | None
    subtitleDecision: str | None
    throttled: bool | None
    timestamp: float | None
    transcodeHwDecoding: str | None
    transcodeHwDecodingTitle: str | None
    transcodeHwEncoding: str | None
    transcodeHwEncodingTitle: str | None
    transcodeHwFullPipeline: bool | None
    transcodeHwRequested: bool | None
    videoCodec: str | None
    videoDecision: str | None
    width: int | None

class TranscodeJob(PlexObject):
    generatorID: str | None
    progress: str | None
    ratingKey: str | None
    size: str | None
    targetTagID: str | None
    thumb: str | None
    title: str | None
    type: str | None

class Optimized(PlexObject):
    id: str | None
    composite: str | None
    title: str | None
    type: str | None
    target: str | None
    targetTagID: str | None

    def items(self) -> list[Any]: ...
    def remove(self) -> None: ...
    def rename(self, title: str) -> None: ...
    def reprocess(self, ratingKey: str) -> None: ...

class Conversion(PlexObject):
    addedAt: str | None
    art: str | None
    chapterSource: str | None
    contentRating: str | None
    duration: str | None
    generatorID: str | None
    generatorType: str | None
    guid: str | None
    lastViewedAt: str | None
    librarySectionID: str | None
    librarySectionKey: str | None
    librarySectionTitle: str | None
    originallyAvailableAt: str | None
    playQueueItemID: str | None
    playlistID: str | None
    primaryExtraKey: str | None
    rating: str | None
    ratingKey: str | None
    studio: str | None
    summary: str | None
    tagline: str | None
    target: str | None
    thumb: str | None
    title: str | None
    type: str | None
    updatedAt: str | None
    userID: str | None
    username: str | None
    viewOffset: str | None
    year: str | None

    def remove(self) -> None: ...
    def move(self, after: str) -> None: ...

class MediaTag(PlexObject):
    filter: str | None
    id: int | None
    role: str | None
    tag: str | None
    tagKey: str | None
    thumb: str | None
    _librarySectionID: int | None
    _librarySectionKey: str | None
    _librarySectionTitle: str | None
    _parentType: str

    def items(self) -> list[Any]: ...

class Collection(MediaTag):
    FILTER: str

    def collection(self) -> Any: ...

class Country(MediaTag):
    FILTER: str

class Director(MediaTag):
    FILTER: str

class Format(MediaTag):
    FILTER: str

class Genre(MediaTag):
    FILTER: str

class Label(MediaTag):
    FILTER: str

class Mood(MediaTag):
    FILTER: str

class Producer(MediaTag):
    FILTER: str

class Role(MediaTag):
    FILTER: str

class Similar(MediaTag):
    FILTER: str

class Style(MediaTag):
    FILTER: str

class Subformat(MediaTag):
    FILTER: str

class Tag(MediaTag):
    FILTER: str

class Writer(MediaTag):
    FILTER: str

class Guid(PlexObject):
    id: str | None

class Image(PlexObject):
    alt: str | None
    type: str | None
    url: str | None

class Rating(PlexObject):
    image: str | None
    type: str | None
    value: float | None

class Review(PlexObject):
    filter: str | None
    id: int | None
    image: str | None
    link: str | None
    source: str | None
    tag: str | None
    text: str | None

class UltraBlurColors(PlexObject):
    bottomLeft: str | None
    bottomRight: str | None
    topLeft: str | None
    topRight: str | None

class BaseResource(PlexObject):
    provider: str | None
    ratingKey: str | None
    selected: bool | None
    thumb: str | None

    def select(self) -> None: ...
    @property
    def resourceFilepath(self) -> str: ...

class Art(BaseResource):
    pass

class Logo(BaseResource):
    pass

class Poster(BaseResource):
    pass

class Theme(BaseResource):
    pass

class Chapter(PlexObject):
    end: int | None
    filter: str | None
    id: int | None
    index: int | None
    tag: str | None
    title: str | None
    thumb: str | None
    start: int | None

class Marker(PlexObject):
    end: int | None
    final: bool | None
    id: int | None
    type: str | None
    start: int | None
    version: str | None

    @property
    def first(self) -> bool | None: ...

class Field(PlexObject):
    locked: bool | None
    name: str | None

class SearchResult(PlexObject):
    guid: str | None
    lifespanEnded: str | None
    name: str | None
    score: int | None
    year: str | None

class Agent(PlexObject):
    hasAttribution: str | None
    hasPrefs: str | None
    identifier: str | None
    name: str | None
    primary: str | None
    shortIdentifier: str | None
    languageCodes: list[str]
    mediaTypes: list[AgentMediaType]

    @property
    def languageCode(self) -> list[str]: ...
    def settings(self) -> list[Setting]: ...
    def _settings(self) -> list[Setting]: ...

class AgentMediaType(Agent):
    mediaType: int | None
    name: str | None

    @property
    def languageCode(self) -> list[str]: ...

class Availability(PlexObject):
    country: str | None
    offerType: str | None
    platform: str | None
    platformColorThumb: str | None
    platformInfo: str | None
    platformUrl: str | None
    price: float | None
    priceDescription: str | None
    quality: str | None
    title: str | None
    url: str | None

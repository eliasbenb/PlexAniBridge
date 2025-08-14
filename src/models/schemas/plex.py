"""Plex schema definitions.

The models stored here won't be defined in the python-plexapi or the custom metadata
server implementation and are reserved for more niche use cases.
"""

from enum import StrEnum
from functools import cached_property

from pydantic import BaseModel, Field


class PlexWebhookEventType(StrEnum):
    """Enumeration of Plex webhook event types."""

    MEDIA_ADDED = "library.new"
    ON_DECK = "library.on.deck"
    PLAY = "media.play"
    PAUSE = "media.pause"
    STOP = "media.stop"
    RESUME = "media.resume"
    SCROBBLE = "media.scrobble"
    RATE = "media.rate"
    DATABASE_BACKUP = "admin.database.backup"
    DATABASE_CORRUPTED = "admin.database.corrupted"
    NEW_ADMIN_DEVICE = "device.new"
    SHARED_PLAYBACK_STARTED = "playback.started"


class Account(BaseModel):
    """Represents a Plex account involved in a webhook event.

    Attributes:
        id (int | None): Unique identifier for the account.
        thumb (str | None): URL or path to the account's thumbnail image.
        title (str | None): Display name of the account.
    """

    id: int | None = None
    thumb: str | None = None
    title: str | None = None


class Server(BaseModel):
    """Represents a Plex server involved in a webhook event.

    Attributes:
        title (str | None): Display name of the server.
        uuid (str | None): Unique identifier for the server.
    """

    title: str | None = None
    uuid: str | None = None


class Player(BaseModel):
    """Represents a Plex player involved in a webhook event.

    Attributes:
        local (bool): Indicates if the player is local.
        publicAddress (str | None): Public IP address of the player.
        title (str | None): Display name of the player.
        uuid (str | None): Unique identifier for the player.
    """

    local: bool
    publicAddress: str | None = None
    title: str | None = None
    uuid: str | None = None


class Metadata(BaseModel):
    """Represents metadata information received from a Plex webhook event.

    Attributes:
        librarySectionType (str | None): The type of the library section.
        ratingKey (str | None): Unique key identifying the media item.
        key (str | None): The key path to the media item.
        parentRatingKey (str | None): Unique key for the parent media item.
        grandparentRatingKey (str | None): Unique key for the grandparent media item.
        guid (str | None): Globally unique identifier for the media item.
        librarySectionID (int | None): ID of the library section.
        type (str | None): The type of media (e.g., 'episode', 'movie').
        title (str | None): Title of the media item.
        year (int | None): Release year.
        grandparentKey (str | None): Key path to the grandparent media item.
        parentKey (str | None): Key path to the parent media item.
        grandparentTitle (str | None): Title of the grandparent media item.
        parentTitle (str | None): Title of the parent media item.
        summary (str | None): Summary or description of the media item.
        index (int | None): Index of the media item within its parent.
        parentIndex (int | None): Index of the parent media item within its grandparent.
        ratingCount (int | None): Number of ratings for the media item.
        thumb (str | None): URL or path to the thumbnail image of the media item.
        art (str | None): URL or path to the artwork image of the media item.
        parentThumb (str | None): URL or path to the thumbnail of the parent media item.
        grandparentThumb (str | None): URL/path to the thumbnail of the grandparent.
        grandparentArt (str | None): URL/path to the artwork of the grandparent.
        addedAt (int | None): Unix timestamp when the media item was added.
        updatedAt (int | None): Unix timestamp when the media item was last updated.
    """

    librarySectionType: str | None = None
    ratingKey: str | None = None
    key: str | None = None
    parentRatingKey: str | None = None
    grandparentRatingKey: str | None = None
    guid: str | None = None
    librarySectionID: int | None = None
    type: str | None = None
    title: str | None = None
    year: int | None = None
    grandparentKey: str | None = None
    parentKey: str | None = None
    grandparentTitle: str | None = None
    parentTitle: str | None = None
    summary: str | None = None
    index: int | None = None
    parentIndex: int | None = None
    ratingCount: int | None = None
    thumb: str | None = None
    art: str | None = None
    parentThumb: str | None = None
    grandparentThumb: str | None = None
    grandparentArt: str | None = None
    addedAt: int | None = None
    updatedAt: int | None = None


class PlexWebhook(BaseModel):
    """Represents a Plex webhook event.

    Attributes:
        event (str | None): Type of the event.
        user (bool): Indicates if the event was triggered by a user.
        owner (bool): Indicates if the event was triggered by the owner.
        account (Account | None): Account information.
        server (Server | None): Server information.
        player (Player | None): Player information.
        metadata (Metadata | None): Metadata information.
    """

    event: str | None = None
    user: bool
    owner: bool
    account: Account | None = Field(None, alias="Account")
    server: Server | None = Field(None, alias="Server")
    player: Player | None = Field(None, alias="Player")
    metadata: Metadata | None = Field(None, alias="Metadata")

    @cached_property
    def event_type(self) -> PlexWebhookEventType | None:
        """The webhook event type."""
        if self.event is None:
            return None
        try:
            return PlexWebhookEventType(self.event)
        except ValueError:
            return None

    @cached_property
    def account_id(self) -> int | None:
        """The webhook owner's Plex account ID."""
        return self.account.id if self.account and self.account.id is not None else None

    @cached_property
    def top_level_rating_key(self) -> str | None:
        """The top-level rating key for the media item."""
        if not self.metadata:
            return None
        return (
            self.metadata.grandparentRatingKey
            or self.metadata.parentRatingKey
            or self.metadata.ratingKey
        )

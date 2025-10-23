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
    """Represents a Plex account involved in a webhook event."""

    id: int | None = None
    thumb: str | None = None
    title: str | None = None


class Server(BaseModel):
    """Represents a Plex server involved in a webhook event."""

    title: str | None = None
    uuid: str | None = None


class Player(BaseModel):
    """Represents a Plex player involved in a webhook event."""

    local: bool
    publicAddress: str | None = None
    title: str | None = None
    uuid: str | None = None


class Metadata(BaseModel):
    """Represents metadata information received from a Plex webhook event."""

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
    """Represents a Plex webhook event."""

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

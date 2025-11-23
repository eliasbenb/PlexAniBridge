"""AniList list provider implementation."""

import contextlib
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from src.core.providers.list import (
    ListEntry,
    ListMedia,
    ListMediaType,
    ListProvider,
    ListStatus,
    ListUser,
    ProviderBackupEntries,
)
from src.models.schemas.anilist import (
    FuzzyDate,
    Media,
    MediaFormat,
    MediaList,
    MediaListStatus,
    ScoreFormat,
)
from src.providers.anilist.client import AniListClient


class AniListListMedia(ListMedia):
    """AniList list media implementation."""

    def __init__(self, provider: AniListListProvider, media: Media) -> None:
        """Initialize the AniList list media.

        Args:
            provider (AniListListProvider): The list provider instance.
            media (Media): The AniList media object.
        """
        self._provider = provider
        self._media = media

        self.key = str(media.id)
        self.title = (
            media.title.romaji or media.title.english or "" if media.title else ""
        )

    @property
    def media_type(self) -> ListMediaType:
        """Get the type of media (e.g., ANIME, MANGA)."""
        match self._media.format:
            case MediaFormat.TV:
                return ListMediaType.TV
            case _:
                return ListMediaType.MOVIE

    @property
    def total_units(self) -> int | None:
        """Return the total number of units (e.g. episodes) for the media."""
        if self._media.episodes:
            return self._media.episodes
        if self._media.format == MediaFormat.MOVIE:
            return 1
        return None

    @property
    def poster_image(self) -> str | None:
        """Return the best available cover image URL for the media."""
        image = self._media.cover_image
        if image is None:
            return None
        return image.extra_large or image.large or image.medium or image.color

    def provider(self) -> AniListListProvider:
        """Get the list provider associated with the media.

        Returns:
            AniListListProvider: The list provider instance.
        """
        return self._provider


class AniListListEntry(ListEntry):
    """AniList list entry implementation."""

    def __init__(
        self, provider: AniListListProvider, media: Media, entry: MediaList
    ) -> None:
        """Initialize the AniList list entry.

        Args:
            provider (AniListListProvider): The list provider instance.
            media (Media): The AniList media object.
            entry (MediaList): The AniList media list entry object.
        """
        self._provider = provider
        self._media = AniListListMedia(provider, media)
        self._entry = entry

        self.key = str(entry.id)
        self.title = (
            media.title.romaji or media.title.english or "" if media.title else ""
        )

    @property
    def status(self) -> ListStatus | None:
        """Get the status of the list entry."""
        if self._entry.status is None:
            return None
        match self._entry.status:
            case MediaListStatus.COMPLETED:
                return ListStatus.COMPLETED
            case MediaListStatus.CURRENT:
                return ListStatus.CURRENT
            case MediaListStatus.DROPPED:
                return ListStatus.DROPPED
            case MediaListStatus.PAUSED:
                return ListStatus.PAUSED
            case MediaListStatus.PLANNING:
                return ListStatus.PLANNING
            case MediaListStatus.REPEATING:
                return ListStatus.REPEATING
            case _:
                return None

    @status.setter
    def status(self, value: ListStatus | None) -> None:
        """Update the status represented by the entry."""
        if value is None:
            self._entry.status = None
            return

        match value:
            case ListStatus.COMPLETED:
                self._entry.status = MediaListStatus.COMPLETED
            case ListStatus.CURRENT:
                self._entry.status = MediaListStatus.CURRENT
            case ListStatus.DROPPED:
                self._entry.status = MediaListStatus.DROPPED
            case ListStatus.PAUSED:
                self._entry.status = MediaListStatus.PAUSED
            case ListStatus.PLANNING:
                self._entry.status = MediaListStatus.PLANNING
            case ListStatus.REPEATING:
                self._entry.status = MediaListStatus.REPEATING
            case _:
                raise ValueError(f"Unsupported list status: {value}")

    @property
    def progress(self) -> int:
        """Get the progress of the list entry."""
        return self._entry.progress or 0

    @progress.setter
    def progress(self, value: int | None) -> None:
        """Update the tracked progress for the entry."""
        if value is None:
            self._entry.progress = None
            return
        if value < 0:
            raise ValueError("Progress cannot be negative.")
        self._entry.progress = value

    @property
    def repeats(self) -> int:
        """Get the repeat count of the list entry."""
        return self._entry.repeat or 0

    @repeats.setter
    def repeats(self, value: int | None) -> None:
        """Update the repeat counter for the entry."""
        if value is None:
            self._entry.repeat = None
            return
        if value < 0:
            raise ValueError("Repeat count cannot be negative.")
        self._entry.repeat = value

    @property
    def user_rating(self) -> int | None:
        """Get the user rating of the list entry."""
        if self._entry.score is None:
            return None

        anilist_user = self._provider._client.user
        score_format = ScoreFormat.POINT_100
        if anilist_user and anilist_user.media_list_options is not None:
            score_format = anilist_user.media_list_options.score_format

        match score_format:
            case ScoreFormat.POINT_100:
                return int(self._entry.score)
            case ScoreFormat.POINT_10_DECIMAL:
                return int(self._entry.score * 10)
            case ScoreFormat.POINT_10:
                return int(self._entry.score * 10)
            case ScoreFormat.POINT_5:
                return int(self._entry.score * 20)
            case ScoreFormat.POINT_3:
                return int(self._entry.score * (100 / 3))
            case _:
                return int(self._entry.score)

    @user_rating.setter
    def user_rating(self, value: int | None) -> None:
        """Update the user rating, converting to AniList's score scale."""
        if value is None:
            self._entry.score = None
            return

        if value < 0 or value > 100:
            raise ValueError("Ratings must be between 0 and 100.")

        score_format = self._score_format()
        match score_format:
            case ScoreFormat.POINT_100:
                self._entry.score = float(value)
            case ScoreFormat.POINT_10_DECIMAL:
                self._entry.score = value / 10
            case ScoreFormat.POINT_10:
                self._entry.score = round(value / 10)
            case ScoreFormat.POINT_5:
                self._entry.score = round(value / 20)
            case ScoreFormat.POINT_3:
                self._entry.score = value * 3 / 100
            case _:
                self._entry.score = float(value)

    @property
    def started_at(self) -> datetime | None:
        """Get the start date of the list entry."""
        if self._entry.started_at is None:
            return None
        return self._entry.started_at.to_datetime()

    @started_at.setter
    def started_at(self, value: datetime | None) -> None:
        """Update the recorded start date."""
        self._entry.started_at = FuzzyDate.from_date(value)

    @property
    def finished_at(self) -> datetime | None:
        """Get the finish date of the list entry."""
        if self._entry.completed_at is None:
            return None
        return self._entry.completed_at.to_datetime()

    @finished_at.setter
    def finished_at(self, value: datetime | None) -> None:
        """Update the recorded finish date."""
        self._entry.completed_at = FuzzyDate.from_date(value)

    @property
    def review(self) -> str | None:
        """Get the review of the list entry.

        Returns:
            str | None: The review text, or None if not set.
        """
        return self._entry.notes

    @review.setter
    def review(self, value: str | None) -> None:
        """Update the review text."""
        self._entry.notes = value

    @property
    def total_units(self) -> int | None:
        """Return the total number of units for the media if known."""
        if self._media.total_units is not None:
            return self._media.total_units
        if self._media.media_type == MediaFormat.MOVIE:
            return 1
        return None

    def media(self) -> AniListListMedia:
        """Get the media item associated with the list entry.

        Returns:
            AniListListMedia: The media item.
        """
        return self._media

    def provider(self) -> AniListListProvider:
        """Get the list provider for this entry.

        Returns:
            AniListListProvider: The owning list provider instance.
        """
        return self._provider

    def _score_format(self) -> ScoreFormat:
        """Return the score format configured for the current user.

        Returns:
            ScoreFormat: The user's score format.
        """
        user = self._provider._client.user
        if user and user.media_list_options is not None:
            score_format = user.media_list_options.score_format
            if score_format is not None:
                return score_format
        return ScoreFormat.POINT_100


class AniListListProvider(ListProvider):
    """List provider implementation backed by the AniList GraphQL API."""

    NAMESPACE = "anilist"

    def __init__(self, *, config: dict | None = None) -> None:
        """Initialize the AniList list provider.

        Args:
            config (dict | None): Optional configuration options for the provider.
        """
        super().__init__(config=config)
        token = self.config.get("token")
        backup_dir = self.config.get("backup_dir")
        dry_run = bool(self.config.get("dry_run", False))
        profile_name = self.config.get("profile_name", "default")

        backup_path = None
        if backup_dir is not None:
            backup_path = Path(backup_dir)

        self._client = AniListClient(
            anilist_token=token,
            backup_dir=backup_path,
            dry_run=dry_run,
            profile_name=profile_name,
        )

        self._user: ListUser | None = None

    async def initialize(self) -> None:
        """Perform any asynchronous startup work before the provider is used."""
        await self._client.initialize()
        user = await self._client.get_user()
        if user is not None:
            self._user = ListUser(
                key=str(user.id),
                title=user.name,
            )

    async def backup_list(self) -> str:
        """Backup the entire list from AniList.

        Returns:
            str: The backup data as a string to be dumped.
        """
        return await self._client.backup_anilist()

    async def delete_entry(self, key: str) -> None:
        """Delete a list entry by its media key.

        Args:
            key (str): The media key of the entry to delete.
        """
        media = await self._client.get_anime(int(key))
        if not media.media_list_entry:
            return
        await self._client.delete_anime_entry(
            entry_id=media.media_list_entry.id,
            media_id=media.media_list_entry.media_id,
        )

    async def get_entry(self, key: str) -> AniListListEntry | None:
        """Retrieve a list entry by its media key.

        Args:
            key (str): The media key of the entry to retrieve.
        """
        media = await self._client.get_anime(int(key))
        if media.media_list_entry is None:
            return None
        return AniListListEntry(self, media=media, entry=media.media_list_entry)

    async def build_entry(self, key: str) -> AniListListEntry:
        """Construct an AniList list entry for the supplied media key."""
        media = await self._client.get_anime(int(key))
        entry = media.media_list_entry or MediaList(
            id=0,
            user_id=self._client.user.id if self._client.user else 0,
            media_id=media.id,
        )
        return AniListListEntry(self, media=media, entry=entry)

    async def restore_list(self, backup: str) -> None:
        """Restore the list from a backup sequence of list entries."""
        # TODO: Implement list restoration.
        raise NotImplementedError("AniList list restore is not implemented yet")

    async def search(self, query: str) -> Sequence[AniListListEntry]:
        """Search AniList for entries matching the query.

        Args:
            query (str): The search query string.

        Returns:
            Sequence[AniListListEntry]: The sequence of matching entries.
        """
        results: list[AniListListEntry] = []
        async for media in self._client.search_anime(query, is_movie=None, limit=10):
            entry = media.media_list_entry or MediaList(
                id=0,
                user_id=self._client.user.id if self._client.user else 0,
                media_id=media.id,
            )
            results.append(AniListListEntry(self, media=media, entry=entry))
        return results

    async def update_entry(self, key: str, entry: ListEntry) -> None:
        """Update a list entry with new information.

        Args:
            key (str): The media key of the entry to update.
            entry (ListEntry): The updated list entry data.
        """
        payload = await self._build_media_payload(key, cast(AniListListEntry, entry))
        await self._client.update_anime_entry(payload)

    def user(self) -> ListUser | None:
        """Get the user associated with the list.

        Returns:
            ListUser | None: The user information, or None if not available.
        """
        return self._user

    async def clear_cache(self) -> None:
        """Clear any cached data within the provider."""
        self._client.offline_anilist_entries.clear()

    async def close(self) -> None:
        """Perform any asynchronous cleanup work before the provider is closed."""
        await self._client.close()

    async def update_entries_batch(
        self, entries: Sequence[ListEntry]
    ) -> Sequence[AniListListEntry | None]:
        """Update multiple list entries in a single operation.

        Args:
            entries (Sequence[ListEntry]): The list entries to update.

        Returns:
            Sequence[AniListListEntry | None]: The sequence of updated entries.
        """
        payloads: list[MediaList] = []
        for entry in entries:
            payloads.append(
                await self._build_media_payload(
                    entry.media().key, cast(AniListListEntry, entry)
                )
            )
        if payloads:
            await self._client.batch_update_anime_entries(payloads)
        return [None] * len(entries)

    async def restore_entries(self, entries: Sequence[object]) -> None:
        """Restore AniList entries from serialized MediaList payloads."""
        if not entries:
            return
        payloads = [cast(MediaList, entry) for entry in entries]
        await self._client.batch_update_anime_entries(payloads)

    def deserialize_backup_entries(
        self, payload: dict[str, Any]
    ) -> ProviderBackupEntries:
        """Convert AniList backup JSON into MediaList restore payloads."""
        entries: list[MediaList] = []
        user = None

        with contextlib.suppress(Exception):
            user = payload.get("user", {}).get("name")

        for group in payload.get("lists", []) or []:
            if group.get("isCustomList"):
                continue
            for entry in group.get("entries", []) or []:
                try:
                    entries.append(MediaList(**entry))
                except Exception:
                    continue

        return ProviderBackupEntries(entries=entries, user=user)

    async def get_entries_batch(
        self, keys: Sequence[str]
    ) -> Sequence[AniListListEntry | None]:
        """Get multiple list entries by their media keys.

        Args:
            keys (Sequence[str]): The media keys of the entries to retrieve.

        Returns:
            Sequence[AniListListEntry | None]: The sequence of retrieved entries.
        """
        ids = [int(key) for key in keys]
        if not ids:
            return [None] * len(keys)

        medias = await self._client.batch_get_anime(ids)
        media_by_id = {media.id: media for media in medias}
        entries: list[AniListListEntry | None] = []
        for key in keys:
            media = media_by_id.get(int(key))
            if media is None or media.media_list_entry is None:
                entries.append(None)
                continue
            entries.append(
                AniListListEntry(self, media=media, entry=media.media_list_entry)
            )
        return entries

    async def _build_media_payload(
        self, media_key: str | int, entry: AniListListEntry
    ) -> MediaList:
        """Build the MediaList payload for updating an entry."""
        media_id = int(media_key)
        media = await self._client.get_anime(media_id)
        base_entry = media.media_list_entry or MediaList(
            id=0,
            user_id=self._client.user.id if self._client.user else 0,
            media_id=media.id,
        )

        match entry.status:
            case ListStatus.COMPLETED:
                status = MediaListStatus.COMPLETED
            case ListStatus.CURRENT:
                status = MediaListStatus.CURRENT
            case ListStatus.DROPPED:
                status = MediaListStatus.DROPPED
            case ListStatus.PAUSED:
                status = MediaListStatus.PAUSED
            case ListStatus.PLANNING:
                status = MediaListStatus.PLANNING
            case ListStatus.REPEATING:
                status = MediaListStatus.REPEATING
            case _:
                status = base_entry.status

        return MediaList(
            id=base_entry.id,
            user_id=base_entry.user_id,
            media_id=base_entry.media_id,
            status=status,
            score=float(entry.user_rating) if entry.user_rating is not None else None,
            progress=entry.progress,
            repeat=entry.repeats,
            notes=entry.review,
            started_at=FuzzyDate.from_date(entry.started_at) or base_entry.started_at,
            completed_at=FuzzyDate.from_date(entry.finished_at)
            or base_entry.completed_at,
        )

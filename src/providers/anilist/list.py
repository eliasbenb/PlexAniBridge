"""AniList list provider implementation."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import cast

from src.core.providers.list import ListEntry, ListProvider, ListStatus, ListUser
from src.models.schemas.anilist import (
    FuzzyDate,
    Media,
    MediaList,
    MediaListStatus,
    ScoreFormat,
)
from src.providers.anilist.client import AniListClient


class AniListListEntry(ListEntry):
    """AniList list entry implementation."""

    def __init__(
        self, provider: AniListListProvider, media: Media, entry: MediaList
    ) -> None:
        """Initialize the AniList list entry."""
        self._provider = provider
        self._media = media
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

    @property
    def progress(self) -> int:
        """Get the progress of the list entry."""
        return self._entry.progress or 0

    @property
    def repeats(self) -> int:
        """Get the repeat count of the list entry."""
        return self._entry.repeat or 0

    @property
    def user_rating(self) -> int | None:
        """Get the user rating of the list entry."""
        if self._entry.score is None:
            return None

        anilist_user = self._provider._client.user
        score_format = ScoreFormat.POINT_100
        if anilist_user.media_list_options is not None:
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

    @property
    def started_at(self) -> datetime | None:
        """Get the start date of the list entry."""
        if self._entry.started_at is None:
            return None
        return self._entry.started_at.to_datetime()

    @property
    def finished_at(self) -> datetime | None:
        """Get the finish date of the list entry."""
        if self._entry.completed_at is None:
            return None
        return self._entry.completed_at.to_datetime()

    @property
    def review(self) -> str | None:
        """Get the review of the list entry."""
        return self._entry.notes

    def provider(self) -> AniListListProvider:
        """Get the list provider for this entry."""
        return self._provider


class AniListListProvider(ListProvider):
    """List provider implementation backed by the AniList GraphQL API."""

    NAMESPACE = "anilist"

    def __init__(self, *, config: dict | None = None) -> None:
        """Initialize the AniList list provider."""
        super().__init__(config=config)
        token = self.config.get("token")
        backup_dir = self.config.get("backup_dir")
        dry_run = bool(self.config.get("dry_run", False))
        profile_name = self.config.get("profile_name") or "default"
        retention = self.config.get("backup_retention_days")

        backup_path = None
        if backup_dir is not None:
            backup_path = Path(backup_dir)

        self._client = AniListClient(
            anilist_token=token,
            backup_dir=backup_path,
            dry_run=dry_run,
            profile_name=profile_name,
            backup_retention_days=retention,
        )

        self._user: ListUser | None = None

    async def initialize(self) -> None:
        """Perform any asynchronous startup work before the provider is used."""
        await self._client.initialize()
        if self._client.user is not None:
            self._user = ListUser(
                key=str(self._client.user.id),
                display_name=self._client.user.name,
            )

    async def backup_list(self) -> str:
        """Backup the entire list from AniList."""
        # TODO: Instead of reading the file back, refactor the client to return the
        # data directly.
        backup_file = await self._client.backup_anilist()
        return backup_file.read_text(encoding="utf-8")

    async def delete_entry(self, media_key: str) -> None:
        """Delete a list entry by its media key."""
        media = await self._client.get_anime(int(media_key))
        if not media.media_list_entry:
            return
        await self._client.delete_anime_entry(
            entry_id=media.media_list_entry.id,
            media_id=media.media_list_entry.media_id,
        )

    async def get_entry(self, media_key: str) -> AniListListEntry | None:
        """Retrieve a list entry by its media key."""
        media = await self._client.get_anime(int(media_key))
        entry = media.media_list_entry
        if entry is None:
            return None
        return AniListListEntry(self, media=media, entry=entry)

    async def restore_list(self, backup: str) -> None:
        """Restore the list from a backup sequence of list entries."""
        # TODO: Implement list restoration.
        raise NotImplementedError("AniList list restore is not implemented yet")

    async def search(self, query: str) -> Sequence[ListEntry]:
        """Search AniList for entries matching the query."""
        results: list[AniListListEntry] = []
        async for media in self._client.search_anime(query, is_movie=None, limit=10):
            entry = media.media_list_entry or MediaList(
                id=0,
                user_id=self._client.user.id if self._client.user else 0,
                media_id=media.id,
            )
            results.append(AniListListEntry(self, media=media, entry=entry))
        return cast(Sequence[ListEntry], results)

    async def update_entry(self, media_key: str, entry: ListEntry) -> None:
        """Update a list entry with new information."""
        payload = await self._build_media_payload(media_key, entry)
        await self._client.update_anime_entry(payload)

    async def user(self) -> ListUser | None:
        """Get the user associated with the list."""
        return self._user

    def clear_cache(self) -> None:
        """Clear any cached data within the provider."""
        self._client.offline_anilist_entries.clear()

    async def close(self) -> None:
        """Perform any asynchronous cleanup work before the provider is closed."""
        await self._client.close()

    async def update_entries_batch(self, entries: Sequence[ListEntry]) -> None:
        """Update multiple list entries in a single operation."""
        payloads: list[MediaList] = []
        for entry in entries:
            payloads.append(await self._build_media_payload(entry.key, entry))
        if payloads:
            await self._client.batch_update_anime_entries(payloads)

    async def _build_media_payload(
        self, media_key: str | int, entry: ListEntry
    ) -> MediaList:
        media_id = int(media_key)
        media = await self._client.get_anime(media_id)
        base_entry = media.media_list_entry
        if base_entry is None:
            raise ValueError(f"No AniList entry exists for media id {media_id}")

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

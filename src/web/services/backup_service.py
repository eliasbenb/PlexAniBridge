"""Backup listing and restore service."""

import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import BaseModel

from src.exceptions import (
    BackupFileNotFoundError,
    InvalidBackupFilenameError,
    ProfileNotFoundError,
    SchedulerNotInitializedError,
)
from src.models.schemas.anilist import MediaList
from src.web.state import get_app_state

__all__ = ["BackupService", "get_backup_service"]


class BackupMeta(BaseModel):
    """Metadata about a backup file used for listing in the UI."""

    filename: str
    created_at: datetime
    size_bytes: int
    entries: int | None = None
    user: str | None = None
    age_seconds: float


class RestoreSummary(BaseModel):
    """Result of a restore operation."""

    ok: bool
    filename: str
    total_entries: int
    processed: int
    restored: int
    skipped: int
    errors: list[dict[str, Any]]
    elapsed_seconds: float


@dataclass
class _ParsedBackup:
    entries: list[MediaList]
    user: str | None


class BackupService:
    """Service for listing and restoring AniList backups."""

    def _get_profile_bridge(self, profile: str):
        """Get the scheduler bridge client for a profile."""
        scheduler = get_app_state().scheduler
        if not scheduler:
            raise SchedulerNotInitializedError("Scheduler not initialised")
        bridge = scheduler.bridge_clients.get(profile)
        if not bridge:
            raise ProfileNotFoundError(f"Unknown profile: {profile}")
        return bridge

    def _backup_dir(self, profile: str) -> Path:
        """Get the backup directory for a profile."""
        bridge = self._get_profile_bridge(profile)
        return bridge.profile_config.data_path / "backups"

    def list_backups(self, profile: str) -> list[BackupMeta]:
        """Enumerate available backups for a profile.

        Args:
            profile: Profile name.

        Returns:
            list[BackupMeta]: List of backup metadata, newest first.
        """
        bdir = self._backup_dir(profile)
        if not bdir.exists():
            return []
        metas: list[BackupMeta] = []
        now = datetime.now(UTC)

        anilist_client = self._get_profile_bridge(profile).anilist_client

        for f in sorted(bdir.glob(f"plexanibridge-{profile}.*.json")):
            try:
                parts = f.name.split(".")
                ts_raw = parts[-2] if len(parts) >= 2 else None
                dt: datetime | None = None
                if ts_raw and ts_raw.isdigit():
                    try:
                        dt = datetime.strptime(ts_raw, "%Y%m%d%H%M%S").replace(
                            tzinfo=UTC
                        )
                    except ValueError:
                        dt = datetime.fromtimestamp(f.stat().st_mtime, UTC)
                else:
                    dt = datetime.fromtimestamp(f.stat().st_mtime, UTC)
                metas.append(
                    BackupMeta(
                        filename=f.name,
                        created_at=dt,
                        size_bytes=f.stat().st_size,
                        entries=None,  # Can be populated on demand
                        user=anilist_client.user.name,
                        age_seconds=(now - dt).total_seconds(),
                    )
                )
            except Exception:
                continue
        return list(reversed(metas))  # Newest first

    def read_backup_raw(self, profile: str, filename: str) -> dict[str, Any]:
        """Return the raw JSON content of a backup file.

        Args:
            profile: Profile name
            filename: Backup filename (basename only)

        Returns:
            dict[str, Any]: Parsed JSON content.
        """
        bdir = self._backup_dir(profile)
        path = (bdir / filename).resolve()
        if path.parent != bdir.resolve():  # Path traversal protection
            raise InvalidBackupFilenameError("Invalid backup filename")
        if not path.exists():
            raise BackupFileNotFoundError("Backup file not found")

        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _parse_backup(self, profile: str, filename: str) -> _ParsedBackup:
        """Parse a backup file and return its entries."""
        bdir = self._backup_dir(profile)
        path = (bdir / filename).resolve()

        if path.parent != bdir.resolve():
            raise InvalidBackupFilenameError("Invalid backup filename")
        if not path.exists():
            raise BackupFileNotFoundError("Backup file not found")

        raw = json.loads(path.read_text())
        user = None

        with contextlib.suppress(Exception):
            user = raw.get("user", {}).get("name")
        entries: list[MediaList] = []

        for lst in raw.get("lists", []) or []:
            if lst.get("isCustomList"):
                continue
            for entry in lst.get("entries", []) or []:
                try:
                    entries.append(MediaList(**entry))
                except Exception:
                    continue
        return _ParsedBackup(entries=entries, user=user)

    async def restore_backup(self, profile: str, filename: str) -> RestoreSummary:
        """Restore a backup file for a profile.

        Args:
            profile: Profile name
            filename: Backup filename (basename only)
        """
        bridge = self._get_profile_bridge(profile)
        parsed = self._parse_backup(profile, filename)
        total = len(parsed.entries)
        start = perf_counter()
        errors: list[dict[str, Any]] = []

        BATCH = 50
        restored = 0
        for i in range(0, total, BATCH):
            batch = parsed.entries[i : i + BATCH]
            try:
                await bridge.anilist_client.batch_update_anime_entries(batch)
                restored += len(batch)
            except Exception as e:
                errors.append(
                    {
                        "index_start": i,
                        "count": len(batch),
                        "error": str(e),
                    }
                )

        return RestoreSummary(
            ok=not errors,
            filename=filename,
            total_entries=total,
            processed=total,
            restored=restored,
            skipped=0,
            errors=errors,
            elapsed_seconds=perf_counter() - start,
        )


@lru_cache(maxsize=1)
def get_backup_service() -> BackupService:
    """Get the singleton BackupService instance.

    Returns:
        BackupService: The singleton BackupService instance.
    """
    return BackupService()

"""Backup listing and restore service."""

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import BaseModel

from src import log
from src.exceptions import (
    BackupFileNotFoundError,
    BackupParseError,
    InvalidBackupFilenameError,
    ProfileNotFoundError,
    SchedulerNotInitializedError,
)
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


class BackupService:
    """Service for listing and restoring provider-managed backups."""

    def _get_profile_bridge(self, profile: str):
        """Get the scheduler bridge client for a profile."""
        scheduler = get_app_state().scheduler
        if not scheduler:
            raise SchedulerNotInitializedError("Scheduler not available")
        bridge = scheduler.bridge_clients.get(profile)
        if not bridge:
            raise ProfileNotFoundError(f"Unknown profile: {profile}")
        return bridge

    def _backup_dir(self, profile: str) -> Path:
        """Get the backup directory for a profile."""
        bridge = self._get_profile_bridge(profile)
        return bridge.global_config.data_path / "backups"

    def list_backups(self, profile: str) -> list[BackupMeta]:
        """Enumerate available backups for a profile.

        Args:
            profile: Profile name.

        Returns:
            list[BackupMeta]: List of backup metadata, newest first.

        Raises:
            SchedulerNotInitializedError: If the scheduler is not running.
            ProfileNotFoundError: If the profile is unknown.
        """
        log.debug(f"Listing backups for profile $$'{profile}'$$")
        bdir = self._backup_dir(profile) / profile
        if not bdir.exists():
            log.debug(f"Backup directory $$'{bdir}'$$ does not exist")
            return []
        metas: list[BackupMeta] = []
        now = datetime.now(UTC)

        bridge = self._get_profile_bridge(profile)
        list_provider = bridge.list_provider
        provider_user = list_provider.user()

        count = 0
        pattern = f"anibridge_{profile}_{list_provider.NAMESPACE}_*.json"
        for f in sorted(bdir.glob(pattern)):
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
                        user=provider_user.title if provider_user else None,
                        age_seconds=(now - dt).total_seconds(),
                    )
                )
                count += 1
            except Exception:
                continue
        log.debug(f"Found {count} backups for profile $$'{profile}'$$")
        return list(reversed(metas))  # Newest first

    def read_backup_raw(self, profile: str, filename: str) -> dict[str, Any]:
        """Return the raw JSON content of a backup file.

        Args:
            profile: Profile name
            filename: Backup filename (basename only)

        Returns:
            dict[str, Any]: Parsed JSON content.

        Raises:
            SchedulerNotInitializedError: If the scheduler is not running.
            ProfileNotFoundError: If the profile is unknown.
            InvalidBackupFilenameError: If the filename is invalid.
            BackupFileNotFoundError: If the file does not exist.
        """
        log.debug(f"Reading raw backup $$'{filename}'$$ for profile $$'{profile}'$$")
        path = self._resolve_backup_path(profile, filename)

        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _resolve_backup_path(self, profile: str, filename: str) -> Path:
        """Resolve and validate a backup filename for a profile."""
        bdir = self._backup_dir(profile) / profile
        path = (bdir / filename).resolve()

        if path.parent != bdir.resolve():
            raise InvalidBackupFilenameError("Invalid backup filename")
        if not path.exists():
            raise BackupFileNotFoundError("Backup file not found")

        return path

    async def restore_backup(self, profile: str, filename: str) -> RestoreSummary:
        """Restore a backup file for a profile.

        Args:
            profile: Profile name
            filename: Backup filename (basename only)

        Raises:
            SchedulerNotInitializedError: If the scheduler is not running.
            ProfileNotFoundError: If the profile is unknown.
            InvalidBackupFilenameError: If the filename is invalid.
            BackupFileNotFoundError: If the file does not exist.
        """
        log.info(f"Restoring backup $$'{filename}'$$ for profile $$'{profile}'$$")
        bridge = self._get_profile_bridge(profile)
        path = self._resolve_backup_path(profile, filename)

        try:
            raw_payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BackupParseError("Backup file is not valid JSON") from exc

        deserialize = getattr(bridge.list_provider, "deserialize_backup_entries", None)
        if deserialize is None:
            raise BackupParseError(
                "List provider does not support backup deserialization"
            )

        try:
            parsed = deserialize(raw_payload)
        except NotImplementedError as exc:
            raise BackupParseError(
                "List provider does not support backup deserialization"
            ) from exc

        total = len(parsed.entries)
        start = perf_counter()
        errors: list[dict[str, Any]] = []

        restored = 0
        list_provider = bridge.list_provider
        entries = list(parsed.entries)
        log.debug(
            "Parsed backup entries: %s for user %s",
            len(entries),
            parsed.user or "unknown",
        )
        restore_entries = getattr(list_provider, "restore_entries", None)
        if restore_entries is None:
            errors.append(
                {
                    "index_start": 0,
                    "count": len(entries),
                    "error": "List provider does not support restoring backups",
                }
            )
        else:
            try:
                await restore_entries(entries)
                restored = len(entries)
            except Exception as e:
                errors.append(
                    {
                        "index_start": 0,
                        "count": len(entries),
                        "error": str(e),
                    }
                )
                log.error(
                    f"Error restoring backup entries: {e}",
                    exc_info=True,
                )
        elapsed = perf_counter() - start
        log.info(
            f"Restore completed for profile "
            f"$$'{profile}'$$: {restored}/{total} restored, "
            f"errors={len(errors)}, in {elapsed:.2f}s"
        )

        return RestoreSummary(
            ok=not errors,
            filename=filename,
            total_entries=total,
            processed=total,
            restored=restored,
            skipped=0,
            errors=errors,
            elapsed_seconds=elapsed,
        )


@lru_cache(maxsize=1)
def get_backup_service() -> BackupService:
    """Get the singleton BackupService instance.

    Returns:
        BackupService: The singleton BackupService instance.
    """
    return BackupService()

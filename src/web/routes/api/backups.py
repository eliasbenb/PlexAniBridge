"""Backup API endpoints."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from src.web.services.backup_service import (
    BackupMeta,
    RestoreSummary,
    get_backup_service,
)

router = APIRouter()


class ListBackupsResponse(BaseModel):
    """Response model for listing backups."""

    backups: list[BackupMeta]


class RestoreRequest(BaseModel):
    """Request body for triggering a restore."""

    filename: str


@router.get("/{profile}", response_model=ListBackupsResponse)
def list_backups(profile: str) -> ListBackupsResponse:
    """List backups for a profile.

    Args:
        profile (str): Profile name

    Returns:
        ListBackupsResponse: List of available backups
    """
    backups = get_backup_service().list_backups(profile)
    return ListBackupsResponse(backups=backups)


@router.post("/{profile}/restore", response_model=RestoreSummary)
async def restore_backup(profile: str, req: RestoreRequest) -> RestoreSummary:
    """Restore a backup file (no dry-run mode)."""
    return await get_backup_service().restore_backup(
        profile=profile,
        filename=req.filename,
    )


@router.get("/{profile}/raw/{filename}")
def get_backup_raw(profile: str, filename: str) -> dict[str, Any]:
    """Return raw JSON content of a backup.

    The response is unvalidated JSON so the UI can present a preview.
    """
    return get_backup_service().read_backup_raw(profile, filename)

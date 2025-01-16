#!/usr/bin/env python3

import argparse
import json
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from time import sleep
from typing import Any

import requests
from pydantic import BaseModel


class FuzzyDate(BaseModel):
    year: int | None = None
    month: int | None = None
    day: int | None = None


class MediaList(BaseModel):
    id: int
    userId: int
    mediaId: int
    status: str | None = None
    score: float | None = None
    progress: int | None = None
    repeat: int | None = None
    notes: str | None = None
    started_at: FuzzyDate | None = None
    completed_at: FuzzyDate | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AniListRestoreClient:
    API_URL = "https://graphql.anilist.co"
    RATE_LIMIT_REQUESTS = 90
    RATE_LIMIT_WINDOW = 60

    def __init__(self, token: str, dry_run: bool = False):
        self.token = token
        self.dry_run = dry_run
        self.request_count = 0
        self.last_request_time = 0

    def restore_from_file(self, backup_file: Path) -> None:
        print(f"Loading backup from {backup_file}")
        data = json.loads(backup_file.read_text())

        entries = [
            MediaList(**entry)
            for list_data in data["lists"]
            if not list_data["isCustomList"]
            for entry in list_data["entries"]
        ]
        for entry in entries:
            self._restore_entry(entry)

    def _restore_entry(self, entry: MediaList) -> None:
        query = dedent("""
        mutation ($mediaId: Int, $status: MediaListStatus, $score: Float, $progress: Int, $repeat: Int, $notes: String, $startedAt: FuzzyDateInput, $completedAt: FuzzyDateInput) {{
            SaveMediaListEntry(mediaId: $mediaId, status: $status, score: $score, progress: $progress, repeat: $repeat, notes: $notes, startedAt: $startedAt, completedAt: $completedAt) {{
                id
                mediaId
            }}
        }}
        """).strip()

        if self.dry_run:
            print(
                f"[DRY RUN] Would restore entry for media ID: {entry.mediaId} with data:"
            )
            print(f"\t{entry.model_dump_json(exclude_none=True)}")
            return

        variables = entry.model_dump_json(exclude_none=True)

        try:
            response = self._make_request(query, variables)
            if "errors" in response:
                print(f"Error restoring entry {entry.mediaId}: {response['errors']}")
            else:
                print(f"Restored entry for media ID: {entry.mediaId}")
        except Exception as e:
            print(f"Failed to restore entry {entry.mediaId}: {str(e)}")

    def _make_request(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = requests.post(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={"query": query, "variables": variables or {}},
        )

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            print(f"Rate limit exceeded, waiting {retry_after} seconds")
            sleep(retry_after + 1)
            return self._make_request(query, variables)

        response.raise_for_status()
        return response.json()


def main():
    parser = argparse.ArgumentParser(description="Restore AniList data from backup")
    parser.add_argument("backup_file", type=Path, help="Path to the backup JSON file")
    parser.add_argument("--token", required=True, help="AniList API token")
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't actually make any changes"
    )

    args = parser.parse_args()

    if not args.backup_file.exists():
        print(f"Error: Backup file {args.backup_file} does not exist")
        return 1

    client = AniListRestoreClient(args.token, args.dry_run)
    client.restore_from_file(args.backup_file)
    return 0


if __name__ == "__main__":
    main()

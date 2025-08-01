#!/usr/bin/env python3

"""AniList Restore Script.

This script restores AniList media list entries from a backup JSON file. You can use it
to recover your AniList data exactly as it was at the time of the backup. To test the
restore process without making any changes, use the `--dry-run` option.

Usage:
    python anilist_restore.py <backup_file> --token <anilist_token> [--dry-run]
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Any

import requests
import urllib3.exceptions
from pydantic import BaseModel


class FuzzyDate(BaseModel):
    """Model representing a fuzzy date in AniList."""

    year: int | None = None
    month: int | None = None
    day: int | None = None


class MediaList(BaseModel):
    """Model representing a media list entry in AniList."""

    id: int
    userId: int
    mediaId: int
    status: str | None = None
    score: float = 0
    progress: int | None = None
    repeat: int | None = None
    notes: str | None = None
    startedAt: FuzzyDate | None = None
    completedAt: FuzzyDate | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class AniListRestoreClient:
    """Client for restoring AniList data from a backup JSON file."""

    API_URL = "https://graphql.anilist.co"
    RATE_LIMIT_REQUESTS = 90
    RATE_LIMIT_WINDOW = 60

    def __init__(self, token: str, dry_run: bool = False) -> None:
        """Initializes the AniList restore client.

        Args:
            token (str): AniList API token for authentication.
            dry_run (bool): If True, does not actually make any changes, just simulates
                           the restore process.
        """
        self.token = token
        self.dry_run = dry_run
        self.request_count = 0
        self.last_request_time = 0

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "PlexAniBridge",
                "Authorization": f"Bearer {self.token}",
            }
        )

    def restore_from_file(self, backup_file: Path) -> None:
        """Restores AniList data from a backup JSON file.

        Args:
            backup_file (Path): Path to the backup JSON file containing lists and
                                entries.

        Raises:
            FileNotFoundError: If the backup file does not exist.
            json.JSONDecodeError: If the backup file is not a valid JSON.
        """
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
        query = """
        mutation (
            $mediaId: Int, $status: MediaListStatus, $score: Float, $progress: Int,
            $repeat: Int, $notes: String, $startedAt: FuzzyDateInput,
            $completedAt: FuzzyDateInput
        ) {
            SaveMediaListEntry(
                mediaId: $mediaId, status: $status, score: $score, progress: $progress,
                repeat: $repeat, notes: $notes, startedAt: $startedAt,
                completedAt: $completedAt
            ) {
                id
                media {
                    title {
                        userPreferred
                    }
                }
            }
        }
        """

        variables = entry.model_dump_json()

        if self.dry_run:
            print(
                f"[DRY RUN] Would restore entry for media ID: {entry.mediaId} with "
                "data:"
            )
            print(f"\t{variables}")
            return

        res = self._make_request(query, variables)
        print(
            f"Succesfully restored entry for "
            f"'{res['data']['SaveMediaListEntry']['media']['title']['userPreferred']}' "
            f"(ID: {res['data']['SaveMediaListEntry']['id']})"
        )

    def _make_request(
        self,
        query: str,
        variables: dict[str, Any] | str | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        if retry_count >= 3:
            raise requests.exceptions.HTTPError("Failed to make request after 3 tries")

        try:
            response = self.session.post(
                self.API_URL,
                json={"query": query, "variables": variables or {}},
            )
        except (
            requests.exceptions.RequestException,
            urllib3.exceptions.ProtocolError,
        ):
            print("Connection error while making request to AniList API")
            sleep(1)
            return self._make_request(
                query=query, variables=variables, retry_count=retry_count + 1
            )

        if response.status_code == 429:  # Handle rate limit retries
            retry_after = int(response.headers.get("Retry-After", 60))
            print(f"Rate limit exceeded, waiting {retry_after} seconds")
            sleep(retry_after + 1)
            return self._make_request(
                query=query, variables=variables, retry_count=retry_count
            )
        elif response.status_code == 502:  # Bad Gateway
            print("Received 502 Bad Gateway, retrying")
            sleep(1)
            return self._make_request(
                query=query, variables=variables, retry_count=retry_count + 1
            )

        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            print("Failed to make request to AniList API")
            print(f"\t\t{response.text}")
            raise e

        return response.json()


def main():
    """Main function to restore AniList data from a backup file."""
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

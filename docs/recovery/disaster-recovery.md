---
title: Disaster Recovery
icon: material/weather-cloudy-alert
---

Given that software will always be susceptible to bugs, AniBridge offers multiple recovery features: daily automatic AniList backups, in-app restore, and a per‑sync undo capability on the timeline.

!!! tip "Prevention"

    Before running AniBridge for the first time, it is recommended to try a [dry run](../configuration.md#dry_run) to see what changes will be made without actually making them. This can help you identify any potential issues before they occur.

## Backups

AniBridge creates a JSON snapshot of the current AniList list data on startup and on a daily schedule. These backups are stored under the data folder (defined in `AB_DATA_PATH`) in the `backups` directory as JSON files named like:

```
anibridge-<PROFILE_NAME>.<YYYYMMDDHHMMSS>.json
```

You can view or restore these back ups through the web UI's [backups page](../web/backups.md).

!!! warning

    Backups are kept for 30 days by default. Adjust [BACKUP_RETENTION_DAYS](../configuration.md#backup_retention_days) if you need a longer retention window.

### Restoring from Backups

1. Open the Web UI and navigate to: Backups → select a profile.
2. You will see a table of recent backups (filename, created time, size, age, detected user if available).
3. Click Preview to open a highlighted JSON view (no data is changed).
4. Click Restore to apply that snapshot back to AniList for the profile.
5. A toast will indicate success; any individual sync outcomes will appear later on the timeline.

!!! warning

    Initiating a restore will **overwrite all current AniList entries** for that profile.

## Undoing Individual Sync Changes

In addition to full restores, you can undo specific sync operations directly from the Timeline page.

Each timeline entry representing a change (e.g. a creation, update, or deletion) exposes an Undo button when it is logically reversible. When clicked, AniBridge applies an inverse operation to restore the previous state and creates a new timeline entry marked as `undone`.

### Undo Is Available When

| Original Outcome | Before State | After State | Meaning       | Undo Action      |
| ---------------- | ------------ | ----------- | ------------- | ---------------- |
| synced           | present      | present     | Updated entry | Revert to before |
| synced           | null         | present     | Created entry | Delete it        |
| deleted          | present      | null        | Deleted entry | Restore it       |

_Note: Undos that are supposed to cause an entry deletion will not take effect if [DESTRUCTIVE_SYNC](../configuration.md#destructive_sync) is disabled._

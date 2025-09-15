---
title: Disaster Recovery
icon: material/weather-cloudy-alert
---

Given that software will always be susceptible to bugs, PlexAniBridge offers multiple recovery features: daily automatic AniList backups, in-app restore, and a per‑sync undo capability on the timeline.

!!! tip "Prevention"

    Before running PlexAniBridge for the first time, it is recommended to try a [dry run](../configuration.md#dry_run) to see what changes will be made without actually making them. This can help you identify any potential issues before they occur.

## Backups

PlexAniBridge creates a JSON snapshot of the current AniList list data on startup and on a daily schedule. These backups are stored under the data folder (defined in `PAB_DATA_PATH`) in the `backups` directory as JSON files named like:

```
plexanibridge-<ANILIST_USERNAME>.<YYYYMMDDHHMMSS>.json
```

You can work with these backups in two ways:

1. Web UI (recommended for most cases) - browse, preview, and restore directly.
2. CLI [restore script](https://github.com/eliasbenb/PlexAniBridge/blob/HEAD/scripts/anilist_restore.py) (legacy, deprecated).

!!! warning
    Backups are automatically deleted after 7 days (rolling retention). If you need to keep a snapshot longer, save it in a safe location.

### Viewing & Restoring Backups in the Web UI

1. Open the Web UI and navigate to: Backups → select a profile.
2. You will see a table of recent backups (filename, created time, size, age, detected user if available).
3. Click Preview to open a highlighted JSON view (no data is changed).
4. Click Restore to apply that snapshot back to AniList for the profile.
5. A toast will indicate success; any individual sync outcomes will appear later on the timeline.

#### What a Web UI Restore Does

- Replays the backed-up list entries to AniList, overwriting current state for that profile's lists.
- Only the selected backup file is used—other backups remain untouched.
- Errors encountered during restore are summarized (restored / skipped / errors).

!!! danger "Irreversible Overwrite"
    A restore replaces current AniList list entries with the backup content. If you want a safety net, trigger a manual sync first so a fresh pre‑restore backup is generated, or download the current latest backup file.

## Restoring from Backups (CLI Script)

_This method is no longer recommended for typical users; prefer the Web UI above._

To restore from a backup without the Web UI, use the [restore script](https://github.com/eliasbenb/PlexAniBridge/blob/HEAD/scripts/anilist_restore.py) in the `scripts` folder. You will need to pass the backup file and AniList token as arguments:

## Undoing Individual Sync Changes

In addition to full restores, you can undo specific sync operations directly from the Timeline page.

### How It Works

Each timeline entry representing a change (e.g. a creation, update, or deletion) exposes an Undo button when it is logically reversible. When clicked, PlexAniBridge applies an inverse operation to restore the previous state and creates a new timeline entry marked as `undone`.

### Undo Is Available When

| Original Outcome | Before State | After State | Meaning       | Undo Action      |
| ---------------- | ------------ | ----------- | ------------- | ---------------- |
| synced           | present      | present     | Updated entry | Revert to before |
| synced           | null         | present     | Created entry | Delete it        |
| deleted          | present      | null        | Deleted entry | Restore it       |

_Note: Undos that are supposed to cause an entry deletion will not take effect if [DESTRUCTIVE_SYNC](../configuration.md#destructive_sync) is disabled._

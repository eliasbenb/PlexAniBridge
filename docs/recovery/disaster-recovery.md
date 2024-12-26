---
title: Disaster Recovery
icon: material/weather-cloudy-alert
---

Given that software will always be susceptible to bugs, PlexAniBridge offers a backup and restore feature to help you recover from any data loss.

!!! tip "Prevention"

    Before running PlexAniBridge for the first time, it is recommended to try a [dry run](../configuration.md#dry_run) to see what changes will be made without actually making them. This can help you identify any potential issues before they occur.

## Backups

Before any scheduled sync job, PlexAniBridge will create a backup of your current AniList data. These backups are stored under the data folder (defined in `DATA_PATH`) in the `backups` directory as JSON files.

!!! warning

    These backups are automatically deleted after 7 days.

To restore from a backup, use the [restore script](https://github.com/eliasbenb/PlexAniBridge/blob/main/scripts/anilist_restore.py) in the `scripts` folder. You will need to pass the backup file and AniList token as arguments:

```shell
pip install requests pydantic # Python 3.10+
python scripts/anilist_restore.py --token <YOUR_ANILIST_TOKEN> ./data/backups/plexanibridge-user.1.json
```

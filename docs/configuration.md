---
title: Configuration
icon: material/cog
---

## Example

Below is a PlexAniBridge .env file with example values. Optional environment variables are commented out.

```env title=".env"
--8<-- ".env.example"
```

## Configuration Options

### `ANILIST_TOKEN`

`str | list[str]` (required)

AniList API access token. You can [get one here](https://anilist.co/login?apiVersion=v2&client_id=23079&response_type=token).

??? info "Multiple Users"

    For multiple users:

    - Provide a list of tokens: `["token1", "token2", "token3"]`
    - Each token must have a corresponding Plex user in `PLEX_USER`

### `PLEX_TOKEN`

`str` (required)

Plex API access token. [Learn how to find your token here](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).

!!! note

    The token must belong to the admin user of the Plex server.

### `PLEX_USER`

`str | list[str]` (required)

Which Plex user(s) to sync. Can be identified by:

- Plex account username: `username`
- Plex account email: `user@email.com`
- Plex Home user name: `Home User`

??? info "Multiple Users"

    For multiple users:

    - Provide a list of users: `["user1", "user2@email.com", "Home User"]`
    - Each user must have a corresponding AniList token in `ANILIST_TOKEN`

??? note "Multi-User Limitations"

    Due to limitations in the Plex API, only the admin user can sync reviews and watch lists. Besides these two fields, all other features are available for all users.

### `PLEX_URL`

`str` (required)

URL to your Plex server that the PlexAniBridge host can access.

??? tip "Docker Networking"

    If both Plex and PlexAniBridge are running as Docker containers in the same Docker network, you can use the service name as the URL: `http://plex:32400`

### `PLEX_SECTIONS`

`list[str]` (required)

List of Plex library sections to consider, specified in Python list syntax:

```python
["Anime", "Anime Movies"]
```

??? note "Multi-User Considerations"

    In multi-user setups, every section will be synced for every user. However, if the user doesn't have access to a section, it will be skipped.

### `SYNC_INTERVAL`

`int` (optional, default `3600`)

Interval in seconds between sync jobs. Set to `-1` to run once and exit.

??? note "Sync Interval with Polling Scan"

    If `POLLING_SCAN` is enabled, the sync interval still applies. The polling scanner will run in addition to the regular sync.

    The difference being that the polling scanner will only sync the changes detected in the library, while the regular sync will pull the mappings database and sync the entire library.

### `POLLING_SCAN`

`bool` (optional, default `False`)

When enabled, PlexAniBridge will poll the Plex server for changes instead of waiting for the sync interval.

The polling scanner is event-driven and will detect changes in your library and sync that subset of your library. This is useful if you want real-time updates on your AniList profile.

!!! note

    Even with polling scan enabled, the sync interval will still be respected. So, every `SYNC_INTERVAL` seconds, a regular sync will be performed.

### `FULL_SCAN`

`bool` (optional, default `False`)

Scan all Plex media regardless of it has any activity. The default behavior (when disabled) is a partial scan which only scans items that have been watched.

!!! note

    Full scan is largely useless unless used in tandem with `DESTRUCTIVE_SYNC`. It is not recommended to enable this without understanding the implications.

!!! warning

    Enabling full scan will lead to excessive API usage and increased processing times.

### `DESTRUCTIVE_SYNC`

`bool` (optional, default `False`)

!!! warning

    Enable only if you understand the implications.

    This mode allows for regressive updates and deletions and can cause data loss.

    Destructive sync allows for:

    - Deleting AniList entriyes
    - Making 'regressive' updates to AniList. Meaning, even if AniList reports a 'higher' value than Plex, the Plex value will be used and updated in AniList. For example, if AniList has a higher watch progress than Plex, the AniList value will be lowered to match Plex.

!!! note

    If you want to delete entries from AniList that you haven't watched in Plex, you must enable `FULL_SCAN` in addition to `DESTRUCTIVE_SYNC`. Otherwise, the unwanted entries will not be detected.

### `EXCLUDED_SYNC_FIELDS`

`list[str]` (optional, default `["notes", "score"]`)

Specifies fields to exclude from synchronization. Available fields:

- `status` (planning, current, completed, dropped, paused)
- `score` (rating on a 0-10 scale)
- `progress` (number of watched episodes)
- `repeat` (number of times rewatched)
- `notes` (text reviews)
- `started_at` (start date)
- `completed_at` (completed date)

!!! tip "Allowing All Fields"

    To sync all fields, set this to an empty list: `[]`

### `DATA_PATH`

`str` (optional, default `./data`)

Path to store the database, backups, and custom mappings.

??? note "Docker"

    If running in Docker, it is not recommended to change this path.

    If you do, ensure the path is mapped correctly to your Docker volume/mount.

### `LOG_LEVEL`

`str` (optional, default `INFO`)

Sets logging verbosity. Available levels:

- `DEBUG`
- `INFO`
- `WARNING`
- `ERROR`
- `CRITICAL`

!!! tip "Debugging"

    To get the most detailed logs, set this to `DEBUG`.

### `DRY_RUN`

`bool` (optional, default `False`)

When enabled:

- Doesn't modify AniList data
- Only logs the outcomes that would have occurred

!!! tip "First Run"

    It is a good idea to run with `DRY_RUN` enabled before running the script for the first time.

    This allows you to see what changes will be made without actually making them.

### `FUZZY_SEARCH_THRESHOLD`

`int` (optional, default `90`)

When exact matches fail, PlexAniBridge will search AniList for similar titles. These searches may not always be perfect, so this threshold is used to determine how similar two titles must be to be considered a match.

The threshold is a percentage of similarity between two titles. Lower values result in more matches but also more false positives. Higher values result in fewer matches but also fewer false positives.

??? tip "Disabling Fuzzy Search"

    To disable fuzzy search, set this to `100` to only allow exact matches.

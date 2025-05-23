---
title: Configuration
icon: material/cog
---

## Example

Below is an example `.env` file for PlexAniBridge with example values. Optional environment variables are commented out.

```dosini title=".env"
--8<-- ".env.example"
```

## Configuration Options

### `ANILIST_TOKEN`

`str | list[str]` (Required)

AniList API access token.

[:simple-anilist: Generate AniList Token](https://anilist.co/login?apiVersion=v2&client_id=23079&response_type=token){: .md-button .md-button--primary}

??? info "Multiple Users"

    - Provide a list of tokens: `["token1", "token2", "token3"]`
    - Each token must have a corresponding Plex user in `PLEX_USER`.

---

### `PLEX_TOKEN`

`str` (Required)

Plex API access token.

[:material-plex: Finding the Plex Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/){: .md-button .md-button--primary}

!!! note

    The token must belong to the **admin** user of the Plex server.

---

### `PLEX_USER`

`str | list[str]` (Required)

Plex user(s) to sync. Can be identified by:

- Plex account username: `"username"`
- Plex account email: `"user@email.com"`
- Plex Home user name: `"Home User"`

??? info "Multiple Users"

    - Provide a list of users: `["user1", "user2@email.com", "Home User"]`
    - Each user must have a corresponding AniList token in `ANILIST_TOKEN`.

??? note "Multi-User Limitations"

    Due to limitations in the Plex API, only the **admin user** can sync reviews and watch lists. All other features are available for all users.

---

### `PLEX_URL`

`str` (Required)

URL to your Plex server that the PlexAniBridge host can access.

??? tip "Docker Networking"

    If both Plex and PlexAniBridge are running as Docker containers in the same network, you can use the service name as the URL: `http://plex:32400`

---

### `PLEX_SECTIONS`

`list[str]` (Optional, default: `[]`)

List of Plex library sections to consider, specified in Python list syntax:

```python
["Anime", "Anime Movies"]
```

!!! tip "Allowing All Sections"

    To sync all sections, set this to an empty list: `[]` or don't set it at all. This is the default behavior.

??? note "Multi-User Considerations"

    Every section will be synced for every user. If a user doesn't have access to a section, it will be skipped.

---

### `PLEX_GENRES`

`list[str]` (Optional, default: `[]`)

An optional list of Plex genres to filter by. If specified, only items with these genres will be synced.

```python
["Anime", "Animation"]
```

This is useful for syncing only Anime content in a mixed library.

!!! tip "Allowing All Genres"

    To sync all genres, set this to an empty list: `[]` or don't set it at all.

??? tip "Finding Possible Genres"

    Genres are sources from the metdata you use (typically TheMovieDB or TheTVDB). You can find the possible genres below:

    - [TheTVDB Genres](https://thetvdb.com/genres)
    - [TheMovieDB Genres](https://www.themoviedb.org/talk/644a4b69f794ad04fe3cf1b9)

---

### `PLEX_METADATA_SOURCE`

`Enum("local", "online")` (Optional, default: `"local"`)

Determines the source of metadata for Plex content:

- `local`: Use metadata stored locally on the Plex server.
- `online`: Fetch metadata from Plex's servers using the [Plex Metadata](https://metadata.provider.plex.tv).

!!! warning "Online Metadata Advantages and Limitations"

    The main advantage of using the online metadata is that it provides the most complete library possible. A complete set of seasons and episodes will exist, even if they are not in your library. This is useful if you regularly delete content and keep incomplete shows.

    Additionally, the online source logs your activity across all Plex servers, so you can sync content from multiple servers or even previously deleted servers.

    However, the online metadata has some limitations:

    - Being online, it's subject to outages and rate limits, causing sync times to drastically increase.
    - You are required to enable [Plex Sync](https://support.plex.tv/articles/sync-watch-state-and-ratings/) for the online Plex API to work.
    - It may not be as up-to-date with your activity as the local server in the event Plex Sync fails.
    - Due to API limitations, only the admin user can use the online Plex API. All other users will be forced to use the local metadata source.

---

### `SYNC_INTERVAL`

`int` (Optional, default: `3600`)

Interval in seconds between sync jobs. Set to `-1` to run once and exit.

??? note "Sync Interval with Polling Scan"

    If `POLLING_SCAN` is enabled, the sync interval determines how often the [mappings database](./advanced/custom-mappings.md) and your AniList profile are updated. Periodic scans will be disabled.

---

### `POLLING_SCAN`

`bool` (Optional, default: `False`)

When enabled, PlexAniBridge will detect changes in your Plex library in real-time instead of waiting for the sync interval.

??? note "Sync Interval with Polling Scan"

    If enabled, the sync interval determines how often the [mappings database](./advanced/custom-mappings.md) and your AniList profile are updated.

---

### `FULL_SCAN`

`bool` (Optional, default: `False`)

Scans all Plex media, regardless of activity. By default, only watched items are scanned.

!!! note

    Full scans are generally **not recommended** unless used with `DESTRUCTIVE_SYNC`.

!!! warning

    Enabling `FULL_SCAN` can lead to **excessive API usage** and **longer processing times**.

---

### `DESTRUCTIVE_SYNC`

`bool` (Optional, default: `False`)

Allows regressive updates and deletions, which **can cause data loss**.

!!! warning

    **Enable only if you understand the implications.**

    Destructive sync allows:

    - Deleting AniList entries.
    - Making regressive updates (e.g., if AniList progress is higher than Plex, AniList will be **lowered** to match Plex).

!!! note

    To delete AniList entries for unwatched Plex content, enable both `FULL_SCAN` and `DESTRUCTIVE_SYNC`.

---

### `EXCLUDED_SYNC_FIELDS`

`list[Enum("status", "score", "progress", "repeat", "notes", "started_at", "completed_at")]` (Optional, default: `["notes", "score]`)

Specifies which fields should **not** be synced. Available fields:

- `status` (planning, current, completed, dropped, paused)
- `score` (rating on a 0-10 scale)
- `progress` (episodes watched)
- `repeat` (rewatch count)
- `notes` (text reviews)
- `started_at` (start date)
- `completed_at` (completion date)

!!! tip "Allowing All Fields"

    To sync all fields, set this to an empty list: `[]` or don't set it at all.

---

### `LOG_LEVEL`

`str` (Optional, default: `INFO`)

Sets logging verbosity. Available levels:

- `DEBUG`
- `INFO`
- `SUCCESS`
- `WARNING`
- `ERROR`
- `CRITICAL`

!!! tip "Minimal Logging"

    For minimal logging, set the verbosity to `SUCCESS` which only logs successful operations like syncing entries.

!!! tip "Debugging"

    For the most detailed logs, set this to `DEBUG`.

---

### `DRY_RUN`

`bool` (Optional, default: `False`)

When enabled:

- AniList data **is not modified**.
- Logs show what changes **would** have been made.

!!! tip "First Run"

    Run with `DRY_RUN` enabled on first launch to preview changes without modifying your AniList data.

---

### `BATCH_REQUESTS`

`bool` (Optional, default: `False`)

When enabled, AniList update and get requests are sent in batches instead of individually. At the start of each sync job, a batch of requests is created and sent to AniList to retrieve all the entries that will be worked on. Then, near the end of the sync job, all entries that need updating are batched to reduce the number of requests.

This can be used to significantly reduce rate limiting at the cost of worse error handling.

For example, if a sync job finds 10 items to update with `BATCH_REQUESTS` enabled, all 10 requests will be sent at once. If any of the requests fail, all 10 requests will fail.

!!! tip "First Run"

    The main use case for this option is when going through the first sync of a large library. It can significantly reduce the rate limiting of the AniList API.

    For subsequent syncs, it is recommended to disable this option unless you encounter rate limiting issues constantly.

---

### `SEARCH_FALLBACK_THRESHOLD`

`int` (Optional, default: `-1`)

Determines how similar (as a percentage) a title must be to the search query to be considered a match.

The default behavior is to disable searching completely and only relying on the [community and local mappings database](./advanced/custom-mappings.md).

??? tip "Enabling Search Fallback"

    Set this to a value between `0` and `100` to enable **search fallback**. The higher the value, the more strict the title matching.

    A value of `100` requires an exact match, while `0` will match the first result returned by AniList, regardless of similarity.

---

### `DATA_PATH`

`str` (Optional, default: `./data`)

Path to store the database, backups, and custom mappings.

??? note "Docker"

    If running in Docker, **do not change this path** unless properly mapped in your Docker volume/mount.

---

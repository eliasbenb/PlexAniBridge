---
title: Configuration
icon: material/cog
---

## Example

Below is an example `.env` file for PlexAniBridge:

```dosini title=".env"
--8<-- ".env.example"
```

??? tip "YAML Configuration"

    If you prefer YAML configuration, you can create a `config.yaml` file in the data directory. The settings will be automatically loaded from there. Example:

    ```yaml title="config.yaml"
    --8<-- "data/config.example.yaml"
    ```

    The order of precedence when loading settings is:

    1. Environment variables
    2. `.env` file in the current working directory
    3. `config.yaml` file in the data directory

## Configuration Hierarchy

Settings are applied in the following order:

1. **Profile-specific settings** (highest priority)
2. **Global default settings** (medium priority)
3. **Built-in defaults** (lowest priority)

For example, if `PAB_SYNC_INTERVAL=900` is set globally and `PAB_PROFILES__personal__SYNC_INTERVAL=1800` is set for a specific profile, the profile named 'personal' will use 1800 seconds as the sync interval while other profiles will use 900 seconds. If `PAB_PROFILES__personal__SYNC_INTERVAL` is unset it falls back to the application's built-in default of 86400 seconds (24 hours).

## Configuration Options

### `ANILIST_TOKEN`

`str` (Required)

AniList API access token for this profile.

[:simple-anilist: Generate AniList Token](https://anilist.co/login?apiVersion=v2&client_id=23079&response_type=token){: .md-button style="background-color: #02a9ff; color: white;"}

---

### `PLEX_TOKEN`

`str` (Required)

Plex API access token (`X-Plex-Token`) belonging to the **admin user** of the server.

[:material-plex: Finding the Plex Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/){: .md-button style="background-color: #e5a00d; color: white;"}

---

### `PLEX_USER`

`str` (Required)

Plex user to sync for this profile. Can be identified by:

- Plex account username: `"username"`
- Plex account email: `"user@email.com"`
- Plex Home user name: `"Home User"`

??? note "Admin User Limitations"

    Due to limitations in the Plex API, only the **admin user** can sync reviews and watch lists. All other features are available for all users.

---

### `PLEX_URL`

`str` (Required)

URL to your Plex server that the PlexAniBridge host can access.

---

### `PLEX_SECTIONS`

`list[str]` (Optional, default: `[]`)

An optional list of Plex library sections to filter by. If specified, only items in these sections will be scanned.

```python
["Anime", "Anime Movies"]
```

---

### `PLEX_GENRES`

`list[str]` (Optional, default: `[]`)

An optional list of Plex genres to filter by. If specified, only items with these genres will be scanned.

```python
["Anime", "Animation"]
```

This is useful for scanning for only Anime content in a mixed library.

!!! question "How to Find Plex Genres"

    Genres are sourced from the media item's source metadata agent (typically TheMovieDB or TheTVDB). You can find some of the common genres here:

    - [TheTVDB Genres](https://thetvdb.com/genres)
    - [TheMovieDB Genres](https://www.themoviedb.org/talk/644a4b69f794ad04fe3cf1b9)

---
### `PLEX_METADATA_SOURCE`

`Enum("local", "online")` (Optional, default: `"local"`)

Determines the source of Plex metadata to use when syncing:

- `local`: Use metadata stored locally on the Plex server.
- `online`: Fetch metadata from Plex's servers using the [Plex Metadata](https://metadata.provider.plex.tv) provider.

!!! warning "Online Metadata Advantages and Limitations"

    Online metadata can provide a more complete library (including seasons/episodes not present locally) and records activity across Plex servers, allowing syncs for content from multiple or previously deleted servers.

    Limitations:

    - Susceptible to outages and rate limits, which can greatly slow syncs.
    - Requires [Plex Sync](https://support.plex.tv/articles/sync-watch-state-and-ratings/) to be enabled for the online API to function.
    - May be less up-to-date than the local server if Plex Sync fails.
    - The online API is available only to the Plex admin user..

---

### `SYNC_INTERVAL`

`int` (Optional, default: `86400`)

Interval in seconds to sync when using the `periodic` [sync mode](#sync_modes)

---

### `SYNC_MODES`

`list[Enum("periodic", "poll", "webhook")]` (Optional, default: `["periodic", "poll", "webhook"]`)

Determines the triggers for scanning:

- `periodic`: Scan all items at the specified [sync interval](#sync_interval).
- `poll`: Poll for changes every 30 seconds, making incremental updates.
- `webhook`: Trigger syncs via Plex [webhook payloads](https://support.plex.tv/articles/115002267687-webhooks/).

Setting `SYNC_MODES` to `None` or an empty list will cause the application to perform a single scan on startup and then exit.

By default, all three modes are enabled, allowing for instant, incremental updates via polling and webhooks, as well as a full periodic scan every [`SYNC_INTERVAL`](#sync_interval) seconds (default: 24 hours) to catch any failed/missed updates.

!!! info "Plex Webhooks"

    To use Plex Webhooks, you must:

    1. Have [`PAB_WEB_ENABLED`](#pab_web_enabled) set to `True` (the default).
    2. Include `webhook` in the enabled [`SYNC_MODES`](#sync_modes).
    3. [Configure the Plex server](https://support.plex.tv/articles/115002267687-webhooks/) to send webhook payloads to `http://<your-server-host>:<port>/webhook/plex`.
    4. Ensure PlexAniBridge is accessible to Plex over the network.

    Example webhook URL: `http://127.0.0.1:4848/webhook/plex`

    Once webhooks are set up, it is recommended to disable `poll` mode since it is redundant.

### `FULL_SCAN`

`bool` (Optional, default: `False`)

When enabled, the scan process will include all items, regardless of watch activity. By default, only watched items are scanned.

!!! warning "Recommended Usage"

    Full scans are generally **not recommended** unless combined with [`DESTRUCTIVE_SYNC`](#destructive_sync) to delete AniList entries for unwatched Plex content.

    Enabling `FULL_SCAN` can lead to **excessive API usage** and **longer processing times**.

---

### `DESTRUCTIVE_SYNC`

`bool` (Optional, default: `False`)

Allows regressive updates and deletions, which **can cause data loss**.

!!! danger "Data Loss Warning"

    **Enable only if you understand the implications.**

    Destructive sync allows:

    - Deleting AniList entries.
    - Making regressive updates - e.g., if AniList progress is higher than Plex, AniList will be **lowered** to match Plex.

    To delete AniList entries for unwatched Plex content, enable both `FULL_SCAN` and `DESTRUCTIVE_SYNC`.

---

### `EXCLUDED_SYNC_FIELDS`

`list[Enum("status", "score", "progress", "repeat", "notes", "started_at", "completed_at")]` (Optional, default: `["notes", "score"]`)

Specifies which fields should **not** be synced. Available fields:

- `status` (planning, current, completed, dropped, paused)
- `score` (rating on a normalized scale)
- `progress` (episodes watched)
- `repeat` (rewatch count)
- `notes` (text reviews)
- `started_at` (start date)
- `completed_at` (completion date)

!!! tip "Allowing All Fields"

    To sync all fields, set this to an empty list: `[]`.

---

### `DRY_RUN`

`bool` (Optional, default: `False`)

When enabled:

- AniList data **is not modified**.
- Logs show what changes **would** have been made.

!!! success "First Run"

    Run with `DRY_RUN` enabled on first launch to preview changes without modifying your AniList data.

---

### `BACKUP_RETENTION_DAYS`

`int` (Optional, default: `30`)

Controls how many days PlexAniBridge keeps AniList backup snapshots before pruning older files. Set to `0` to disable automatic cleanup and retain all backups indefinitely.

---

### `BATCH_REQUESTS`

`bool` (Optional, default: `False`)

When enabled, AniList API requests are made in batches:

1. Prior to syncing, a batch of requests is created to retrieve all the entries that will be worked on.
2. Post-sync, a batch of requests is created to update all the entries that were changed.

This can significantly reduce rate limiting, but at the cost of atomicity. If any request in the batch fails, the entire batch will fail.

For example, if a sync job finds 10 items to update with `BATCH_REQUESTS` enabled, all 10 requests will be sent at once. If any of the requests fail, all 10 updates will fail.

!!! success "First Run"

    The primary use case of batch requests is going through the first sync of a large library. It can significantly reduce rate limiting from AniList.

    For subsequent syncs, your data is pre-cached, and the benefit of batching is reduced.

---

### `SEARCH_FALLBACK_THRESHOLD`

`int` (Optional, default: `-1`)

Determines how similar a title must be to the search query as a percentage to be considered a match.

The default behavior is to disable searching completely and only rely on the [community and local mappings database](./mappings/custom-mappings.md).

The higher the value, the more strict the title matching. A value of `100` requires an exact match, while `0` will match the first result returned by AniList, regardless of similarity.

## Global Configuration Options

These global settings cannot be overridden on the profile level and apply to all profiles.

### `PAB_DATA_PATH`

`str` (Optional, default: `./data`)

Path to store the database, backups, and custom mappings. This is shared across all profiles.

---

### `PAB_LOG_LEVEL`

`Enum("DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL")` (Optional, default: `INFO`)

Sets logging verbosity for the entire application.

!!! tip "Minimal Logging"

    For minimal logging, set the verbosity to `SUCCESS` which only logs successful operations like syncing entries.

!!! tip "Debugging"

    For the most detailed logs, set this to `DEBUG`.

---

### `PAB_MAPPINGS_URL`

`str` (Optional, default: `https://raw.githubusercontent.com/eliasbenb/PlexAniBridge-Mappings/v2/mappings.json`)

URL to the upstream mappings source. This can be a JSON or YAML file.

This option is only intended for advanced users who want to use their own upstream mappings source or disable upstream mappings entirely. For most users, it is recommended to keep the default value.

!!! info "Custom Mappings"

    This setting works in tandem with custom mappings stored in the `mappings/` directory inside the data path. Custom mappings will overload any upstream mappings.

??? question "Disabling Upstream Mappings"

    To disable upstream mappings, set this to an empty string: `""`.

---

### `PAB_WEB_ENABLED`

`bool` (Optional, default: `True`)

When enabled, the [web interface](./web/screenshots.md) is accessible.

---

### `PAB_WEB_HOST`

`str` (Optional, default: `0.0.0.0`)

The host address for the web interface.

---

### `PAB_WEB_PORT`

`int` (Optional, default: `4848`)

The port for the web interface.

---

### `PAB_WEB_BASIC_AUTH_USERNAME`

`str` (Optional, default: `None`)

HTTP Basic Authentication username for the web UI. Basic Auth is enabled only when both the username and password are provided. Leave unset to disable authentication.

---

### `PAB_WEB_BASIC_AUTH_PASSWORD`

`str` (Optional, default: `None`)

HTTP Basic Authentication password for the web UI. Basic Auth is enabled only when both the username and password are provided. Leave unset to disable authentication.

---

### `PAB_WEB_BASIC_AUTH_REALM`

`str` (Optional, default: `PlexAniBridge`)

Realm label presented in the browser Basic Auth prompt and `WWW-Authenticate` response header.

## Advanced Examples

### Multiple Users

This example demonstrates configuring three distinct profiles, each with their own AniList accounts, Plex users, and customized sync preferences.

```dosini
# Global defaults shared by all profiles
PAB_PLEX_TOKEN=admin_plex_token
PAB_PLEX_URL=http://localhost:32400
PAB_SYNC_MODES=["periodic"]

# Admin user - aggressive sync with full features
PAB_PROFILES__admin__ANILIST_TOKEN=admin_anilist_token
PAB_PROFILES__admin__PLEX_USER=admin_plex_user
PAB_PROFILES__admin__DESTRUCTIVE_SYNC=True
PAB_PROFILES__admin__EXCLUDED_SYNC_FIELDS=[]

# Family member - typical sync
PAB_PROFILES__family__ANILIST_TOKEN=family_anilist_token
PAB_PROFILES__family__PLEX_USER=family_plex_user

# Guest user - minimal sync
PAB_PROFILES__guest__ANILIST_TOKEN=guest_anilist_token
PAB_PROFILES__guest__PLEX_USER=guest_plex_user
PAB_PROFILES__guest__EXCLUDED_SYNC_FIELDS=["notes", "score", "repeat", "started_at", "completed_at"]
```

### Per-Library Profiles

This example shows how to create separate profiles for different Plex libraries, allowing for tailored sync settings based on content type.

```dosini
# Global defaults shared by all profiles
PAB_ANILIST_TOKEN=global_anilist_token
PAB_PLEX_TOKEN=admin_plex_token
PAB_PLEX_USER=admin_plex_user
PAB_PLEX_URL=http://localhost:32400

# Movies library - aggressive sync with full features
PAB_PROFILES__movies__PLEX_SECTIONS=["Anime Movies"]
PAB_PROFILES__movies__FULL_SCAN=True
PAB_PROFILES__movies__SYNC_INTERVAL=1800
PAB_PROFILES__movies__EXCLUDED_SYNC_FIELDS=[]

# TV Shows library - more conservative with updates
PAB_PROFILES__tvshows__PLEX_SECTIONS=["Anime"]
PAB_PROFILES__tvshows__SYNC_MODES=["periodic"]
```

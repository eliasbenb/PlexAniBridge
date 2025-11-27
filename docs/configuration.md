---
title: Configuration
icon: material/cog
---

## Example

Below is an example `.env` file for AniBridge:

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

For example, if `AB_SYNC_INTERVAL=900` is set globally and `AB_PROFILES__personal__SYNC_INTERVAL=1800` is set for a specific profile, the profile named 'personal' will use 1800 seconds as the sync interval while other profiles will use 900 seconds. If `AB_PROFILES__personal__SYNC_INTERVAL` is unset it falls back to the application's built-in default of 86400 seconds (24 hours).

## Shared Settings

These settings can be defined globally or overridden on a per-profile basis.

### `LIBRARY_PROVIDER`

`str` (default: `plex`)

Specifies the media library provider to use. Currently, `plex` is the only built-in option.

Load third-party providers via the [`PROVIDER_MODULES`](#provider_modules) setting.

---

### `LIST_PROVIDER`

`str` (default: `anilist`)

Specifies the list provider to use. Currently, `anilist` is the only built-in option.

Load third-party providers via the [`PROVIDER_MODULES`](#provider_modules) setting.

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
- `webhook`: Trigger syncs via [webhook payloads](https://support.plex.tv/articles/115002267687-webhooks/).

Setting `SYNC_MODES` to `None` or an empty list will cause the application to perform a single scan on startup and then exit.

By default, all three modes are enabled, allowing for instant, incremental updates via polling and webhooks, as well as a full periodic scan every [`SYNC_INTERVAL`](#sync_interval) seconds (default: 24 hours) to catch any failed/missed updates.

!!! info "Webhooks"

    Using the webhooks sync mode will require configuring your library provider (e.g., Plex) to send webhook payloads to AniBridge. Refer to the documentation of your library provider for instructions on setting up webhooks.

    _Note: not all library providers may support webhooks._

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

`list[Enum("status", "progress", "repeats", "review", "user_rating", "started_at", "finished_at")]` (Optional, default: `["review", "user_rating"]`)

Specifies which fields should **not** be synced. Available fields:

- `status` Watch status (watching, completed, etc.)
- `progress` Number of episodes/movies watched
- `repeats` Number of times rewatched
- `review` User's review/comments (text)
- `user_rating` User's rating/score
- `started_at` When the user started watching (date)
- `finished_at` When the user finished watching (date)

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

Controls how many days AniBridge keeps AniList backup snapshots before pruning older files. Set to `0` to disable automatic cleanup and retain all backups indefinitely.

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

## Provider Settings

Providers may consume additional configuration options. Refer to the documentation of each provider for details. Here are sample configuration options for the built-in providers:

### LIBRARY_PROVIDER: `plex`

Documentation: [anibridge/anibridge-plex-provider](https://github.com/anibridge/anibridge-plex-provider)

```yaml
providers:
    plex:
        url: ...
        token: ...
        user: ...
        sections: []
        genres: []
```

### LIST_PROVIDER: `anilist`

Documentation: [anibridge/anibridge-anilist-provider](https://github.com/anibridge/anibridge-anilist-provider)

```yaml
providers:
    anilist:
        token: ...
```

## Global Settings

These global settings cannot be overridden on the profile level and apply to all profiles.

### `DATA_PATH`

`str` (Optional, default: `./data`)

Path to store the database, backups, and custom mappings. This is shared across all profiles.

---

### `LOG_LEVEL`

`Enum("DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL")` (Optional, default: `INFO`)

Sets logging verbosity for the entire application.

!!! tip "Minimal Logging"

    For minimal logging, set the verbosity to `SUCCESS` which only logs successful operations like syncing entries.

!!! tip "Debugging"

    For the most detailed logs, set this to `DEBUG`.

---

### `MAPPINGS_URL`

`str` (Optional, default: `https://raw.githubusercontent.com/eliasbenb/PlexAniBridge-Mappings/v2/mappings.json`)

URL to the upstream mappings source. This can be a JSON or YAML file.

This option is only intended for advanced users who want to use their own upstream mappings source or disable upstream mappings entirely. For most users, it is recommended to keep the default value.

!!! info "Custom Mappings"

    This setting works in tandem with custom mappings stored in the `mappings/` directory inside the data path. Custom mappings will overload any upstream mappings.

??? question "Disabling Upstream Mappings"

    To disable upstream mappings, set this to an empty string: `""`.

---

### `WEB__ENABLED`

`bool` (Optional, default: `True`)

When enabled, the [web interface](./web/screenshots.md) is accessible.

---

### `WEB__HOST`

`str` (Optional, default: `0.0.0.0`)

The host address for the web interface.

---

### `AB__WEB__PORT`

`int` (Optional, default: `4848`)

The port for the web interface.

---

### `AB__WEB__BASIC_AUTH__USERNAME`

`str` (Optional, default: `None`)

HTTP Basic Authentication username for the web UI. Basic Auth is enabled only when both the username and password are provided. Leave unset to disable authentication.

---

### `AB__WEB__BASIC_AUTH__PASSWORD`

`str` (Optional, default: `None`)

HTTP Basic Authentication password for the web UI. Basic Auth is enabled only when both the username and password are provided. Leave unset to disable authentication.

---

### `AB__WEB__BASIC_AUTH__HTPASSWD_PATH`

`str` (Optional, default: `None`)

Path to an [Apache `htpasswd`](https://httpd.apache.org/docs/current/programs/htpasswd.html) file containing user credentials for HTTP Basic Authentication. When set, the web UI validates requests against this file. Only **bcrypt** (recommended) and **SHA1** hashed passwords are supported.

Providing an `htpasswd` file allows you to manage multiple users and rotate passwords without exposing plaintext credentials in the configuration. You may still set `AB_WEB_BASIC_AUTH_USERNAME` and `AB_WEB_BASIC_AUTH_PASSWORD`; both authentication methods will be accepted.

!!! tip "Generate htpasswd entries"

    <div class="htpasswd-generator" data-htpasswd-generator>
        <form class="htpasswd-generator__grid" autocomplete="off" novalidate>
            <label>Username
                <input data-htpasswd-username="" type="text" name="username" required  />
            </label>
            <label>Password
                <input data-htpasswd-password="" type="password" name="password" required />
            </label>
            <div class="htpasswd-generator__actions">
                <button type="submit">Generate htpasswd entry</button>
            </div>
        </form>
        <div class="htpasswd-generator__output">
            <textarea data-htpasswd-output="" autocomplete="off" readonly></textarea>
            <div class="htpasswd-generator__actions">
                <button type="button" data-htpasswd-copy="">Copy to clipboard</button>
            </div>
            <div class="htpasswd-generator__feedback" data-htpasswd-feedback=""></div>
        </div>
    </div>

---

### `AB__WEB__BASIC_AUTH__REALM`

`str` (Optional, default: `AniBridge`)

Realm label presented in the browser Basic Auth prompt and `WWW-Authenticate` response header.

## Advanced Examples

### Multiple Users

This example demonstrates configuring three distinct profiles, each with their own AniList accounts, Plex users, and customized sync preferences.

```dosini
# Global defaults shared by all profiles
AB_LIBRARY_PROVIDER=plex
AB_LIST_PROVIDER=anilist
AB_PROVIDERS__PLEX__TOKEN=admin_plex_token
AB_PROVIDERS__PLEX__URL=http://localhost:32400
AB_SYNC_MODES=["periodic"]

# Admin user - aggressive sync with full features
AB_PROFILES__admin__PROVIDERS__ANILIST__TOKEN=admin_anilist_token
AB_PROFILES__admin__PROVIDERS__PLEX__USER=admin_plex_user
AB_PROFILES__admin__DESTRUCTIVE_SYNC=True
AB_PROFILES__admin__EXCLUDED_SYNC_FIELDS=[]

# Family member - typical sync
AB_PROFILES__family__PROVIDERS__ANILIST__TOKEN=family_anilist_token
AB_PROFILES__family__PROVIDERS__PLEX__USER=family_plex_user

# Guest user - minimal sync
AB_PROFILES__guest__PROVIDERS__ANILIST__TOKEN=guest_anilist_token
AB_PROFILES__guest__PROVIDERS__PLEX__USER=guest_plex_user
AB_PROFILES__guest__EXCLUDED_SYNC_FIELDS=["notes", "score", "repeats", "started_at", "finished_at"]
```

### Per-Library Profiles

This example shows how to create separate profiles for different Plex libraries, allowing for tailored sync settings based on content type.

```dosini
# Global defaults shared by all profiles
AB_LIBRARY_PROVIDER=plex
AB_LIST_PROVIDER=anilist
AB_PROVIDERS__ANILIST__TOKEN=global_anilist_token
AB_PROVIDERS__PLEX__TOKEN=admin_plex_token
AB_PROVIDERS__PLEX__USER=admin_plex_user
AB_PROVIDERS__PLEX__URL=http://localhost:32400

# Movies library - aggressive sync with full features
AB_PROFILES__movies__PROVIDERS__PLEX__SECTIONS=["Anime Movies"]
AB_PROFILES__movies__FULL_SCAN=True
AB_PROFILES__movies__SYNC_INTERVAL=1800
AB_PROFILES__movies__EXCLUDED_SYNC_FIELDS=[]

# TV Shows library - more conservative with updates
AB_PROFILES__tvshows__PROVIDERS__PLEX__SECTIONS=["Anime"]
AB_PROFILES__tvshows__SYNC_MODES=["periodic"]
```

---
title: Configuration
icon: material/cog
---

## Example

AniBridge reads configuration from a YAML file named `config.yaml` that lives
inside the data directory `$AB_DATA_PATH` (defaults to `./data` or `/config` when
using the official Docker image).

A config editor is also available through the web UI.

```yaml title="config.yaml"
--8<-- "data/config.example.yaml"
```

## Configuration Hierarchy

Settings are applied in the following order:

1. **Profile-specific settings** (highest priority)
2. **Global shared settings** (medium priority)
3. **Built-in defaults** (lowest priority)

For example, if `sync_interval: 900` is defined globally and
`profiles.personal.sync_interval: 1800` overrides it for a specific profile, the
profile named `personal` will use `1800` seconds while other profiles keep the
global value of `900`. If `profiles.personal.sync_interval` is omitted it falls
back to the application's built-in default of `86400` seconds (24 hours).

## Shared Settings

These settings can be defined globally or overridden on a per-profile basis.

### `library_provider`

`str` (default: `plex`)

Specifies the media library provider to use. Currently, `plex` is the only built-in option.

Load third-party providers via the [`provider_modules`](#provider_modules) setting.

---

### `list_provider`

`str` (default: `anilist`)

Specifies the list provider to use. Currently, `anilist` is the only built-in option.

Load third-party providers via the [`provider_modules`](#provider_modules) setting.

---

### `sync_interval`

`int` (Optional, default: `86400`)

Interval in seconds to sync when using the `periodic` [sync mode](#sync_modes)

---

### `sync_modes`

`list[Enum("periodic", "poll", "webhook")]` (Optional, default: `["periodic", "poll", "webhook"]`)

Determines the triggers for scanning:

- `periodic`: Scan all items at the specified [sync interval](#sync_interval).
- `poll`: Poll for changes every 30 seconds, making incremental updates.
- `webhook`: Trigger syncs via [webhook payloads](https://support.plex.tv/articles/115002267687-webhooks/).

Setting `sync_modes` to `None` or an empty list will cause the application to perform a single scan on startup and then exit.

By default, all three modes are enabled, allowing for instant, incremental updates via polling and webhooks, as well as a full periodic scan every [`sync_interval`](#sync_interval) seconds (default: 24 hours) to catch any failed/missed updates.

!!! info "Webhooks"

    Using the webhooks sync mode will require configuring your library provider (e.g., Plex) to send webhook payloads to AniBridge. Refer to the documentation of your library provider for instructions on setting up webhooks.

    _Note: not all library providers may support webhooks._

### `full_scan`

`bool` (Optional, default: `False`)

When enabled, the scan process will include all items, regardless of watch activity. By default, only watched items are scanned.

!!! warning "Recommended Usage"

    Full scans are generally **not recommended** unless combined with [`destructive_sync`](#destructive_sync) to delete AniList entries for unwatched Plex content.

    Enabling `full_scan` can lead to **excessive API usage** and **longer processing times**.

---

### `destructive_sync`

`bool` (Optional, default: `False`)

Allows regressive updates and deletions, which **can cause data loss**.

!!! danger "Data Loss Warning"

    **Enable only if you understand the implications.**

    Destructive sync allows:

    - Deleting AniList entries.
    - Making regressive updates - e.g., if AniList progress is higher than Plex, AniList will be **lowered** to match Plex.

    To delete AniList entries for unwatched Plex content, enable both `FULL_SCAN` and `DESTRUCTIVE_SYNC`.

---

### `excluded_sync_fields`

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

### `dry_run`

`bool` (Optional, default: `False`)

When enabled:

- AniList data **is not modified**.
- Logs show what changes **would** have been made.

!!! success "First Run"

    Run with `dry_run` enabled on first launch to preview changes without modifying your AniList data.

---

### `backup_retention_days`

`int` (Optional, default: `30`)

Controls how many days AniBridge keeps AniList backup snapshots before pruning older files. Set to `0` to disable automatic cleanup and retain all backups indefinitely.

---

### `batch_requests`

`bool` (Optional, default: `False`)

When enabled, AniList API requests are made in batches:

1. Prior to syncing, a batch of requests is created to retrieve all the entries that will be worked on.
2. Post-sync, a batch of requests is created to update all the entries that were changed.

This can significantly reduce rate limiting, but at the cost of atomicity. If any request in the batch fails, the entire batch will fail.

For example, if a sync job finds 10 items to update with `batch_requests` enabled, all 10 requests will be sent at once. If any of the requests fail, all 10 updates will fail.

!!! success "First Run"

    The primary use case of batch requests is going through the first sync of a large library. It can significantly reduce rate limiting from AniList.

    For subsequent syncs, your data is pre-cached, and the benefit of batching is reduced.

---

### `search_fallback_threshold`

`int` (Optional, default: `-1`)

Determines how similar a title must be to the search query as a percentage to be considered a match.

The default behavior is to disable searching completely and only rely on the [community and local mappings database](./mappings/custom-mappings.md).

The higher the value, the more strict the title matching. A value of `100` requires an exact match, while `0` will match the first result returned by AniList, regardless of similarity.

## Provider Settings

Providers may consume additional configuration options. Refer to the documentation of each provider for details. Here are sample configuration options for the built-in providers:

### library_provider: `plex`

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

### list_provider: `anilist`

Documentation: [anibridge/anibridge-anilist-provider](https://github.com/anibridge/anibridge-anilist-provider)

```yaml
providers:
    anilist:
        token: ...
```

## Global Settings

These global settings cannot be overridden on the profile level and apply to all profiles.

### `log_level`

`Enum("DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL")` (Optional, default: `INFO`)

Sets logging verbosity for the entire application.

!!! tip "Minimal Logging"

    For minimal logging, set the verbosity to `SUCCESS` which only logs successful operations like syncing entries.

!!! tip "Debugging"

    For the most detailed logs, set this to `DEBUG`.

---

### `mappings_url`

`str` (Optional, default: `https://raw.githubusercontent.com/eliasbenb/PlexAniBridge-Mappings/v2/mappings.json`)

URL to the upstream mappings source. This can be a JSON or YAML file.

This option is only intended for advanced users who want to use their own upstream mappings source or disable upstream mappings entirely. For most users, it is recommended to keep the default value.

!!! info "Custom Mappings"

    This setting works in tandem with custom mappings stored in the `mappings/` directory inside the data path. Custom mappings will overload any upstream mappings.

??? question "Disabling Upstream Mappings"

    To disable upstream mappings, set this to an empty string: `""`.

---

### `web.enabled`

`bool` (Optional, default: `True`)

When enabled, the [web interface](./web/screenshots.md) is accessible.

---

### `web.host`

`str` (Optional, default: `0.0.0.0`)

The host address for the web interface.

---

### `web.port`

`int` (Optional, default: `4848`)

The port for the web interface.

---

### `web.basic_auth.username`

`str` (Optional, default: `None`)

HTTP Basic Authentication username for the web UI. Basic Auth is enabled only when both the username and password are provided. Leave unset to disable authentication.

---

### `web.basic_auth.password`

`str` (Optional, default: `None`)

HTTP Basic Authentication password for the web UI. Basic Auth is enabled only when both the username and password are provided. Leave unset to disable authentication.

---

### `web.basic_auth.htpasswd_path`

`str` (Optional, default: `None`)

Path to an [Apache `htpasswd`](https://httpd.apache.org/docs/current/programs/htpasswd.html) file containing user credentials for HTTP Basic Authentication. When set, the web UI validates requests against this file. Only **bcrypt** (recommended) and **SHA1** hashed passwords are supported.

Providing an `htpasswd` file allows you to manage multiple users and rotate passwords without exposing plaintext credentials in the configuration.

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

### `web.basic_auth.realm`

`str` (Optional, default: `AniBridge`)

Realm label presented in the browser Basic Auth prompt and `WWW-Authenticate` response header.

## Advanced Examples

### Multiple Users

This example demonstrates configuring three distinct profiles, each with their own AniList accounts, Plex users, and customized sync preferences.

```yaml
# Global defaults shared by all profiles
library_provider: plex
list_provider: anilist
providers:
    plex:
        token: admin_plex_token
        url: http://localhost:32400
sync_modes: ["periodic"]

profiles:
    admin:
        providers:
            anilist:
                token: admin_anilist_token
            plex:
                user: admin_plex_user
        destructive_sync: true
        excluded_sync_fields: []
    family:
        providers:
            anilist:
                token: family_anilist_token
            plex:
                user: family_plex_user
    guest:
        providers:
            anilist:
                token: guest_anilist_token
            plex:
                user: guest_plex_user
        excluded_sync_fields:
            - notes
            - score
            - repeats
            - started_at
            - finished_at
```

### Per-Library Profiles

This example shows how to create separate profiles for different Plex libraries, allowing for tailored sync settings based on content type.

```dosini
# Global defaults shared by all profiles
library_provider: plex
list_provider: anilist
providers:
    anilist:
        token: global_anilist_token
    plex:
        token: admin_plex_token
        user: admin_plex_user
        url: http://localhost:32400

profiles:
    movies:
        providers:
            plex:
                sections: ["Anime Movies"]
        full_scan: true
        sync_interval: 1800
        excluded_sync_fields: []
    tvshows:
        providers:
            plex:
                sections: ["Anime"]
        sync_modes: ["periodic"]
```

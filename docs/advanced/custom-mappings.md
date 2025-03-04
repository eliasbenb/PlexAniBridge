---
title: Custom Mappings
icon: material/map
---

# Custom Mappings

PlexAniBridge allows you to define custom mappings for Plex content to AniList, supplementing the [default mappings database](https://github.com/eliasbenb/PlexAniBridge-Mappings). This feature is particularly helpful for content that is missing or incorrectly mapped in the default database.

!!! note

    Custom mappings *merge* with the default mappings, they do not override them. This means that if you add a custom mapping for a series that is already in the default database, only the fields specified in the custom mapping will be updated. The remaining pre-existing fields will remain unchanged.

Below is an example mappings file. You can use [the JSON schema](https://github.com/eliasbenb/PlexAniBridge-Mappings/blob/HEAD/mappings.schema.json) or the [PlexAniBridge-Mappings database](https://github.com/eliasbenb/PlexAniBridge-Mappings) as reference.

```json title="mappings.custom.json"
--8<-- "mappings.example.json"
```

!!! tip "Including External Mappings"

    To include external mappings within a mappings file, you can use the `$includes` key. This key should contain an array of paths or HTTP URLs to other mappings files. The included mappings will be merged with the current mappings file in the order they are specified.

    ```json title="mappings.custom.json"
    {
      "$includes": [
        "https://example.com/mappings.json",
        "/path/to/mappings.json",
        "./relative/path/to/mappings.json"
      ]
    }
    ```

!!! tip "Mapping File Formats"

    Any of JSON, YAML, or TOML can be used as the format for the custom mappings file. The file extension determines the format of the file (`.json`, `.yaml`, `.yml`, or `.toml`).

## Local Custom Mappings

PlexAniBridge will look for a custom mappings file with the name `mappings.custom.(json|yaml|yml|toml)` in the `DATA_PATH` directory. The file extension determines the format of the file (JSON, YAML, or TOML).

## Community Custom Mappings

There are community maintained mappings repositories that you can use to get pre-made mappings for your content. You can include these mappings in your custom mappings file using the `$includes` key as explained above.

## Community Custom Mappings

There are community maintained mappings repositories that you can use to get pre-made mappings for your content. You can include these mappings in your custom mappings file using the `$includes` key as explained above.

- <a href="https://github.com/LuceoEtzio/PlexAniBridge-Custom-Mappings">
    <img src="https://avatars.githubusercontent.com/u/40282884?s=24&v=4" alt="LuceoEtzio" style="margin-right: 4px; border-radius: 50%; vertical-align: middle;">
    <span>LuceoEtzio/PlexAniBridge-Custom-Mappings</span>
  </a>

## Default Mappings

If you want to contribute your custom mappings to the community, you can submit a pull request to the [PlexAniBridge-Mappings](https://github.com/eliasbenb/PlexAniBridge-Mappings) repository. Your pull request should modify the [`mappings.edits.json`](https://github.com/eliasbenb/PlexAniBridge-Mappings/blob/HEAD/mappings.edits.json) and **not** the [`mappings.json`](https://github.com/eliasbenb/PlexAniBridge-Mappings/blob/HEAD/mappings.json) file.

To browse the existing mappings with a web UI, you can use the [PlexAniBridge-Mappings Query Builder](https://plexanibridge-mappings.elias.eu.org).

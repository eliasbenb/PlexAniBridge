---
title: Custom Mappings
icon: material/cable-data
---

# Custom Mappings

PlexAniBridge allows you to define custom mappings for Plex content to AniList, complementing the default mappings database. This feature is particularly helpful for content that is missing or incorrectly mapped in the default database.

## Local Custom Mappings

Custom mappings are stored in a JSON file named `mappings.custom.json`, located in the `DATA_PATH` directory. Any mappings added here will take precedence over existing entries in the default database.

!!! note

    Entries in the custom mappings file *merge* with the pre-existing entries, they do not override them. This means that if you add a custom mapping for a series that is already in the default database, only the fields specified in the custom mapping will be updated. The remaining pre-existing fields will remain unchanged.

The custom mappings file adheres to [the same JSON schema](https://github.com/eliasbenb/PlexAniBridge-Mappings/blob/HEAD/mappings.schema.json) used in [PlexAniBridge-Mappings](https://github.com/eliasbenb/PlexAniBridge-Mappings). You can refer to the default database or the schema for guidance. Below is an example of a `mappings.custom.json` file:

```json title="mappings.custom.json"
--8<-- "mappings.example.json"
```

## Remote Custom Mappings

If you want to contribute your custom mappings to the community, you can submit a pull request to the [PlexAniBridge-Mappings](https://github.com/eliasbenb/PlexAniBridge-Mappings) repository. Your pull request should modify the [`mappings.edits.json`](https://github.com/eliasbenb/PlexAniBridge-Mappings/blob/HEAD/mappings.edits.json) and **not** the [`mappings.json`](https://github.com/eliasbenb/PlexAniBridge-Mappings/blob/HEAD/mappings.json) file.

To browse the existing mappings with a web UI, you can use the [PlexAniBridge-Mappings Query Builder](https://plexanibridge-mappings.elias.eu.org).

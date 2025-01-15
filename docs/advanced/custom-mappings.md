---
title: Custom Mappings
icon: material/cable-data
---

In addition to the default mappings database, PlexAniBridge supports custom mappings for Plex content to AniList. This feature is useful for mapping content that might be missing or incorrectly mapped in the default database.

## Custom Mappings File

Custom mappings are stored in a JSON file named `mappings.custom.json` in the `DATA_PATH` directory. Any custom mappings you add will overwrite and overload the default mappings if it existed.

The custom mappings file shares [the same JSON schema](https://github.com/eliasbenb/PlexAniBridge-Mappings/blob/main/mappings.schema.json) as in [eliasbenb/PlexAniBridge-Mappings](https://github.com/eliasbenb/PlexAniBridge-Mappings). You can use the default database's mappings or the JSON schema for references. Additionally, below is an example `mappings.custom.json`

```json title="mappings.custom.json"
--8<-- "mappings.example.json"
```

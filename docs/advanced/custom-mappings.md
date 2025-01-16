---
title: Custom Mappings
icon: material/cable-data
---

# Custom Mappings

PlexAniBridge allows you to define custom mappings for Plex content to AniList, complementing the default mappings database. This feature is particularly helpful for content that is missing or incorrectly mapped in the default database.

## Custom Mappings File

Custom mappings are stored in a JSON file named `mappings.custom.json`, located in the `DATA_PATH` directory. Any mappings added here will take precedence over existing entries in the default database.

!!! note

    Entries in the custom mappings file *merge* with the pre-existing entries, they do not override them. This means that if you add a custom mapping for a series that is already in the default database, only the fields specified in the custom mapping will be updated. The remaining pre-existing fields will remain unchanged.

The custom mappings file adheres to [the same JSON schema](https://github.com/eliasbenb/PlexAniBridge-Mappings/blob/main/mappings.schema.json) used in [PlexAniBridge-Mappings](https://github.com/eliasbenb/PlexAniBridge-Mappings). You can refer to the default database or the schema for guidance. Below is an example of a `mappings.custom.json` file:

```json title="mappings.custom.json"
--8<-- "mappings.example.json"
```

---
title: Custom Mappings
icon: material/map
---

# Custom Mappings

AniBridge allows you to define custom mappings for Plex content to AniList, supplementing the [default mappings database](https://github.com/eliasbenb/PlexAniBridge-Mappings). This feature is particularly helpful for content that is missing or incorrectly mapped in the default database.

!!! note

    Custom mappings *merge* with the default mappings, they do not override them. This means that if you add a custom mapping for a series that is already in the default database, only the fields specified in the custom mapping will be updated. The remaining pre-existing fields will remain unchanged.

Below is an example mappings file. You can use [the JSON schema](https://github.com/eliasbenb/PlexAniBridge-Mappings/blob/HEAD/mappings.schema.json) or the [PlexAniBridge-Mappings database](https://github.com/eliasbenb/PlexAniBridge-Mappings) as reference.

```yaml title="mappings.custom.yaml"
--8<-- "data/mappings.example.yaml"
```

??? tip "JSON Format for Mappings"

    The mappings file can also be written in JSON format. Here is the same example in JSON:

    ```json title="mappings.custom.json"
    --8<-- "data/mappings.example.json"
    ```

!!! tip "Including External Mappings"

    ```yaml title="mappings.custom.yaml"
    $includes:
        - "https://example.com/mappings.json"
        - "/path/to/mappings.yaml"
        - "./relative/path/to/mappings.yml"
    ```

## Local Custom Mappings

AniBridge looks for a custom mappings file named `mappings.custom.(json|yaml|yml)` inside the data directory. The file extension determines the format of the file (YAML or JSON).

## Community Custom Mappings

There are community maintained mappings repositories that you can use to get pre-made mappings for your content. You can include these mappings in your custom mappings file using the `$includes` key as explained above.

- <a href="https://github.com/LuceoEtzio/AniBridge-Custom-Mappings">
    <img src="https://avatars.githubusercontent.com/u/40282884?s=24&v=4" alt="LuceoEtzio" style="margin-right: 4px; border-radius: 50%; vertical-align: middle;">
    <span>LuceoEtzio/AniBridge-Custom-Mappings</span>
  </a>

## Default Mappings

If you want to contribute your custom mappings to the community, you can submit a pull request to the [PlexAniBridge-Mappings](https://github.com/eliasbenb/PlexAniBridge-Mappings) repository. Your pull request should modify the [`mappings.edits.yaml`](https://github.com/eliasbenb/PlexAniBridge-Mappings/blob/HEAD/mappings.edits.yaml) and **not** the [`mappings.json`](https://github.com/eliasbenb/PlexAniBridge-Mappings/blob/HEAD/mappings.json) file.

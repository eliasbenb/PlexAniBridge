---
title: Mappings Querying Language
icon: simple/quicklook
---

# Mappings Querying Language

PlexAniBridge provides a Booru-like querying language for searching the mappings database and AniList API. You can use this language on the [Mappings Page](../web/screenshots.md#mappings) of the web interface or through the API at:

```
/api/mappings?q=<query>
```

## Basic Syntax

The querying language supports a wide range of operators to build flexible and complex queries. The web UI includes a search bar with query suggestions to help you construct valid queries.

### Search Terms

- **Fielded search:** `foo:bar` → Search for `bar` in field `foo`
- **AniList search:** `"foo"` → Search AniList API for the bare term `foo`

### Boolean Operators

- **AND:** `foo bar` → Search for results matching both `foo` *and* `bar`
- **OR (prefix):** `~foo ~bar baz` → Search for `(foo OR bar) AND baz` *(tilde marks OR terms within an AND group)*
- **OR (infix):** `foo | bar baz` → Search for `foo OR (bar AND baz)` *(pipe creates OR between AND expressions)*
- **NOT:** `-foo` → Exclude results matching `foo`

### Grouping

- `(foo | bar) baz` → Search for `(foo OR bar) AND baz`

### Ranges

- `foo:<10` → Search where `foo` is less than 10
- `foo:100..210` → Search where `foo` is between 100 and 210

### Field Presence

- `has:foo` → Search for mappings that have the field `foo`

### Wildcards

Use `*` for any sequence of characters and `?` for a single character. Matching is case-insensitive.

- `foo:bar*` → Search for mappings where field `foo` starts with `bar`
- `foo:*bar` → Search for mappings where field `foo` ends with `bar`
- `foo:b?r` → Search for mappings where field `foo` matches `b?r` (e.g., `bar`, `ber`, `bir`, etc.)

### Querying JSON fields

For fields that store JSON dictionaries, you can use the following syntax:

- `foo:bar` → Search for mappings where the JSON field `foo` contains the key `bar` or the value `bar`
- `foo:bar*` → Search for mappings where the JSON field `foo` contains a key starting with `bar` or a value starting with `bar`. All other wildcard patterns are also supported.

## Supported Database Fields

The following fields are queried against the local mappings database:

- `anilist` → AniList ID
- `anidb` → AniDB ID
- `imdb` → IMDb ID
- `mal` → MyAnimeList ID
- `tmdb_movie` → TMDb Movie ID
- `tmdb_show` → TMDb Show ID
- `tvdb` → TVDB Show ID
- `tmdb_mappings` → Searches keys/values in TMDb mappings dictionary
- `tvdb_mappings` → Searches keys/values in TVDB mappings dictionary

## Supported AniList Fields

The following fields are queried against the AniList API:

- `"foo"` → Searches AniList for the bare term `foo`.
- `anilist.title"` → Alias for `"foo"`, searches AniList for the bare term `foo`.
- `anilist.duration` → Duration in minutes
- `anilist.episodes` → Number of episodes
- `anilist.start_date` → Start date (YYYYMMDD)
- `anilist.end_date` → End date (YYYYMMDD)
- `anilist.format` → Format (e.g., TV, MOVIE, OVA, etc.)
- `anilist.status` → Status (e.g., FINISHED, RELEASING, NOT_YET_RELEASED, etc.)
- `anilist.genre` → Genre (e.g., Action, Comedy, Drama, etc.)
- `anilist.tag` → Tag (e.g., Mecha, School, Shounen, etc.)
- `anilist.average_score` → Average score (0-100)
- `anilist.popularity` → Popularity (number of AniList users with the entry in their list)

## Example Queries

```bash
"Dororo" 
# Title search for "Dororo"

anilist:101347 
# AniList ID lookup

tvdb:328592 | tmdb_show:21298
# TVDB ID 328592 OR TMDb Show ID 21298

anilist:>100000
# AniList IDs greater than 100000

-(anilist:100..200)
# Exclude AniList IDs 100 to 200 (inclusive)

-has:tvdb_mappings
# Exclude results that have TVDB mappings

imdb:tt0*
# IMDb IDs starting with "tt0"

tvdb_mappings:s0
# TVDB mappings with season 0

tmdb_mappings:e12*
# TMDb mappings starting with episode 12

anilist.status:RELEASING anilist.genre:Action
# Currently releasing anime in the Action genre

anilist.format:TV anilist.average_score:>80 anilist.popularity:>5000
# TV format anime with average score over 80 and popularity over 5000
```

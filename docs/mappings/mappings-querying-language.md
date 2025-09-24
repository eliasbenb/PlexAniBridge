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

### Wildcards on text fields

- Use `*` for any sequence of characters and `?` for a single character.
- Matching is case-insensitive.
- Works on text-based fields: `imdb` and `tvdb_mappings` (both keys like `s1` and values like `e1-e12`).

Examples:

```bash
tvdb_mappings:s1? # season key like s1X (s10..s19)
tvdb_mappings:e12* # any episode range starting with e12-
tvdb_mappings:*e24 # any episode range ending with e24
```

## Supported Fields

- `""` → Title (AniList API search for bare term)
- `anilist` → AniList ID
- `anidb` → AniDB ID
- `imdb` → IMDb ID
- `mal` → MyAnimeList ID
- `tmdb_movie` → TMDb Movie ID
- `tmdb_show` → TMDb Show ID
- `tvdb` → TVDB Show ID
- `tvdb_mappings` → Searches keys/values in TVDB mappings dictionary

## Example Queries

```bash
"Dororo" 
# Title search for "Dororo"

anilist:101347 
# AniList ID lookup

"Dororo" (tvdb:328592 | tmdb_show:21298) 
# Title search for "Dororo" with either TVDB or TMDb Show ID

anilist:>100000
# AniList IDs greater than 100000

-(anilist:100..200)
# Exclude AniList IDs 100 to 200 (inclusive)

-has:tvdb_mappings 
# Exclude results that have TVDB mappings
```

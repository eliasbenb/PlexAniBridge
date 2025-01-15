---
title: Introduction
icon: material/home
---

PlexAniBridge is a synchronization tool that automatically keeps your AniList profile up-to-date based on your Plex watching activity.

## Features

- Synchronize watch status, watch progress, repeat counts, rating scores, text reviews, and start/end dates
- Mapping Plex content (movies, shows, seasons, episode ranges, specials) to AniList via [a mappings database](https://github.com/eliasbenb/PlexAniBridge-Mappings) with fuzzy title search fallback, plus support for custom AniList ID mappings.
- Partial scanning support — only consider items added/updated/rated since the last sync
- Scheduled sync jobs with configurable polling capabilities
- Multi-user support — sync multiple Plex users and home users to multiple AniList accounts
- Intelligent caching of Plex and AniList requests to reduce rate limits
- [Docker](./quick-start/docker.md) 🐳 deployments

## Special Thanks/Dependencies

- [Kometa Mappings](https://github.com/Kometa-Team/Anime-IDs)
- [Python-PlexAPI](https://github.com/pkkid/python-plexapi)

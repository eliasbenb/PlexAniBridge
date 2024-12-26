---
title: Introduction
icon: material/home
---

PlexAniBridge is a synchronization tool that automatically keeps your AniList profile up-to-date based on your Plex watching activity.

## Features

- Synchronize watch status, watch progress, repeat counts, rating scores, text reviews, and start/end dates
- Mapping Plex movies, shows, seasons, episode ranges, and specials to AniList using [Kometa mappings](https://github.com/Kometa-Team/Anime-IDs) with fuzzy title search as a fallback
- Partial scanning support — only consider items added/updated/rated since the last sync
- Scheduled sync jobs with configurable polling capabilities
- Multi-user support — sync multiple Plex users and home users to multiple AniList accounts
- Intelligent caching of Plex and AniList requests to reduce rate limits
- [Docker](./quick-start/docker.md) 🐳 deployments

## Special Thanks/Dependencies

- [Kometa Mappings](https://github.com/Kometa-Team/Anime-IDs)
- [Python-PlexAPI](https://github.com/pkkid/python-plexapi)

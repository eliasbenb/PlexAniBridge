---
title: Introduction
icon: material/home
---

# Introduction

PlexAniBridge is a tool designed to keep your AniList profile automatically synced with your Plex activity. Whether you're tracking your watch progress, ratings, or reviews, PlexAniBridge has you covered.

[![Discord Shield](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fdiscord.com%2Fapi%2Finvites%2Fey8kyQU9aD%3Fwith_counts%3Dtrue&query=%24.approximate_member_count&style=for-the-badge&logo=discord&label=Discord%20Users&labelColor=%23313338&color=%235865f2)](https://discord.gg/ey8kyQU9aD) [![GitHub Shield](https://img.shields.io/github/stars/eliasbenb/PlexAniBridge?style=for-the-badge&logo=github&label=GitHub%20Stars&labelColor=%2324292e&color=%23f0f0f0)](https://github.com/eliasbenb/PlexAniBridge) ![Docker Pulls Shield](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fipitio.github.io%2Fbackage%2Feliasbenb%2FPlexAniBridge%2Fplexanibridge.json&query=downloads&style=for-the-badge&logo=docker&label=Docker%20Pulls&color=2496ed&link=https%3A%2F%2Fgithub.com%2Feliasbenb%2FPlexAniBridge%2Fpkgs%2Fcontainer%2Fplexanibridge)

[Quick Start Docker](./quick-start/docker.md) | [Quick Start Source](./quick-start/source.md) | [Configuration](./configuration.md)

## Key Features

- **Comprehensive Synchronization**: Tracks watch status, progress, repeat counts, ratings, text reviews, and start/end dates.
- **Smart Content Mapping**: Matches Plex content (movies, shows, specials, etc.) to AniList using [a robust mappings database](https://github.com/eliasbenb/PlexAniBridge-Mappings) with fuzzy title search as a fallback and the ability to add custom media mappings.
- **Efficient Scanning**: Supports various modes of scanning like [partial](./configuration.md#full_scan), [full](./configuration.md#full_scan), or [polling](./configuration.md#polling_scan) scans to minimize API usage.
- **Flexible Scheduling**: Configurable [synchronization intervals](./configuration.md#sync_interval) in addition to polling capabilities.
- **Multi-User Support**: Sync multiple [Plex users](./configuration.md#plex_user) and home users with their respective [AniList users](./configuration.md#anilist_token).
- **Optimized Performance**: Intelligent caching of requests to minimize API rate limits.
- **Easy Deployment**: Fully compatible with [Docker deployments](./quick-start/docker.md) 🐳.

## Acknowledgments

- [Kometa Mappings](https://github.com/Kometa-Team/Anime-IDs): The inspiration behind the mappings database.
- [Python-PlexAPI](https://github.com/pkkid/python-plexapi): Powerful and straightforward Plex API bindings.

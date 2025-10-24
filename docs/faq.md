---
title: FAQ
icon: material/frequently-asked-questions
---

## Why is my repeat count incorrect?

PlexAniBridge relies on your Plex server to provide accurate `viewCount` attributes when calculating the repeat count. It is a known issue that Plex may not always update this count reliably or in a way users might expect.

Certain actions can make the `viewCount` behave unexpectedly or become corrupted. Common causes include deleting and re-adding items, syncing play history across multiple devices, and manually marking an item as watched/unwatched.

If you notice discrepancies in repeat counts, consider querying your Plex server directly to verify the `viewCount` values for specific items. If the counts are incorrect at the source, PlexAniBridge will reflect those inaccuracies. See [#174](https://github.com/eliasbenb/PlexAniBridge/issues/174) for more details.

_Note: the `viewCount` attribute **is not** equivalent to the number of items under "View Play History" in the Plex UI._

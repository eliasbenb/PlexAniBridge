"""Plex client abstractions consumed by the Plex library provider."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Literal
from urllib.parse import urlparse

from plexapi.library import LibrarySection, MovieSection, ShowSection
from plexapi.myplex import MyPlexAccount, MyPlexUser
from plexapi.server import PlexServer
from plexapi.video import Movie, Show, Video
from tzlocal import get_localzone

from src.exceptions import PlexUserNotFoundError
from src.utils.requests import SelectiveVerifySession

__all__ = ["PlexClient", "PlexClientBundle", "PlexClientConfig"]


@dataclass(slots=True)
class PlexClientConfig:
    """Settings required to build Plex API clients."""

    url: str
    token: str
    user: str | None


@dataclass(slots=True)
class PlexClientBundle:
    """Container for Plex server connections and associated metadata."""

    admin_client: PlexServer
    user_client: PlexServer
    account: MyPlexAccount
    target_user: MyPlexUser | None
    user_id: int
    display_name: str
    is_admin: bool


@dataclass(slots=True)
class _FrozenCacheEntry:
    """Immutable cache entry for storing Plex item keys with expiration."""

    keys: frozenset[str]
    expires_at: float


class PlexClient:
    """High-level Plex client wrapper used by the library provider."""

    def __init__(
        self,
        *,
        config: PlexClientConfig,
        section_filter: Sequence[str] | None = None,
        genre_filter: Sequence[str] | None = None,
    ) -> None:
        """Initialize client wrapper with optional section and genre filters.

        Args:
            config (PlexClientConfig): Configuration for connecting to Plex.
            section_filter (Sequence[str] | None): If provided, only include sections
                whose titles are in this list (case-insensitive).
            genre_filter (Sequence[str] | None): If provided, only include items that
                have at least one genre in this list.
        """
        self._config = config
        self._section_filter = {value.lower() for value in section_filter or ()}
        self._genre_filter = tuple(genre_filter or ())
        self._local_tz = get_localzone()

        self._bundle: PlexClientBundle | None = None
        self._admin_client: PlexServer | None = None
        self._user_client: PlexServer | None = None

        self._sections: list[MovieSection | ShowSection] = []
        self._continue_cache: dict[str, _FrozenCacheEntry] = {}
        self._ordering_cache: dict[int, Literal["tmdb", "tvdb", ""]] = {}
        self._watchlist_cache: _FrozenCacheEntry | None = None
        self._on_deck_window: timedelta | None = None

    async def initialize(self) -> None:
        """Establish the Plex session and prime provider caches."""
        bundle = await asyncio.to_thread(self._create_client_bundle)
        self._bundle = bundle
        self._admin_client = bundle.admin_client
        self._user_client = bundle.user_client

        self._sections = await asyncio.to_thread(self._load_sections)
        self._on_deck_window = await asyncio.to_thread(self._get_on_deck_window)
        self.clear_cache()

    async def close(self) -> None:
        """Release any held resources."""
        self._bundle = None
        self._admin_client = None
        self._user_client = None
        self._sections.clear()
        self.clear_cache()

    def clear_cache(self) -> None:
        """Clear cached continue-watching and ordering metadata."""
        self._continue_cache.clear()
        self._ordering_cache.clear()

    @property
    def bundle(self) -> PlexClientBundle:
        """Return the active client bundle."""
        if self._bundle is None:
            raise RuntimeError("Plex client has not been initialized")
        return self._bundle

    @property
    def sections(self) -> Sequence[MovieSection | ShowSection]:
        """Return the cached list of Plex library sections."""
        return tuple(self._sections)

    @property
    def on_deck_window(self) -> timedelta | None:
        """Return the configured on-deck time window if available."""
        return self._on_deck_window

    async def list_section_items(
        self,
        section: LibrarySection,
        *,
        min_last_modified: datetime | None = None,
        require_watched: bool = False,
        keys: Sequence[str] | None = None,
        **kwargs,
    ) -> Sequence[Movie | Show]:
        """Return Plex media items that match the provided filters."""

        def _search_sync() -> tuple[Movie | Show, ...]:
            filters: list[dict] = []

            if min_last_modified is not None:
                filters.append(self._build_modified_filter(section, min_last_modified))

            if require_watched:
                filters.append(self._build_watched_filter(section))

            if self._genre_filter:
                filters.append({"genre": self._genre_filter})

            search_kwargs = dict(kwargs)
            if filters:
                search_kwargs["filters"] = {"and": filters}

            try:
                results = section.search(**search_kwargs)
            except Exception:
                return ()

            key_filter: frozenset[str] | None = (
                frozenset(str(k) for k in keys) if keys else None
            )

            items: list[Movie | Show] = []
            for item in results:
                if not isinstance(item, (Movie, Show)):
                    continue

                if key_filter is not None and str(item.ratingKey) not in key_filter:
                    continue

                items.append(item)

            return tuple(items)

        return await asyncio.to_thread(_search_sync)

    def is_on_continue_watching(
        self,
        section: LibrarySection,
        item: Video,
    ) -> bool:
        """Determine whether the given item appears in the Continue Watching hub."""
        self._ensure_user_client()
        cache_entry = self._continue_cache.get(section.key)
        now = monotonic()
        if cache_entry is None or cache_entry.expires_at <= now:
            cache_entry = self._refresh_continue_cache(section)
        return str(item.ratingKey) in cache_entry.keys

    async def fetch_history(self, item: Video) -> Sequence[tuple[str, datetime]]:
        """Return the watch history for the given Plex item."""
        admin_client = self._ensure_admin_client()
        try:
            history_objects = await asyncio.to_thread(
                admin_client.history,
                ratingKey=item.ratingKey,
                accountID=1 if self.bundle.is_admin else self.bundle.user_id,
                librarySectionID=item.librarySectionID,
            )
        except Exception:
            return []

        entries = [
            (str(record.ratingKey), record.viewedAt)
            for record in history_objects
            if record.viewedAt is not None
        ]
        return entries

    def is_on_watchlist(self, item: Video) -> bool:
        """Determine whether the given item appears in the user's watchlist."""
        if not self.bundle.is_admin:
            return False

        now = monotonic()
        cache_entry = self._watchlist_cache
        if cache_entry is None or cache_entry.expires_at <= now:
            cache_entry = self._refresh_watchlist_cache()

        return item.guid is not None and item.guid in cache_entry.keys

    def get_ordering(self, show: Show) -> Literal["tmdb", "tvdb", ""]:
        """Return the preferred episode ordering for the provided show."""
        if show.showOrdering:
            if show.showOrdering == "tmdbAiring":
                return "tmdb"
            if show.showOrdering in {"tvdbAiring", "aired"}:
                return "tvdb"
            return ""

        cached = self._ordering_cache.get(show.librarySectionID)
        if cached is not None:
            return cached

        ordering_setting = next(
            (
                setting
                for setting in show.section().settings()
                if setting.id == "showOrdering"
            ),
            None,
        )
        if not ordering_setting:
            resolved = ""
        else:
            value = ordering_setting.value
            if value == "tmdbAiring":
                resolved = "tmdb"
            elif value in {"aired", "tvdbAiring"}:
                resolved = "tvdb"
            else:
                resolved = ""

        self._ordering_cache[show.librarySectionID] = resolved
        return resolved

    def _create_client_bundle(self) -> PlexClientBundle:
        return _default_bundle(self._config)

    def _load_sections(self) -> list[MovieSection | ShowSection]:
        user_client = self._ensure_user_client()
        sections: list[MovieSection | ShowSection] = []

        for raw in user_client.library.sections():
            if not isinstance(raw, (MovieSection, ShowSection)):
                continue
            if self._section_filter and raw.title.lower() not in self._section_filter:
                continue
            sections.append(raw)
        return sections

    def _get_on_deck_window(self) -> timedelta | None:
        admin_client = self._admin_client
        if admin_client is None:
            return None
        try:
            window_value = admin_client.settings.get("onDeckWindow").value
        except Exception:
            return None
        try:
            return timedelta(weeks=float(window_value))
        except (TypeError, ValueError):
            return None

    def _build_modified_filter(
        self, section: LibrarySection, reference: datetime
    ) -> dict:
        reference_dt = self._coerce_datetime(reference)
        if reference_dt is None:
            reference_dt = datetime.now(tz=UTC)

        if section.type == "movie":
            return {
                "or": [
                    {"lastViewedAt>>=": reference_dt},
                    {"lastRatedAt>>=": reference_dt},
                    {"addedAt>>=": reference_dt},
                    {"updatedAt>>=": reference_dt},
                ]
            }

        return {
            "or": [
                {"show.lastViewedAt>>=": reference_dt},
                {"show.lastRatedAt>>=": reference_dt},
                {"show.addedAt>>=": reference_dt},
                {"show.updatedAt>>=": reference_dt},
                {"season.lastViewedAt>>=": reference_dt},
                {"season.lastRatedAt>>=": reference_dt},
                {"season.addedAt>>=": reference_dt},
                {"season.updatedAt>>=": reference_dt},
                {"episode.lastViewedAt>>=": reference_dt},
                {"episode.lastRatedAt>>=": reference_dt},
                {"episode.addedAt>>=": reference_dt},
                {"episode.updatedAt>>=": reference_dt},
            ]
        }

    def _build_watched_filter(self, section: LibrarySection) -> dict:
        epoch = datetime.fromtimestamp(0, tz=UTC)
        if section.type == "movie":
            return {
                "or": [
                    {"viewCount>>": 0},
                    {"lastViewedAt>>": epoch},
                    {"lastRatedAt>>": epoch},
                ]
            }

        return {
            "or": [
                {"show.viewCount>>": 0},
                {"show.lastViewedAt>>": epoch},
                {"show.lastRatedAt>>": epoch},
                {"season.viewCount>>": 0},
                {"season.lastViewedAt>>": epoch},
                {"season.lastRatedAt>>": epoch},
                {"episode.viewCount>>": 0},
                {"episode.lastViewedAt>>": epoch},
                {"episode.lastRatedAt>>": epoch},
            ]
        }

    def _refresh_continue_cache(self, section: LibrarySection) -> _FrozenCacheEntry:
        """Refresh the continue-watching cache for the given section."""
        rating_keys: set[str] = set()
        try:
            for item in section.continueWatching():
                if item.ratingKey is not None:
                    rating_keys.add(str(item.ratingKey))
        except Exception:
            rating_keys.clear()

        entry = _FrozenCacheEntry(
            keys=frozenset(rating_keys),
            expires_at=monotonic() + 300,
        )
        self._continue_cache[section.key] = entry
        return entry

    def _refresh_watchlist_cache(self) -> _FrozenCacheEntry:
        """Refresh the watchlist cache for the given section."""
        if not self.bundle.is_admin:
            return _FrozenCacheEntry(keys=frozenset(), expires_at=monotonic() + 300)
        try:
            # Rating keys won't work here because watchlist items can exist outside of
            # the user's server. We'll use GUIDs as as substitute.
            keys = {
                str(item.guid)
                for item in self.bundle.account.watchlist()
                if item.guid is not None
            }
        except Exception:
            keys = set()

        entry = _FrozenCacheEntry(
            keys=frozenset(keys),
            expires_at=monotonic() + 300,
        )
        self._watchlist_cache = entry
        return entry

    def _coerce_datetime(self, value: datetime | str | None) -> datetime | None:
        """Convert various datetime representations into a timezone-aware datetime."""
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self._local_tz)
        return dt.astimezone(UTC)

    def _ensure_user_client(self) -> PlexServer:
        """Ensure the user Plex client is available."""
        if self._user_client is None:
            raise RuntimeError("Plex client has not been initialized")
        return self._user_client

    def _ensure_admin_client(self) -> PlexServer:
        """Ensure the admin Plex client is available."""
        if self._admin_client is None:
            raise RuntimeError("Plex client has not been initialized")
        return self._admin_client


def _default_bundle(config: PlexClientConfig) -> PlexClientBundle:
    """TODO: temporary function while staging client refactor."""
    session = _build_session(config.url)
    admin_client = _create_admin_client(config, session=session)
    account = admin_client.myPlexAccount()

    requested_user = (config.user or "").strip() or None
    target_user: MyPlexUser | None = None
    is_admin = True

    if requested_user and not _matches_account(requested_user, account):
        target_user = _match_plex_user(requested_user, account.users())
        is_admin = False
    elif requested_user:
        is_admin = True

    user_client = _create_user_client(
        admin_client=admin_client,
        account=account,
        target_user=target_user,
    )

    user_id = target_user.id if target_user else account.id
    display_name = _resolve_display_name(account, target_user, requested_user)

    return PlexClientBundle(
        admin_client=admin_client,
        user_client=user_client,
        account=account,
        target_user=target_user,
        user_id=user_id,
        display_name=display_name,
        is_admin=is_admin,
    )


def _build_session(url: str) -> SelectiveVerifySession | None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return None
    return SelectiveVerifySession(whitelist=[parsed.hostname])


def _create_admin_client(
    config: PlexClientConfig, *, session: SelectiveVerifySession | None
) -> PlexServer:
    return PlexServer(config.url, config.token, session=session)


def _matches_account(requested: str, account: MyPlexAccount) -> bool:
    requested_lower = requested.lower()
    for candidate in (account.username, account.email, account.title):
        if candidate and candidate.lower() == requested_lower:
            return True
    return False


def _match_plex_user(plex_user: str, users: Sequence[MyPlexUser]) -> MyPlexUser:
    target = plex_user.lower()
    for user in users:
        if target in (
            (user.username or "").lower(),
            (user.email or "").lower(),
            (user.title or "").lower(),
        ):
            return user
    raise PlexUserNotFoundError(f"User '{plex_user}' not found in Plex account")


def _create_user_client(
    *,
    admin_client: PlexServer,
    account: MyPlexAccount,
    target_user: MyPlexUser | None,
) -> PlexServer:
    if target_user is None:
        return admin_client

    login = target_user.username or target_user.email or target_user.title
    if not login:
        raise PlexUserNotFoundError(
            "Unable to switch Plex user: no username, email, or title available"
        )
    try:
        return admin_client.switchUser(login)
    except Exception as exc:
        raise PlexUserNotFoundError(f"Failed to switch to Plex user '{login}'") from exc


def _resolve_display_name(
    account: MyPlexAccount,
    target_user: MyPlexUser | None,
    requested: str | None,
) -> str:
    if target_user is not None:
        candidates = (
            target_user.username,
            target_user.email,
            target_user.title,
            requested,
            "Plex User",
        )
    else:
        candidates = (
            account.username,
            account.email,
            account.title,
            requested,
            "Plex Admin",
        )

    for candidate in candidates:
        if candidate:
            return candidate
    return "Plex User"

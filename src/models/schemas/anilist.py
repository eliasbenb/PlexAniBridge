"""AniList Models Module."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from functools import cache
from typing import Annotated, Any, ClassVar, Generic, TypeVar, get_args, get_origin

from pydantic import AfterValidator, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

UTCDateTime = Annotated[
    datetime, AfterValidator(lambda dt: dt.astimezone(timezone.utc))
]


class AniListBaseEnum(StrEnum):
    """Base enum for AniList models."""

    pass


class MediaType(AniListBaseEnum):
    """Enum representing media types (ANIME, MANGA)."""

    ANIME = "ANIME"
    MANGA = "MANGA"


class MediaFormat(AniListBaseEnum):
    """Enum representing media formats (TV, MOVIE, etc)."""

    TV = "TV"
    TV_SHORT = "TV_SHORT"
    MOVIE = "MOVIE"
    SPECIAL = "SPECIAL"
    OVA = "OVA"
    ONA = "ONA"
    MUSIC = "MUSIC"
    MANGA = "MANGA"
    NOVEL = "NOVEL"
    ONE_SHOT = "ONE_SHOT"


class MediaStatus(AniListBaseEnum):
    """Enum representing media status (FINISHED, RELEASING, etc)."""

    FINISHED = "FINISHED"
    RELEASING = "RELEASING"
    NOT_YET_RELEASED = "NOT_YET_RELEASED"
    CANCELLED = "CANCELLED"
    HIATUS = "HIATUS"


class MediaSeason(AniListBaseEnum):
    """Enum representing media seasons (WINTER, SPRING, etc)."""

    WINTER = "WINTER"
    SPRING = "SPRING"
    SUMMER = "SUMMER"
    FALL = "FALL"


class MediaSort(AniListBaseEnum):
    """Enum representing sort options for media queries."""

    ID = "ID"
    ID_DESC = "ID_DESC"
    TITLE_ROMAJI = "TITLE_ROMAJI"
    TITLE_ROMAJI_DESC = "TITLE_ROMAJI_DESC"
    TITLE_ENGLISH = "TITLE_ENGLISH"
    TITLE_ENGLISH_DESC = "TITLE_ENGLISH_DESC"
    TITLE_NATIVE = "TITLE_NATIVE"
    TITLE_NATIVE_DESC = "TITLE_NATIVE_DESC"
    TYPE = "TYPE"
    TYPE_DESC = "TYPE_DESC"
    FORMAT = "FORMAT"
    FORMAT_DESC = "FORMAT_DESC"
    START_DATE = "START_DATE"
    START_DATE_DESC = "START_DATE_DESC"
    END_DATE = "END_DATE"
    END_DATE_DESC = "END_DATE_DESC"
    SCORE = "SCORE"
    SCORE_DESC = "SCORE_DESC"
    POPULARITY = "POPULARITY"
    POPULARITY_DESC = "POPULARITY_DESC"
    TRENDING = "TRENDING"
    TRENDING_DESC = "TRENDING_DESC"
    EPISODES = "EPISODES"
    EPISODES_DESC = "EPISODES_DESC"
    DURATION = "DURATION"
    DURATION_DESC = "DURATION_DESC"
    STATUS = "STATUS"
    STATUS_DESC = "STATUS_DESC"
    CHAPTERS = "CHAPTERS"
    CHAPTERS_DESC = "CHAPTERS_DESC"
    VOLUMES = "VOLUMES"
    VOLUMES_DESC = "VOLUMES_DESC"
    UPDATED_AT = "UPDATED_AT"
    UPDATED_AT_DESC = "UPDATED_AT_DESC"
    SEARCH_MATCH = "SEARCH_MATCH"
    FAVOURITES = "FAVOURITES"
    FAVOURITES_DESC = "FAVOURITES_DESC"


class MediaListStatus(AniListBaseEnum):
    """Enum representing status of a media list entry (CURRENT, COMPLETED, etc)."""

    _ignore_ = ["__priority"]

    CURRENT = "CURRENT"
    PLANNING = "PLANNING"
    COMPLETED = "COMPLETED"
    DROPPED = "DROPPED"
    PAUSED = "PAUSED"
    REPEATING = "REPEATING"

    __priority = {
        "PLANNING": 1,
        "CURRENT": 2,
        "PAUSED": 2,
        "DROPPED": 2,
        "COMPLETED": 3,
        "REPEATING": 3,
    }

    def __eq__(self, other: object) -> bool:
        """Check equality with another MediaListStatus."""
        if not isinstance(other, MediaListStatus):
            return NotImplemented
        return self.value == other.value

    def __ne__(self, other: object) -> bool:
        """Check inequality with another MediaListStatus."""
        if not isinstance(other, MediaListStatus):
            return NotImplemented
        return self.value != other.value

    def __lt__(self, other: object) -> bool:
        """Check if status is less than another based on priority."""
        if not isinstance(other, MediaListStatus):
            return NotImplemented
        return (
            self.value != other.value
            and self.__priority[self.value] < self.__priority[other.value]
        )

    def __le__(self, other: object) -> bool:
        """Check if status is less than or equal to another based on priority."""
        if not isinstance(other, MediaListStatus):
            return NotImplemented
        return self.__priority[self.value] <= self.__priority[other.value]

    def __gt__(self, other: object) -> bool:
        """Check if status is greater than another based on priority."""
        if not isinstance(other, MediaListStatus):
            return NotImplemented
        return (
            self.value != other.value
            and self.__priority[self.value] > self.__priority[other.value]
        )

    def __ge__(self, other: object) -> bool:
        """Check if status is greater than or equal to another based on priority."""
        if not isinstance(other, MediaListStatus):
            return NotImplemented
        return self.__priority[self.value] >= self.__priority[other.value]


class ScoreFormat(AniListBaseEnum):
    """Enum representing score formats for media list entries."""

    POINT_100 = "POINT_100"
    POINT_10_DECIMAL = "POINT_10_DECIMAL"
    POINT_10 = "POINT_10"
    POINT_5 = "POINT_5"
    POINT_3 = "POINT_3"


class UserTitleLanguage(AniListBaseEnum):
    """Enum representing user title language preferences."""

    ROMAJI = "ROMAJI"
    ENGLISH = "ENGLISH"
    NATIVE = "NATIVE"
    ROMAJI_STYLISED = "ROMAJI_STYLISED"
    ENGLISH_STYLISED = "ENGLISH_STYLISED"
    NATIVE_STYLISED = "NATIVE_STYLISED"


class AniListBaseModel(BaseModel):
    """Base, abstract class for all AniList models to represent GraphQL objects.

    Provides serialization, aliasing, and GraphQL query generation utilities.
    """

    _processed_models: ClassVar[set] = set()

    def model_dump(self, **kwargs) -> dict:
        """Convert the model to a dictionary, converting all keys to camelCase.

        Returns:
            dict: Dictionary representation of the model.
        """
        return super().model_dump(by_alias=True, **kwargs)

    def model_dump_json(self, **kwargs) -> str:
        """Serialize the model to JSON, converting all keys to camelCase.

        Returns:
            str: JSON serialized string of the model.
        """
        return super().model_dump_json(by_alias=True, **kwargs)

    def unset_fields(self, fields: list[str]) -> None:
        """Unset specified fields to their default values.

        Args:
            fields (list[str]): List of field names to unset.
        """
        for field, field_info in self.__class__.model_fields.items():
            if field in fields:
                setattr(self, field, field_info.default)

    @classmethod
    @cache
    def model_dump_graphql(cls) -> str:
        """Generate GraphQL query fields for this model.

        Returns:
            str: The GraphQL query fields.
        """
        if cls.__name__ in cls._processed_models:
            return ""

        cls._processed_models.add(cls.__name__)
        fields = cls.model_fields
        graphql_fields = []

        for field_name, field in fields.items():
            field_type = (
                get_args(field.annotation)[0]
                if get_origin(field.annotation)
                else field.annotation
            )

            camel_field_name = to_camel(field_name)

            if isinstance(field_type, type) and issubclass(
                field_type, AniListBaseModel
            ):
                nested_fields = field_type.model_dump_graphql()
                if nested_fields:
                    graphql_fields.append(f"{camel_field_name} {{\n{nested_fields}\n}}")
            else:
                graphql_fields.append(f"{camel_field_name}")

        cls._processed_models.remove(cls.__name__)
        return "\n".join(graphql_fields)

    def __hash__(self) -> int:
        """Return hash of the model representation."""
        return hash(self.__repr__())

    def __repr__(self) -> str:
        """Return string representation of the model."""
        return f"<{
            ' : '.join(
                [f'{k}={v}' for k, v in self.model_dump().items() if v is not None]
            )
        }>"

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class UserOptions(AniListBaseModel):
    """Model representing user options/preferences."""

    title_language: UserTitleLanguage | None = None
    timezone: str | None = None


class MediaListOptions(AniListBaseModel):
    """Model representing media list options for a user."""

    score_format: ScoreFormat | None = None
    row_order: str | None = None


class User(AniListBaseModel):
    """Model representing an AniList user."""

    id: int
    name: str
    options: UserOptions | None = None
    media_list_options: MediaListOptions | None = None


class PageInfo(AniListBaseModel):
    """Model representing pagination info for AniList queries."""

    total: int | None = None
    per_page: int | None = None
    current_page: int | None = None
    last_page: int | None = None
    has_next_page: bool | None = None


class MediaTitle(AniListBaseModel):
    """Model representing media titles in various languages."""

    romaji: str | None = None
    english: str | None = None
    native: str | None = None
    user_preferred: str | None = None

    def titles(self) -> list[str]:
        """Return a list of all the available titles.

        Returns:
            list[str]: All the available titles.
        """
        return [getattr(self, t) for t in self.__class__.model_fields if t]

    def __str__(self) -> str:
        """Return the first available title or an empty string.

        Returns:
            str: A title or an empty string.
        """
        return self.user_preferred or self.english or self.romaji or self.native or ""


class FuzzyDate(AniListBaseModel):
    """Model representing a fuzzy date (year, month, day may be missing)."""

    year: int | None = None
    month: int | None = None
    day: int | None = None

    @staticmethod
    def from_date(d: date | datetime | None) -> FuzzyDate | None:
        """Create a FuzzyDate from a date or datetime object.

        Args:
            d (date | datetime | None): A date or datetime object.

        Returns:
            FuzzyDate | None: An equivalent FuzzyDate object or None.
        """
        if d is None:
            return None
        return FuzzyDate(year=d.year, month=d.month, day=d.day)

    def to_datetime(self) -> datetime | None:
        """Convert the FuzzyDate to a datetime object.

        Returns:
            datetime | None: A datetime object or None if the FuzzyDate is incomplete.
        """
        if not self.year:
            return None
        return datetime(year=self.year, month=self.month or 1, day=self.day or 1)

    def __bool__(self) -> bool:
        """Return True if the date has a year, else False."""
        return self.year is not None

    def __eq__(self, other: Any) -> bool:
        """Check equality with another FuzzyDate."""
        if not isinstance(other, FuzzyDate):
            return False
        return (
            self.year == other.year
            and self.month == other.month
            and self.day == other.day
        )

    def __lt__(self, other: Any) -> bool:
        """Check if this date is less than another."""
        if not isinstance(other, FuzzyDate):
            return NotImplemented
        if not self.year or not other.year:
            return True
        return ((self.year), (self.month or 1), (self.day or 1)) < (
            (other.year),
            (other.month or 1),
            (other.day or 1),
        )

    def __le__(self, other: Any) -> bool:
        """Check if this date is less than or equal to another."""
        if not isinstance(other, FuzzyDate):
            return NotImplemented
        if not self.year or not other.year:
            return True
        return ((self.year), (self.month or 1), (self.day or 1)) <= (
            (other.year),
            (other.month or 1),
            (other.day or 1),
        )

    def __gt__(self, other: Any) -> bool:
        """Check if this date is greater than another."""
        if not isinstance(other, FuzzyDate):
            return NotImplemented
        if not self.year or not other.year:
            return True
        return ((self.year), (self.month or 1), (self.day or 1)) > (
            (other.year),
            (other.month or 1),
            (other.day or 1),
        )

    def __ge__(self, other: Any) -> bool:
        """Check if this date is greater than or equal to another."""
        if not isinstance(other, FuzzyDate):
            return NotImplemented
        if not self.year or not other.year:
            return True
        return ((self.year), (self.month or 1), (self.day or 1)) >= (
            (other.year),
            (other.month or 1),
            (other.day or 1),
        )

    def __str__(self) -> str:
        """Return string representation of the FuzzyDate."""
        return self.__repr__()

    def __repr__(self) -> str:
        """Return formatted string representation of the FuzzyDate."""
        return (
            f"{self.year or '????'}-"
            f"{str(self.month).zfill(2) if self.month else '??'}-"
            f"{str(self.day).zfill(2) if self.day else '??'}"
        )


class MediaList(AniListBaseModel):
    """Model representing a media list entry in AniList."""

    id: int
    user_id: int
    media_id: int
    status: MediaListStatus | None = None
    score: float | None = None
    progress: int | None = None
    repeat: int | None = None
    notes: str | None = None
    started_at: FuzzyDate | None = None
    completed_at: FuzzyDate | None = None
    created_at: UTCDateTime | None = None
    updated_at: UTCDateTime | None = None

    @staticmethod
    def diff(old: MediaList | None, new: MediaList) -> str:
        """Generate a diff string between two MediaList objects.

        Args:
            old (MediaList | None): The old MediaList object.
            new (MediaList): The new MediaList object.

        Returns:
            str: A diff string between the two objects.
        """
        if old is None:
            old = MediaList(id=new.id, user_id=new.user_id, media_id=new.media_id)

        diff_parts = []
        for field, _ in old.__class__.model_fields.items():
            old_value = getattr(old, field)
            new_value = getattr(new, field)

            if old_value != new_value:
                if field == "notes":
                    if old_value:
                        old_value = old_value[:50].replace("\n", "  ") + "..."
                    if new_value:
                        new_value = new_value[:50].replace("\n", "  ") + "..."
                diff_parts.append(f"{field}: {old_value} -> {new_value}")
        return "(" + ", ".join(diff_parts) + ")"

    def __str__(self) -> str:
        """Return string representation of the MediaList entry."""
        notes_truncated = None
        if self.notes:
            notes_truncated = self.notes[:50].replace("\n", "  ") + "..."

        return (
            f"(status={self.status}, score={self.score}, progress={self.progress}, "
            f"repeat={self.repeat}, notes={notes_truncated}, started_at="
            f"{self.started_at}, completed_at={self.completed_at})"
        )


EntryType = TypeVar("EntryType", bound=MediaList)
GroupType = TypeVar("GroupType", bound="MediaListGroup")


class MediaListGroup(AniListBaseModel, Generic[EntryType]):
    """Model representing a group of media list entries."""

    entries: list[EntryType] = []
    name: str | None = None
    is_custom_list: bool | None = None
    is_split_completed_list: bool | None = None
    status: MediaListStatus | None = None


class MediaListCollection(AniListBaseModel, Generic[GroupType]):
    """Model representing a collection of media list groups for a user."""

    user: User | None = None
    lists: list[GroupType] = []
    has_next_chunk: bool | None = None


class AiringSchedule(AniListBaseModel):
    """Model representing an airing schedule for a media entry."""

    id: int
    airing_at: UTCDateTime
    time_until_airing: timedelta
    episode: int
    media_id: int


class MediaWithoutList(AniListBaseModel):
    """Model representing a media entry without list information."""

    id: int
    id_mal: int | None = None
    type: MediaType | None = None
    format: MediaFormat | None = None
    status: MediaStatus | None = None
    season: MediaSeason | None = None
    season_year: int | None = None
    episodes: int | None = None
    duration: int | None = None
    synonyms: list[str] | None = None
    is_locked: bool | None = None
    title: MediaTitle | None = None
    start_date: FuzzyDate | None = None
    end_date: FuzzyDate | None = None
    next_airing_episode: AiringSchedule | None = None


class Media(MediaWithoutList):
    """Model representing a media entry with list information."""

    media_list_entry: MediaList | None = None


class MediaListWithMedia(MediaList):
    """Model representing a media list entry with attached media info."""

    media: MediaWithoutList | None = None


class MediaListGroupWithMedia(MediaListGroup[MediaListWithMedia]):
    """Model representing a group of media list entries with media info."""

    pass


class MediaListCollectionWithMedia(MediaListCollection[MediaListGroupWithMedia]):
    """Model representing a collection of media list groups with media info."""

    pass


class MediaConnection(AniListBaseModel):
    """Model representing a paginated connection of media entries."""

    nodes: list[Media]
    pageInfo: PageInfo = PageInfo()
